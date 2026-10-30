"""Read-only replay of every agenda request, action and institutional outcome."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import paper3_bonsai_agenda as study
from paper3.audit_runtime import digest
from analysis.paper3_budgeted_episode_audit import expected_boundary, verify_tokenization


class Replay:
    def __init__(self, protocol, records, session, tokenizer=None, base=None):
        self.protocol, self.records, self.session = protocol, records, session
        self.tokenizer, self.base, self.position = tokenizer, base, 0

    def call(self, messages, seed, base):
        if self.position == len(self.session["call_keys"]):
            pending = self.session.get("unsubmitted_request")
            if pending != dict(messages=messages, seed=seed):
                raise RuntimeError("unexpected missing replay record")
            if self.tokenizer is None:
                raise RuntimeError("pre-inference failure needs tokenizer verification")
            study.render(self.tokenizer, self.base, messages)  # Must reproduce the pre-inference failure.
            raise RuntimeError("saved pre-inference failure does not reproduce")
        key = self.session["call_keys"][self.position]
        self.position += 1
        row = self.records[key]
        if row["request"] != study.request_for(self.protocol["model"], messages, seed):
            raise RuntimeError("exact request replay mismatch")
        return key, row


def audit(root, check_tokenization=False):
    manifest = json.loads((root / "manifest.json").read_text())
    protocol, ph = manifest["protocol"], digest(manifest)
    if protocol["name"] != study.NAME:
        raise ValueError("wrong protocol")
    snapshots = json.loads((root / "sources.json").read_text())
    errors = []
    for name, expected in manifest["sources"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError("frozen source changed: " + name)
        if hashlib.sha256(snapshots[str(Path(name).relative_to(ROOT))].encode()).hexdigest() != expected:
            errors.append("source snapshot mismatch: " + name)
    if protocol["cases"] != study.game.gate_cases() or protocol["episodes"] != study.specifications():
        errors.append("frozen fixtures differ")
    records = {p.stem: json.loads(p.read_text()) for p in (root / "calls").glob("*.json")}
    sessions = {p.stem: json.loads(p.read_text()) for p in (root / "sessions").glob("*.json")}
    tokenfile = Path(protocol["model"]) / "tokenizer.json"
    if hashlib.sha256(tokenfile.read_bytes()).hexdigest() != protocol["model_file_sha256"]["tokenizer.json"]:
        raise ValueError("tokenizer changed")
    data = json.loads(tokenfile.read_text())
    specials = {t["content"]: t["id"] for t in data["added_tokens"]}
    newline = data["model"]["vocab"]["Ċ"]
    tokenizer = base = None
    if check_tokenization:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(protocol["model"], local_files_only=True)
        base = AutoTokenizer.from_pretrained(protocol["base_tokenizer"], local_files_only=True)
        config = json.loads((Path(protocol["model"]) / "generation_config.json").read_text())
        eos = config.get("eos_token_id", tokenizer.eos_token_id)
        eos = set(eos if isinstance(eos, list) else [eos])
    token_checks = 0
    for key, row in records.items():
        try:
            assert row["status"] == "recorded" and row["protocol_hash"] == ph
            assert key == digest(dict(request=row["request"], protocol=ph))
            assert row["request"] == study.request_for(protocol["model"], row["request"]["messages"], row["request"]["seed"])
            usage = row["response"]["usage"]
            assert len(row["prompt_token_ids"]) == usage["prompt_tokens"] <= study.MAX_INPUT
            assert len(row["generated_token_ids"]) == usage["completion_tokens"] <= study.CAP
            assert row["cached_tokens"] == 0
            if not row.get("generation_error"):
                assert row["boundary"] == expected_boundary(row["generated_token_ids"], specials["<think>"], specials["</think>"], newline, row["response"]["choices"][0]["finish_reason"])
                if check_tokenization:
                    verify_tokenization(row, tokenizer, base, eos)
                    token_checks += 1
        except (AssertionError, KeyError, ValueError) as exc:
            errors.append("raw record mismatch: " + key + " " + str(exc))
    expected_names = {"terminal"} | {c["name"] for c in protocol["cases"]} | {s["name"] for s in protocol["episodes"]}
    if set(sessions) != expected_names:
        errors.append("missing or extra terminal sessions")
    references, exact = [], []
    for case in protocol["cases"]:
        key = digest(dict(request=study.request_for(protocol["model"], case["messages"], case["seed"]), protocol=ph))
        references.append(key)
        try:
            result = dict(study.score_gate(records[key], case), name=case["name"], expected=case["expected"], call_keys=[key], protocol_hash=ph)
            assert sessions[case["name"]] == result
            exact.append(result["exact"])
        except (AssertionError, KeyError, ValueError) as exc:
            errors.append("gate replay: " + case["name"] + " " + str(exc))
    passed = len(exact) == 8 and all(exact)
    statuses, readout = {}, {}
    for spec in protocol["episodes"]:
        saved = sessions.get(spec["name"])
        if saved is None:
            continue
        references.extend(saved["call_keys"])
        try:
            if passed:
                replay = Replay(protocol, records, saved, tokenizer, base)
                expected = dict(study.run_one(replay, None, spec), protocol_hash=ph)
                assert replay.position == len(saved["call_keys"])
            else:
                expected = dict(name=spec["name"], status="not_run", reason="private interface gate failed", call_keys=[], protocol_hash=ph)
            assert saved == expected
        except (AssertionError, KeyError, ValueError, RuntimeError) as exc:
            errors.append("episode replay: " + spec["name"] + " " + str(exc))
        statuses[spec["name"]] = saved["status"]
        readout[spec["name"]] = {k: saved[k] for k in ("status", "error", "resolution", "metrics", "replay", "ratification_consistency") if k in saved}
    if sessions.get("terminal") != dict(gate_passed=passed, episodes=statuses, protocol_hash=ph):
        errors.append("terminal decision mismatch")
    if len(references) != len(set(references)) or set(references) != set(records):
        errors.append("missing, duplicate or unattached calls")
    timeline = [records[k] for k in references if k in records and "elapsed_seconds" in records[k]]
    if any(b["started_unix"] < a["started_unix"] + a["elapsed_seconds"] for a,b in zip(timeline,timeline[1:])):
        errors.append("overlapping or out-of-order calls")
    if list(root.rglob("*.partial")):
        errors.append("partial writes remain")
    tokens = sum(r.get("response", {}).get("usage", {}).get("completion_tokens", 0) for r in records.values())
    if len(records) > 108 or tokens > 165888:
        errors.append("authorized cap exceeded")
    return dict(protocol_hash=ph, integrity_errors=errors, calls=len(records), gate_exact=sum(exact), gate_total=8,
        episodes=readout, generated_tokens=tokens,
        forced_tokens=sum(r.get("boundary", {}).get("forced_output_tokens", 0) for r in records.values()),
        generation_seconds=sum(r.get("elapsed_seconds", 0) for r in records.values()),
        peak_memory_gb=max((r.get("peak_memory_gb") or 0 for r in records.values()), default=0),
        tokenization_checks=token_checks if check_tokenization else None,
        scope="two selected profiles; feasibility/discovery only, no confirmation or significance claim")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--check-tokenization", action="store_true")
    args = parser.parse_args()
    report = audit(args.root, args.check_tokenization)
    print(json.dumps(report, indent=2))
    sys.exit(bool(report["integrity_errors"]))
