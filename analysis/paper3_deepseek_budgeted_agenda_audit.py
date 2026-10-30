"""Read-only provenance, spending and exact-decision replay for hosted discovery.

API usage is provider-reported; this cannot inspect provider-internal token paths.
"""
from __future__ import annotations
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import paper3_deepseek_budgeted_agenda as study
from paper3.audit_runtime import digest


class Replay:
    def __init__(self, records, session, ph, previous):
        self.records, self.session, self.ph = records, session, ph
        self.position, self.previous = 0, previous

    def call(self, case, phase):
        request = study.request_for(case)
        _, reserve = study.reserve_for(request)
        if self.position == len(self.session["call_keys"]):
            if self.session.get("unsubmitted_request") != case:
                raise ValueError("missing replay record")
            study.budget_guard(self.previous, phase, reserve)
            raise ValueError("saved pre-request failure did not reproduce")
        key = self.session["call_keys"][self.position]
        row = self.records[key]
        if row["request"] != request or row["request_text"] != study.encoded_request(request):
            raise ValueError("exact request replay mismatch")
        if key != digest(dict(request=request, phase=phase, protocol=self.ph)):
            raise ValueError("request key mismatch")
        study.budget_guard(self.previous, phase, reserve)
        self.previous.append(row)
        self.position += 1
        return key, row


def pairs(sessions):
    result = []
    for seed in study.SEEDS:
        pair = {arm: sessions.get(f"conflict39-s{seed}-{arm}") for arm in ("D", "B")}
        row = dict(seed=seed, completed=all(s and s["status"] == "completed" for s in pair.values()))
        if row["completed"]:
            d, b = pair["D"]["metrics"], pair["B"]["metrics"]
            changes = {r: b["enacted"]["utilities"][r]-d["enacted"]["utilities"][r] for r in study.game.ROLES}
            row.update(outcomes={a: s["resolution"] for a,s in pair.items()},
                locked_proposals={a: s["metrics"]["locked_proposal"]["policy"] for a,s in pair.items()},
                locked_leader_advantage_B_minus_D=b["locked_proposal"]["leader_advantage"]-d["locked_proposal"]["leader_advantage"],
                enacted_mean_regret_B_minus_D=b["enacted"]["mean_regret"]-d["enacted"]["mean_regret"],
                utility_B_minus_D=changes, principals_gaining=sum(v > 0 for v in changes.values()),
                principals_losing=sum(v < 0 for v in changes.values()))
        else:
            row["reason"] = "missing or failed episode; no outcomes imputed"
        result.append(row)
    return result


