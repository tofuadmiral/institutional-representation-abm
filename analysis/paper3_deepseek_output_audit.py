"""Read-only exact requests, actions, returned reasoning observations and cost replay."""
from __future__ import annotations
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import paper3_deepseek_output_diagnostic as study
from paper3.audit_runtime import digest


def audit(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    ph = digest(manifest)
    protocol, sources = study.prepare()
    if protocol != manifest["protocol"] or set(map(str,sources)) != set(manifest["sources"]):
        raise ValueError("protocol/source set mismatch")
    snapshots = json.loads((root / "sources.json").read_text())
    for path, sha in manifest["sources"].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha:
            raise ValueError("frozen source changed: "+path)
        if hashlib.sha256(snapshots[str(Path(path).relative_to(ROOT))].encode()).hexdigest() != sha:
            raise ValueError("source snapshot mismatch: "+path)
    records = {p.stem:json.loads(p.read_text()) for p in (root / "calls").glob("*.json")}
    sessions = {p.stem:json.loads(p.read_text()) for p in (root / "sessions").glob("*.json")}
    errors, checks, previous, refs = [], [], [], []
    known, halt, certified = {"terminal"}, None, 0
    for case in protocol["cases"]:
        if halt:
            break
        request = study.request_for(case)
        bound, reserve = study.base.reserve_for(request)
        try:
            study.base.budget_guard(previous, "gate", reserve)
        except study.base.Halt as exc:
            halt = str(exc)
            break
        try:
            name = case["name"]
            saved = sessions[name]
            known.add(name)
            key = digest(dict(request=request, phase="gate", protocol=ph))
            row = records[key]
            assert saved["call_keys"] == [key]
            assert row["protocol_hash"] == ph and row["phase"] == "gate" and row["status"] == "recorded"
            assert row["request"] == request and row["request_text"] == study.base.encoded_request(request)
            assert row["input_token_bound"] == bound and Decimal(row["reserved_usd"]) == reserve
            try:
                raw = json.loads(row["response_text"])
            except ValueError:
                raw = {}
            assert raw == row["response"]
            try:
                cost = study.base.accounting(row)
            except (ValueError, KeyError, TypeError, ArithmeticError):
                assert row.get("accounting_error") and "verified_cost_usd" not in row
                halt = "transport/accounting/routing failure"
            else:
                assert row["verified_cost_usd"] == str(cost) and not row.get("accounting_error")
                certified += 1
            expected = dict(study.score(row, case), name=name, fixture=case["fixture"], mode=case["mode"],
                call_keys=[key], protocol_hash=ph)
            assert saved == expected
            if previous:
                assert row["started_unix"] >= previous[-1]["started_unix"]+previous[-1]["elapsed_seconds"]
            assert row["elapsed_seconds"] >= 0
            previous.append(row)
            refs.append(key)
            checks.append(saved)
        except (AssertionError, KeyError, TypeError, ValueError) as exc:
            errors.append(case["name"]+": "+type(exc).__name__+": "+str(exc))
    expected_terminal = study.terminal(checks, list(records.values()), ph, halt)
    if sessions.get("terminal") != expected_terminal:
        errors.append("terminal mismatch")
    if set(sessions) != known or set(refs) != set(records) or len(refs) != len(set(refs)):
        errors.append("extra/missing sessions or calls")
    if len(records) > 16 or Decimal(expected_terminal["budget"]["accounted_usd"]) > Decimal("0.10"):
        errors.append("budget exceeded")
    if list(root.rglob("*.partial")):
        errors.append("partial writes remain")
    pairs = []
    for i in range(8):
        modes = {mode:sessions.get(f"selector-{i}-{mode}") for mode in study.MODES}
        pairs.append(dict(fixture=i, complete=all(modes.values()), modes={mode:
            {k:r[k] for k in ("valid", "exact", "reply", "error", "reasoning_observation") if k in r}
            for mode,r in modes.items() if r}))
    return dict(protocol_hash=ph, integrity_errors=errors, calls=len(records), certified_cost_records=certified,
        terminal=expected_terminal, pairs=pairs,
        scope="selected eight private fixtures, one sample per mode; not a competence gate or institutional effect; provider internals unverified")


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
