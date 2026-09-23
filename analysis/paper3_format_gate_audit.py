"""Read-only exact replay of the 16-call format gate; never loads model weights."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
from experiments import paper3_bonsai_format_gate as study
from paper3.audit_runtime import digest
from paper3_budgeted_episode_audit import expected_boundary, verify_tokenization


def verify_trace(row, closing_id):
    previous = [row["prompt_token_ids"][-1]] + row["generated_token_ids"]
    events = row["grammar_trace"]
    assert len(events) == len(previous), "generation lookahead trace count mismatch"
    active = False
    initial_size = events[0]["input_tokens"]
    assert 1 <= initial_size <= len(row["prompt_token_ids"])
    for i, (event, token) in enumerate(zip(events, previous)):
        active = active or token == closing_id
        assert event == dict(previous_token=token, input_tokens=initial_size+i,
                             active=active, constrained=active), "grammar phase trace mismatch"


def audit(root):
    manifest = json.loads((root / "manifest.json").read_text())
    protocol, ph = manifest["protocol"], digest(manifest)
    if protocol["name"] != study.NAME:
        raise ValueError("wrong protocol")
    snapshots = json.loads((root / "sources.json").read_text())
    for path, sha in manifest["sources"].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha:
            raise ValueError("frozen source changed: " + path)
        if hashlib.sha256(snapshots[str(Path(path).relative_to(ROOT))].encode()).hexdigest() != sha:
            raise ValueError("source snapshot mismatch: " + path)
    for group in ("runtime_source_sha256", "grammar_source_sha256"):
        for path, sha in protocol[group].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha:
                raise ValueError("runtime source changed: " + path)
    for rel, sha in protocol["model_file_sha256"].items():
        if hashlib.sha256((Path(protocol["model"]) / rel).read_bytes()).hexdigest() != sha:
            raise ValueError("model artifact changed: " + rel)
    if protocol["cases"] != study.cases():
        raise ValueError("frozen fixtures differ")
    from transformers import AutoTokenizer
    import llguidance as llg
    import llguidance.hf
    tokenizer = AutoTokenizer.from_pretrained(protocol["model"], local_files_only=True)
    base = AutoTokenizer.from_pretrained(protocol["base_tokenizer"], local_files_only=True)
    grammar_tokenizer = llguidance.hf.from_tokenizer(tokenizer)
    config = json.loads((Path(protocol["model"]) / "generation_config.json").read_text())
    eos = config.get("eos_token_id", tokenizer.eos_token_id)
    eos = set(eos if isinstance(eos, list) else [eos])
    start, close, newline = [tokenizer.encode(x, add_special_tokens=False)[-1] for x in ("<think>", "</think>", "\n")]
    records = {p.stem:json.loads(p.read_text()) for p in (root / "calls").glob("*.json")}
    sessions = {p.stem:json.loads(p.read_text()) for p in (root / "sessions").glob("*.json")}
    errors, keys, results, checked, grammar_checked = [], [], [], 0, 0
    for case in protocol["cases"]:
        request = study.request_for(protocol["model"], case)
        key = digest(dict(request=request, protocol=ph))
        keys.append(key)
        try:
            row = records[key]
            assert row["status"] == "recorded" and row["protocol_hash"] == ph and row["request"] == request
            usage = row["response"]["usage"]
            assert len(row["prompt_token_ids"]) == usage["prompt_tokens"] <= study.old.MAX_INPUT
            assert len(row["generated_token_ids"]) == usage["completion_tokens"] <= study.old.CAP
            if not row.get("generation_error"):
                assert row["cached_tokens"] == 0
                verify_tokenization(row, tokenizer, base, eos)
                assert row["boundary"] == expected_boundary(row["generated_token_ids"], start, close, newline,
                    row["response"]["choices"][0]["finish_reason"])
                verify_trace(row, close)
                checked += 1
                if close in row["generated_token_ids"]:
                    suffix = row["generated_token_ids"][row["generated_token_ids"].index(close)+1:]
                    normal = row["response"]["choices"][0]["finish_reason"] == "stop"
                    grammar = llg.JsonCompiler(separators=(", ", ": "), whitespace_pattern="").compile(json.dumps(case["schema"]))
                    matcher = llg.LLMatcher(grammar_tokenizer, grammar, log_level=0)
                    answer_tokens = suffix[:-1] if normal else suffix
                    assert matcher.consume_tokens(answer_tokens) and not matcher.is_error()
                    if normal:
                        assert suffix[-1] in eos and matcher.is_accepting()
                        assert matcher.consume_token(suffix[-1]) and not matcher.is_error()
                    grammar_checked += 1
            result = dict(study.score(row, case), name=case["name"], call_keys=[key], protocol_hash=ph)
            assert result == sessions[case["name"]]
            results.append(result)
        except (AssertionError, ValueError, KeyError, IndexError) as exc:
            errors.append(case["name"] + ": " + str(exc))
    if set(keys) != set(records) or len(keys) != len(set(keys)):
        errors.append("missing, duplicate or unattached calls")
    if set(sessions) != {c["name"] for c in protocol["cases"]} | {"terminal"}:
        errors.append("missing or extra sessions")
    terminal = dict(passed=all(r["passed"] for r in results), checks=len(results), valid=sum(r["valid"] for r in results),
        exact=sum(r["exact"] is True for r in results), exact_scored=12, protocol_hash=ph)
    if sessions.get("terminal") != terminal:
        errors.append("terminal mismatch")
    ordered = [records[k] for k in keys if k in records]
    if any(b["started_unix"] < a["started_unix"]+a.get("elapsed_seconds", 0) for a,b in zip(ordered, ordered[1:])):
        errors.append("overlapping or out-of-order calls")
    tokens = sum(r.get("response",{}).get("usage",{}).get("completion_tokens",0) for r in ordered)
    if len(records) > 16 or tokens > 24576 or list(root.rglob("*.partial")):
        errors.append("call/token cap exceeded or partial writes")
    return dict(protocol_hash=ph, integrity_errors=errors, calls=len(records), terminal=terminal,
        tokenization_checks=checked, grammar_path_checks=grammar_checked,
        checks=[{k:v for k,v in r.items() if k not in ("protocol_hash", "call_keys")} for r in results],
        generated_tokens=tokens, forced_tokens=sum(r.get("boundary",{}).get("forced_output_tokens",0) for r in ordered),
        generation_seconds=sum(r.get("elapsed_seconds",0) for r in ordered),
        peak_memory_gb=max((r.get("peak_memory_gb") or 0 for r in ordered), default=0),
        scope="selected private instrument checks; no collective or paper-worthy result")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.archive:
        from experiments.paper3_archive_agenda import archive
        print(json.dumps(archive(args.root, args.archive, report_fn=audit), indent=2))
    else:
        report = audit(args.root)
        print(json.dumps(report, indent=2))
        sys.exit(bool(report["integrity_errors"]))