def audit(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    protocol, ph = manifest["protocol"], digest(manifest)
    rebuilt = study.prepare()[0]
    if protocol != rebuilt:
        raise ValueError("frozen protocol mismatch")
    # Manifest storage sorts object keys. Rebuild original schema insertion order
    # from frozen sources when reproducing the exact serialized request bytes.
    protocol = rebuilt
    snapshots = json.loads((root / "sources.json").read_text())
    for path, sha in manifest["sources"].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha:
            raise ValueError("frozen source changed: "+path)
        if hashlib.sha256(snapshots[str(Path(path).relative_to(ROOT))].encode()).hexdigest() != sha:
            raise ValueError("source snapshot mismatch: "+path)
    records = {p.stem: json.loads(p.read_text()) for p in (root / "calls").glob("*.json")}
    sessions = {p.stem: json.loads(p.read_text()) for p in (root / "sessions").glob("*.json")}
    errors, previous, references, checks, statuses, known_sessions = [], [], [], [], {}, {"terminal"}
    halt, certified = None, 0
    for key,row in records.items():
        try:
            assert row["protocol_hash"] == ph and row["status"] == "recorded"
            assert json.loads(row["request_text"]) == row["request"]
            bound, reserve = study.reserve_for(row["request"])
            assert row["input_token_bound"] == bound and Decimal(row["reserved_usd"]) == reserve
            try:
                raw = json.loads(row["response_text"])
            except ValueError:
                raw = {}
            assert raw == row["response"]
            try:
                cost = study.accounting(row)
                assert row["verified_cost_usd"] == str(cost)
                assert not row.get("accounting_error")
                certified += 1
            except (ValueError, KeyError, TypeError, ArithmeticError):
                assert row.get("accounting_error") and "verified_cost_usd" not in row
        except (AssertionError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
            errors.append("record "+key+": "+str(exc))
    for case in protocol["cases"]:
        name = "gate-"+case["name"]
        if name not in sessions:
            if halt:
                break
            try:
                study.budget_guard(previous, "gate", study.reserve_for(study.request_for(case))[1])
            except study.Halt as exc:
                halt = str(exc)
                break
            errors.append("missing gate without reproduced halt: "+name)
            break
        known_sessions.add(name)
        try:
            saved = sessions[name]
            replay = Replay(records, saved, ph, previous)
            key,row = replay.call(case, "gate")
            references.append(key)
            expected = dict(study.gate_score(row, case), name=name, call_keys=[key], protocol_hash=ph)
            assert saved == expected
            checks.append(saved)
            if row.get("accounting_error"):
                halt = "transport/accounting/routing failure"
                break
        except (AssertionError, ValueError, KeyError, TypeError) as exc:
            errors.append("gate "+name+": "+str(exc))
    passed = len(checks) == 0 and protocol["inherited_gate"]["gate_passed"]
    if passed and not halt:
        for spec in protocol["episodes"]:
            try:
                saved = sessions[spec["name"]]
                known_sessions.add(spec["name"])
                replay = Replay(records, saved, ph, previous)
                expected = dict(study.run_one(replay, spec), protocol_hash=ph)
                assert saved == expected and replay.position == len(saved["call_keys"])
                references.extend(saved["call_keys"])
                statuses[spec["name"]] = saved["status"]
                if any(records[k].get("accounting_error") for k in saved["call_keys"]):
                    halt = "transport/accounting/routing failure"
                elif saved.get("unsubmitted_request") is not None:
                    halt = saved["error"]
                if halt:
                    break
            except (AssertionError, ValueError, KeyError, TypeError) as exc:
                errors.append("episode "+spec["name"]+": "+str(exc))
    budgets = {p:dict(calls=study.ledger(list(records.values()), p)[0],
                accounted_usd=str(study.ledger(list(records.values()), p)[1])) for p in study.LIMITS}
    terminal = dict(protocol_hash=ph, gate_passed=passed, checks=len(checks),
        gate_reused_from=protocol["inherited_gate_protocol"],
        valid=sum(r["valid"] for r in checks), exact=sum(r["exact"] is True for r in checks),
        episodes=statuses, halt=halt, budgets=budgets)
    if sessions.get("terminal") != terminal:
        errors.append("terminal mismatch")
    if set(sessions) != known_sessions:
        errors.append("extra or missing sessions")
    if len(references) != len(set(references)) or set(references) != set(records):
        errors.append("unattached, duplicate or missing calls")
    if any(b["started_unix"] < a["started_unix"]+a["elapsed_seconds"] for a,b in zip(previous, previous[1:])):
        errors.append("overlapping or out-of-order calls")
    for phase,(cap,cost) in study.LIMITS.items():
        if budgets[phase]["calls"] > cap or Decimal(budgets[phase]["accounted_usd"]) > cost:
            errors.append("phase budget exceeded: "+phase)
    if list(root.rglob("*.partial")):
        errors.append("partial writes remain")
    return dict(protocol_hash=ph, integrity_errors=errors, calls=len(records),
        certified_cost_records=certified, terminal=terminal, pairs=pairs(sessions),
        episodes={s: {k:sessions[s][k] for k in ("status", "resolution", "metrics", "replay", "ratification_consistency", "error") if k in sessions[s]} for s in statuses},
        total_accounted_usd=str(sum((Decimal(b["accounted_usd"]) for b in budgets.values()), Decimal(0))),
        provider_reported_prompt_tokens=sum(r.get("response",{}).get("usage",{}).get("prompt_tokens",0) for r in records.values() if isinstance(r.get("response"),dict)),
        provider_reported_completion_tokens=sum(r.get("response",{}).get("usage",{}).get("completion_tokens",0) for r in records.values() if isinstance(r.get("response"),dict)),
        scope="single selected profile; within-hosted-model discovery only; API internals and weights not independently verified")


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

