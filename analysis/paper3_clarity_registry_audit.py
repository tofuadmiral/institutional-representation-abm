"""Read-only provenance, controller, scoring and selected-history cell audit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
from experiments import paper3_bonsai_clarity_registry as study
from paper3.audit_runtime import digest
from paper3_budgeted_episode_audit import expected_boundary, verify_tokenization


def audit(root, check_tokenization=False):
    manifest = json.loads((root / "manifest.json").read_text())
    protocol, ph = manifest["protocol"], digest(manifest)
    if protocol["name"] != study.NAME:
        raise ValueError("wrong diagnostic")
    errors = []
    snapshots = json.loads((root / "sources.json").read_text())
    for name, expected in manifest["sources"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError("cannot replay changed frozen source: " + name)
        if hashlib.sha256(snapshots[str(Path(name).relative_to(ROOT))].encode()).hexdigest() != expected:
            errors.append("source snapshot mismatch: " + name)
    parent = Path(protocol["predecessor"]["path"])
    if digest(json.loads((parent / "manifest.json").read_text())) != study.PARENT_HASH:
        raise ValueError("parent manifest mismatch")
    for name, expected in protocol["predecessor"]["records"].items():
        if hashlib.sha256((parent / name).read_bytes()).hexdigest() != expected:
            raise ValueError("parent record changed: " + name)
    originals = {p.stem: json.loads(p.read_text()) for p in (parent / "calls").glob("*.json")}
    episode = json.loads((parent / "sessions/episode.json").read_text())
    cases = study.cases_for(originals, episode)
    if cases != protocol["cases"]:
        errors.append("frozen cases differ from permitted transformations")
    tokenfile = Path(protocol["model"]) / "tokenizer.json"
    if hashlib.sha256(tokenfile.read_bytes()).hexdigest() != protocol["model_file_sha256"]["tokenizer.json"]:
        raise ValueError("tokenizer changed")
    data = json.loads(tokenfile.read_text())
    specials = {t["content"]: t["id"] for t in data["added_tokens"]}
    newline = data["model"]["vocab"]["Ċ"]
    if check_tokenization:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(protocol["model"], local_files_only=True)
        base = AutoTokenizer.from_pretrained(protocol["base_tokenizer"], local_files_only=True)
        config = json.loads((Path(protocol["model"]) / "generation_config.json").read_text())
        eos = config.get("eos_token_id", tokenizer.eos_token_id)
        eos = set(eos if isinstance(eos, list) else [eos])
    rows = {p.stem: json.loads(p.read_text()) for p in (root / "calls").glob("*.json")}
    sessions = {p.stem: json.loads(p.read_text()) for p in (root / "sessions").glob("*.json")}
    references, timeline, token_checks = [], [], 0
    for case in cases:
        request = study.old.request_for(protocol["model"], case["messages"], case["seed"])
        key = digest(dict(request=request, protocol=ph))
        references.append(key)
        try:
            row = rows[key]
            assert row["request"] == request and row["protocol_hash"] == ph and row["status"] == "recorded"
            usage = row["response"]["usage"]
            assert len(row["prompt_token_ids"]) == usage["prompt_tokens"] <= study.old.MAX_INPUT
            assert len(row["generated_token_ids"]) == usage["completion_tokens"] <= study.old.CAP
            assert row["cached_tokens"] == 0
            if not row.get("generation_error"):
                assert row["boundary"] == expected_boundary(row["generated_token_ids"],
                    specials["<think>"], specials["</think>"], newline, row["response"]["choices"][0]["finish_reason"])
            expected = dict(study.score(row, case, originals[case["original_key"]]),
                case=case["name"], actor=case["actor"], cell=case["cell"], call_keys=[key], protocol_hash=ph)
            assert sessions[case["name"]] == expected
            timeline.append((row["started_unix"], row["elapsed_seconds"]))
            if check_tokenization:
                verify_tokenization(row, tokenizer, base, eos)
                token_checks += 1
        except (AssertionError, ValueError, KeyError) as exc:
            errors.append(case["name"] + ": raw/session/token replay mismatch " + str(exc))
    if len(references) != study.MAX_CALLS or len(set(references)) != study.MAX_CALLS or set(references) != set(rows):
        errors.append("missing, duplicate or unreferenced raw calls")
    if set(sessions) != {c["name"] for c in cases}:
        errors.append("missing or extra sessions")
    if any(b[0] < a[0] + a[1] for a, b in zip(timeline, timeline[1:])):
        errors.append("execution order changed or calls overlapped")
    if list(root.rglob("*.partial")):
        errors.append("partial write remains")
    total = sum(r.get("response", {}).get("usage", {}).get("completion_tokens", 0) for r in rows.values())
    if len(rows) > study.MAX_CALLS or total > study.MAX_CALLS * study.old.CAP:
        errors.append("frozen budget exceeded")
    cells = study.aggregate(cases, sessions, episode)
    for cell, result in cells.items():
        selected = [rows[k] for c, k in zip(cases, references) if c["cell"] == cell and k in rows]
        result.update(input_tokens=[r["response"]["usage"]["prompt_tokens"] for r in selected],
            output_tokens=sum(r["response"]["usage"]["completion_tokens"] for r in selected),
            forced_closures=sum(r["boundary"].get("closure_origin") == "forced" for r in selected))
    controls = {str(c["actor"]): sessions.get(c["name"], {}).get("control_replay")
                for c in cases if not c["clear"] and not c["registry"]}
    return dict(protocol_hash=ph, integrity_errors=errors, calls=len(rows), cells=cells,
        original_control_replay=controls, generated_tokens=total,
        forced_tokens=sum(r.get("boundary", {}).get("forced_output_tokens", 0) for r in rows.values()),
        elapsed_generation_seconds=sum(r.get("elapsed_seconds", 0) for r in rows.values()),
        peak_memory_gb=max((r.get("peak_memory_gb") or 0 for r in rows.values()), default=0),
        tokenization_records_verified=token_checks if check_tokenization else None,
        scope="one adaptively selected history, descriptive paired prompts; no independent-history replication or causal proof of internal reasoning")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--check-tokenization", action="store_true")
    args = parser.parse_args()
    report = audit(args.root, args.check_tokenization)
    print(json.dumps(report, indent=2))
    sys.exit(bool(report["integrity_errors"]))
