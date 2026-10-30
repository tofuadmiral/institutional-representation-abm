"""Physical-first replay of the unchanged institution under bounded transport.

Reuses the original lossless journal codec/chain, never rewrites old journals.
The only extra terminal disposition is a genuinely unadmitted action after a
deadline/global stop. That remains missing, not a fabricated vote or response.
"""
from copy import deepcopy
import json

from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_deepinfra_execution_v1 as execution
from paper3 import retrospective_deepinfra_failure_v1 as failure
from paper3 import retrospective_deepinfra_calls_v2 as physical
from paper3 import retrospective_deepinfra_budget_v2 as budget


def replay(root, assignments, protocol, *, verify, transport_report):
    saved = journal.inspect(root, assignments, protocol, verify=verify)
    journal.institution.require(saved["complete"], "incomplete journal; never resume")
    journal.institution.require(transport_report["protocol"] == protocol, "physical audit protocol")
    by_id = {r["case"]["id"]: r for r in transport_report["logicals"]}
    journal.institution.require(len(by_id) == len(transport_report["logicals"]), "duplicate audited logicals")
    used, emitted = set(), []
    def respond(request, key):
        journal.institution.require(key in by_id and key not in used, "missing/reused logical evidence")
        record = by_id[key]
        journal.institution.require(journal.canonical(journal.encode(record["case"]["request"])) ==
            journal.canonical(journal.encode(request)), "replayed request differs from physical audit")
        used.add(key)
        if record["status"] == "not_started":
            journal.institution.require(not record["attempts"] and record["returned_evidence"] is None,
                                        "unadmitted action cannot contain physical evidence")
            return dict(id=key, status="not_started", instrument_error="global_stop")
        journal.institution.require(record["status"] in ("recorded_valid", "content_failed", "resource_failed", "unsafe_failed") and
            record["returned_evidence"] is not None, "unfinished physical/logical evidence")
        return deepcopy(record["returned_evidence"])
    def persist(event):
        index = len(emitted)
        journal.institution.require(index < len(saved["events"]) and
            journal.canonical(journal.encode(event)) == journal.canonical(journal.encode(saved["events"][index])),
            "recomputed journal event/report differs")
        emitted.append(event["event"])
    result = execution.execute(assignments, respond=respond,
        verify=lambda: journal._guard(verify, protocol), persist=persist)
    journal.institution.require(len(emitted) == len(saved["events"]) and used == set(by_id),
                                "unmatched journal/physical evidence")
    return dict(protocol=protocol, report=result, events_replayed=len(emitted),
        journal_chain_sha256=saved["chain_sha256"], physical_accounted_usd=transport_report["accounted_usd"],
        allocation_authorized=False, publication_evidence=False,
        limitation="Exact bounded-transport controller replay; missing actions remain missing. "
                   "Not qualification, launch authority or a scientific result.")


def audit(root, ledger_root, stage, assignments, protocol, *, verify):
    journal._guard(verify, protocol)
    journal.start_record(assignments, protocol)
    slots = {a["id"] + f"-{i:02d}": a for a in assignments for i in range(30)}
    def classify(row, case):
        key = case["context"]["logical_id"]
        journal.institution.require(key in slots, "physical slot not assigned")
        payload = json.loads(case["request"]["messages"][1]["content"])
        journal.institution.require(payload["stage"] == case["context"]["stage"], "assigned physical phase")
        return failure.classify(row, case["request"], slots[key]["game"], payload["stage"])
    transport = physical.audit(root, ledger_root, stage, protocol, classify,
        maximum_logical=30 * len(assignments), ledger_factory=budget.RecoveryLedger)
    journal._guard(verify, protocol)
    result = replay(root, assignments, protocol, verify=verify, transport_report=transport)
    result["physical_reissues"] = transport["reissues"]
    result["physical_recovery_events"] = transport["recovery_events"]
    result["physical_attempts"] = len(transport["physical_reports"])
    return result
