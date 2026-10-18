"""Offline exact replay/configuration inheritance of the passed late-context gate.

This proves only a prerequisite. It does not allocate, transmit, assert reliable
480-action execution, or change the economic institution or accepted actions.
"""
from pathlib import Path
import zipfile

from experiments import paper3_retrospective_late_context_bounded_gate_v1 as gate
from paper3 import retrospective_qualification_inheritance as original
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_score_ledger_budget as wire

PROTOCOL = "28339d0a5b7019567a4b69f30e6d4b3cda4c858bba819e4c1ac7316ee26143e7"
ARCHIVE_SHA = "87697c9d3c45de43d2a8f88557254c244cbf1ff6a28a7f396930dcac88dfe7c1"
REPORT_SHA = "4d11ab795ec533dfeb5af0d0160093341d7fd9ee8f2118cd9784b97b35ea6fb4"


def prove(directory, archive, assignments):
    directory, archive = Path(directory), Path(archive)
    helper = gate.archive_helper()
    institution.require(not directory.is_symlink() and not archive.is_symlink() and
        original.file_sha(archive) == ARCHIVE_SHA, "late gate archive changed")
    metadata = helper.verify_bundle(directory, PROTOCOL)
    institution.require(metadata["experiment_family"] == gate.STAGE, "late gate family changed")
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        institution.require(len(names) == len(set(names)) and
            set(names) == set(metadata["files"]) | {"bundle.json"}, "late gate ZIP inventory")
        for name in names:
            institution.require(zipped.read(name) == helper.safe(directory, name).read_bytes(),
                                "late gate extraction differs from ZIP")
    # This is an immutable, fully verified historical snapshot, not the live
    # research ledger. The public audit wrapper creates ledger.lock and would
    # invalidate the very bundle inventory just verified above. Recompute the
    # unchanged production audit without acquiring a writable snapshot lock,
    # exactly as the original qualification-inheritance adapter does.
    report = gate._audit_locked(directory / "run", directory / "ledger")
    institution.require(gate.t.sha(gate.t.canonical(report).encode()) == REPORT_SHA and
        gate.t.canonical(report) == gate.t.canonical(gate.t.load(directory / "expected_report.json"))
        and report["gate_passed"] is True and len(report["assignments"]) == 16,
        "entire passed late gate audit not reproduced")
    reference = {}
    for item in gate.cases():
        phase = next(r["stage"] for r in gate.qualification.cases()
                     if r["id"] == item["context"]["case_id"])
        reference.setdefault(phase, item["request"])
    checked = []
    for assigned in assignments:
        def ask(actor, identity, term, phase, context, index):
            request = wire.action_request(assigned["game"], assigned["arm"], assigned["seed_base"],
                actor, identity, term, phase, context, index)
            checked.append(original.compare(reference[phase], request, qualified_width=6,
                task_width=len(assigned["game"].utilities[0][0][0]), phase=phase))
            if phase in ("draft", "final"):
                return dict(policy=0, message="")
            if phase == "response":
                return dict(support=False, counter_policy=0, message="")
            return dict(vote=False)
        institution.episode(assigned["game"], assigned["arm"], ask)
    institution.require(len(checked) == 30 * len(assignments) and
        all(c["literal_full_schema_equal"] and c["native_equal"] and c["system_equal"]
            for c in checked), "exact late gate native/schema/system mismatch")
    # Prove that replay itself did not add a lock, bytecode, or other artifact.
    institution.require(helper.verify_bundle(directory, PROTOCOL) == metadata,
                        "late gate snapshot changed during read-only replay")
    return dict(protocol=PROTOCOL, archive_sha256=ARCHIVE_SHA, report_sha256=REPORT_SHA,
        entire_report_recomputed=True, all_sixteen_passed=True, compared_slots=len(checked),
        compared_assignments=len(assignments), native_system_schema_equal=True,
        actual_new_model_calls=0, publication_evidence=False, launch_authorized=False)
