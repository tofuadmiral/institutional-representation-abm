"""Frozen seed-stability audit with exact serialized schema/grammar replay."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
from experiments import paper3_bonsai_agenda_seed_stability as study
from paper3.audit_runtime import digest
from paper3_budgeted_episode_audit import expected_boundary, verify_tokenization
from paper3_format_gate_audit import verify_trace


class Replay:
    def __init__(self, protocol, records, session, tokenizer, base):
        self.protocol, self.records, self.session = protocol, records, session
        self.tokenizer, self.base, self.position = tokenizer, base, 0
        self.schemas = {}

    def call(self, case, base):
        if self.position == len(self.session["call_keys"]):
            if self.session.get("unsubmitted_request") != case:
                raise RuntimeError("unexpected missing replay record")
            study.old.render(self.tokenizer, self.base, case["messages"])
            raise RuntimeError("saved pre-inference failure does not reproduce")
        key = self.session["call_keys"][self.position]
        self.position += 1
        row = self.records[key]
        if row["request"] != study.request_for(self.protocol["model"], case):
            raise RuntimeError("exact request replay mismatch")
        self.schemas[key] = case["schema"]
        return key, row


def paired_readout(sessions):
    result = []
    for seed in study.SEEDS:
        names = {arm:f"conflict39-s{seed}-{arm}" for arm in ("D","B")}
        pair = {arm:sessions.get(name) for arm,name in names.items()}
        row = dict(seed=seed, episodes=names,
                   completed=all(s is not None and s["status"] == "completed" for s in pair.values()))
        if row["completed"]:
            d, b = pair["D"], pair["B"]
            row.update(outcomes={arm:s["resolution"] for arm,s in pair.items()},
                locked_proposals={arm:s["metrics"]["locked_proposal"]["policy"] for arm,s in pair.items()},
                locked_leader_advantage_B_minus_D=b["metrics"]["locked_proposal"]["leader_advantage"]-d["metrics"]["locked_proposal"]["leader_advantage"],
                enacted_mean_regret_B_minus_D=b["metrics"]["enacted"]["mean_regret"]-d["metrics"]["enacted"]["mean_regret"],
                enacted_leader_advantage_B_minus_D=b["metrics"]["enacted"]["leader_advantage"]-d["metrics"]["enacted"]["leader_advantage"],
                utility_B_minus_D={r:b["metrics"]["enacted"]["utilities"][r]-d["metrics"]["enacted"]["utilities"][r] for r in study.game.ROLES})
            row["principals_gaining_B_over_D"] = sum(v > 0 for v in row["utility_B_minus_D"].values())
            row["principals_losing_B_vs_D"] = sum(v < 0 for v in row["utility_B_minus_D"].values())
        else:
            row["reason"] = "missing or failed episode; no policy or treatment difference imputed"
        result.append(row)
    return result


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
    if protocol["episodes"] != study.specifications() or protocol["prerequisite"] != study.prerequisite():
        raise ValueError("frozen fixtures or prerequisite differ")
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
    errors, references, checked, grammar_checked = [], [], 0, 0
    statuses, readout, schemas = {}, {}, {}
    for spec in protocol["episodes"]:
        try:
            saved = sessions[spec["name"]]
            references.extend(saved["call_keys"])
            replay = Replay(protocol, records, saved, tokenizer, base)
            expected = dict(study.run_one(replay, None, spec), protocol_hash=ph)
            assert replay.position == len(saved["call_keys"])
            assert saved == expected
            assert not set(schemas) & set(replay.schemas)
            schemas.update(replay.schemas)
            statuses[spec["name"]] = saved["status"]
            readout[spec["name"]] = {k:saved[k] for k in ("status", "error", "resolution", "metrics", "replay", "ratification_consistency") if k in saved}
            readout[spec["name"]]["overlong_messages"] = sum(a["overlong_message"] for a in saved["actions"])
        except (AssertionError, ValueError, KeyError, RuntimeError) as exc:
            errors.append("episode " + spec["name"] + ": " + str(exc))
    for key, row in records.items():
        try:
            assert row["status"] == "recorded" and row["protocol_hash"] == ph
            assert key == digest(dict(request=row["request"], protocol=ph))
            schema_text = json.dumps(schemas[key])
            assert row["request"]["response_schema"] == schemas[key]
            assert row["schema_text"] == schema_text
            compiled = llg.JsonCompiler(separators=(", ", ": "), whitespace_pattern="").compile(schema_text)
            assert row["compiled_grammar"] == compiled
            assert row["grammar_sha256"] == hashlib.sha256(compiled.encode()).hexdigest()
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
                    grammar = row["compiled_grammar"]
                    matcher = llg.LLMatcher(grammar_tokenizer, grammar, log_level=0)
                    assert matcher.consume_tokens(suffix[:-1] if normal else suffix) and not matcher.is_error()
                    if normal:
                        assert suffix[-1] in eos and matcher.is_accepting()
                        assert matcher.consume_token(suffix[-1]) and not matcher.is_error()
                    grammar_checked += 1
        except (AssertionError, ValueError, KeyError, IndexError) as exc:
            errors.append("raw " + key + ": " + str(exc))
    if len(references) != len(set(references)) or set(references) != set(records):
        errors.append("missing, duplicate or unattached calls")
    if set(sessions) != {s["name"] for s in protocol["episodes"]} | {"terminal"}:
        errors.append("missing or extra sessions")
    terminal = dict(prerequisite_passed=True, episodes=statuses, protocol_hash=ph)
    if sessions.get("terminal") != terminal:
        errors.append("terminal mismatch")
    ordered = [records[k] for k in references if k in records]
    if any(b["started_unix"] < a["started_unix"]+a.get("elapsed_seconds", 0) for a,b in zip(ordered, ordered[1:])):
        errors.append("overlapping or out-of-order calls")
    tokens = sum(r.get("response",{}).get("usage",{}).get("completion_tokens",0) for r in ordered)
    if len(records) > study.MAX_CALLS or tokens > study.MAX_CALLS*study.old.CAP or list(root.rglob("*.partial")):
        errors.append("call/token cap exceeded or partial writes")
    return dict(protocol_hash=ph, integrity_errors=errors, calls=len(records), terminal=terminal,
        tokenization_checks=checked, grammar_path_checks=grammar_checked, episodes=readout,
        generated_tokens=tokens, forced_tokens=sum(r.get("boundary",{}).get("forced_output_tokens",0) for r in ordered),
        generation_seconds=sum(r.get("elapsed_seconds",0) for r in ordered),
        peak_memory_gb=max((r.get("peak_memory_gb") or 0 for r in ordered), default=0),
        pairs=paired_readout(sessions),
        scope="three paired stochastic replicates on one selected profile; not population evidence or confirmation",
        timing_caveat="elapsed wall-clock durations may include sleep or suspension; do not assume active compute time")


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

