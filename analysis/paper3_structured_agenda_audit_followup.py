"""Post-run verifier for schema serialization order; original frozen audit retained.

PilotStore sorts JSON object keys on disk. LLGuidance's compiled grammar uses
the insertion order of schema properties, although JSON Schema semantics do not.
Recover the actual schema order by replaying the unchanged frozen request builder,
not by reordering responses or editing saved records. No model weights or calls.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
import paper3_structured_agenda_audit as frozen
from experiments import paper3_bonsai_structured_agenda as study
from paper3.audit_runtime import digest


class SchemaReplay(frozen.Replay):
    def __init__(self, protocol, records, session):
        super().__init__(protocol, records, session, None, None)
        self.schemas = {}

    def call(self, case, base):
        key, row = super().call(case, base)
        if key in self.schemas:
            raise ValueError("duplicate request in schema reconstruction")
        self.schemas[key] = copy.deepcopy(case["schema"])
        return key, row


def collect_schemas(protocol, ph, records, sessions):
    schemas = {}
    for spec in protocol["episodes"]:
        saved = sessions[spec["name"]]
        replay = SchemaReplay(protocol, records, saved)
        expected = dict(study.run_one(replay, None, spec), protocol_hash=ph)
        if saved != expected or replay.position != len(saved["call_keys"]):
            raise ValueError("episode reconstruction differs")
        if set(schemas) & set(replay.schemas):
            raise ValueError("duplicate schema across episodes")
        schemas.update(replay.schemas)
    if set(schemas) != set(records):
        raise ValueError("schema reconstruction does not cover all records")
    return schemas


def grammar_error(row, schema, tokenizer, grammar_tokenizer, eos):
    import llguidance as llg
    try:
        close = tokenizer.encode("</think>", add_special_tokens=False)[-1]
        suffix = row["generated_token_ids"][row["generated_token_ids"].index(close)+1:]
        normal = row["response"]["choices"][0]["finish_reason"] == "stop"
        grammar = llg.JsonCompiler(separators=(", ", ": "), whitespace_pattern="").compile(json.dumps(schema))
        matcher = llg.LLMatcher(grammar_tokenizer, grammar, log_level=0)
        if not matcher.consume_tokens(suffix[:-1] if normal else suffix) or matcher.is_error():
            return "tokens rejected: " + matcher.get_error().splitlines()[0]
        if normal:
            if suffix[-1] not in eos or not matcher.is_accepting():
                return "missing EOS or incomplete grammar"
            if not matcher.consume_token(suffix[-1]) or matcher.is_error():
                return "EOS rejected"
        return None
    except (ValueError, KeyError, IndexError) as exc:
        return type(exc).__name__ + ": " + str(exc)


def reconcile(original, recorded_failures, recovered_failures, count):
    """Resolve only independently reproduced ordering failures, never other errors."""
    explained = {"raw " + k + ": " for k in recorded_failures if k not in recovered_failures}
    errors = [e for e in original["integrity_errors"] if e not in explained]
    if not explained.issubset(set(original["integrity_errors"])):
        errors.append("reproduced ordering failure missing from frozen audit")
    if original["tokenization_checks"] != count:
        errors.append("frozen token/controller/phase checks did not cover every record")
    if original["grammar_path_checks"] != count-len(recorded_failures):
        errors.append("frozen grammar failure count does not reproduce")
    errors.extend("recovered grammar " + k + ": " + v for k,v in recovered_failures.items())
    return errors


def audit(root):
    # This unchanged auditor still verifies frozen sources, source snapshots,
    # runtime/model metadata, all requests/actions/outcomes, tokenization,
    # controller and mask phase traces, accounting, caps and chronology.
    original = frozen.audit(root)
    manifest = json.loads((root / "manifest.json").read_text())
    protocol, ph = manifest["protocol"], digest(manifest)
    records = {p.stem:json.loads(p.read_text()) for p in (root / "calls").glob("*.json")}
    sessions = {p.stem:json.loads(p.read_text()) for p in (root / "sessions").glob("*.json")}
    schemas = collect_schemas(protocol, ph, records, sessions)
    from transformers import AutoTokenizer
    import llguidance.hf
    tokenizer = AutoTokenizer.from_pretrained(protocol["model"], local_files_only=True)
    grammar_tokenizer = llguidance.hf.from_tokenizer(tokenizer)
    config = json.loads((Path(protocol["model"]) / "generation_config.json").read_text())
    eos = config.get("eos_token_id", tokenizer.eos_token_id)
    eos = set(eos if isinstance(eos, list) else [eos])
    stored_bad, recovered_bad, changed = {}, {}, []
    for key, row in records.items():
        stored, recovered = row["request"]["response_schema"], schemas[key]
        if stored != recovered:
            raise ValueError("schema semantics changed: " + key)
        if json.dumps(stored) != json.dumps(recovered):
            changed.append(key)
        error = grammar_error(row, stored, tokenizer, grammar_tokenizer, eos)
        if error:
            stored_bad[key] = error
        error = grammar_error(row, recovered, tokenizer, grammar_tokenizer, eos)
        if error:
            recovered_bad[key] = error
    errors = reconcile(original, stored_bad, recovered_bad, len(records))
    if not set(stored_bad).issubset(changed):
        errors.append("a rejected stored schema has no serialization-order difference")
    sources = [Path(__file__).resolve(), ROOT / "tests/test_paper3_structured_agenda_audit_followup.py"]
    provenance = {str(p.relative_to(ROOT)):dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                  source=p.read_text()) for p in sources}
    result = {k:v for k,v in original.items() if k != "integrity_errors"}
    result.update(integrity_errors=errors, grammar_path_checks=len(records)-len(recovered_bad),
        frozen_audit=original,
        postrun_verification=dict(role="post-run verification only, not part of the earlier experiment freeze",
            defect="sorted JSON serialization changes LLGuidance property order; frozen auditor used saved rather than source-reconstructed runtime schema order",
            record_or_experiment_changes=False, no_model_calls=True,
            reconstructed_schemas=len(schemas), semantically_identical_schemas=len(schemas),
            recorded_order_grammar_failures=stored_bad, runtime_order_grammar_failures=recovered_bad,
            original_frozen_audit_retained=True, sources=provenance),
        timing_caveat="generation_seconds contains recorded wall-clock call durations including macOS sleep and a SIGSTOP/SIGCONT battery-protection pause; not pure compute time")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.archive:
        from experiments.paper3_archive_agenda import archive
        result = archive(args.root, args.archive, report_fn=audit)
        print(json.dumps({k:v for k,v in result.items() if k != "report"}, indent=2))
    else:
        report = audit(args.root)
        print(json.dumps({k:v for k,v in report.items() if k not in ("episodes", "frozen_audit", "postrun_verification")}, indent=2))
        print("REPRODUCED_SAVED_ORDER_FAILURES",len(report["postrun_verification"]["recorded_order_grammar_failures"]))
        sys.exit(bool(report["integrity_errors"]))
