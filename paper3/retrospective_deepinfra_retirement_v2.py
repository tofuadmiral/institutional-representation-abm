"""Approved unused-only retirement using the genuine completed sealed export.

No old run, response or charge is rewritten. The old export actually executed
its isolated replay; this operation checks that exact proof and its sealed bytes
instead of rerunning an old scientific study or inventing a new pass.
"""
import fcntl
import json
import math
from pathlib import Path
import time

from paper3 import retrospective_deepinfra_archive_v1 as previous_archive
from paper3 import retrospective_deepinfra_budget_v1 as previous_budget
from paper3 import retrospective_deepinfra_freeze_v1 as previous_freeze
from paper3 import retrospective_deepinfra_retirement_v1 as previous_retirement
from paper3.pivot_b_budget import atomic

PROTOCOL = "75f544d166edb84c835c19f720dc8d2fda8778c8793ba63b2ee8e0d54a6ed60a"
RUN = "results/paper3/pivot_b_retrospective_deepinfra_pilot_v1"
ARCHIVE = "paper3/data/pivot_b_retrospective_deepinfra_pilot_v1_batch0"
GROUP = "deepinfra-r1-75f544d166edb84c835c19f7"
STAGE = GROUP + "-1"
STAGE_SHA = "e5c4798b9680212ee2a8c1a576f447418e7dbf4c2e4993eb7b820c53681fc955"
GROUP_SHA = "05df5a1dcf9a4c6a7a39ea6085cc1e919cd4610fff9d54dcd479a19770bb7ac0"
CLOSURE_SHA = "bd7ae684fbaa31402ffb0f606b40f6a6cf729ae93bbc3e2d55bcf7573ef9342b"
TERMINAL_SHA = "dc1ae950a926b82c5f73533a08ce9dd9760ba2bc02081b8be1aa0c549bb8c22d"
ARCHIVE_SHA = "72871793b208784d5338035efe5f1d6a7cd39cd1e68bd864b30bc79b0e9eb1c1"
REPORT_SHA = "292e223979fda41061096a7b5dc8d3e8f915713fc0dd83c2aad7591505072818"
EXPORT_PROOF = "results/paper3/deepinfra_bounded_pilot_export0_2026_10_20.stdout"
EXPORT_PROOF_SHA = "c8e1c4c91745ef1038a6508d8f35e8cf2abe07804d7fa1f5013f027c88ef59aa"
ENTRY_COUNT = 6910
ENTRIES_SHA = "6eeefdeaf71fe332265374f222445091434560fb69a1739d192338e2c51a8b61"
AUTHORIZATION_FILE = "deepinfra_overload_authorization_2026_10_21.json"
AUTHORIZATION_SHA = "6ef475049920f3c8a5dcf93c3d16958d86143b6753fd04ecd404ff525aba3fbe"
DIRECTORY = "deepinfra_stage_abandonments_v2"
RETIRED_CAP = "4.39135184"
inventory = previous_retirement.inventory
inventory_sha = previous_retirement.inventory_sha
digest = previous_budget._digest


def old_retirement_pins(root):
    return dict(previous_freeze.RETIREMENT_PINS)


def authorization(root):
    path = Path(root) / AUTHORIZATION_FILE
    if path.is_symlink() or digest(path) != AUTHORIZATION_SHA:
        raise ValueError("exact new human authorization changed")
    record = json.loads(path.read_text())
    if not (record["retire_only_unstarted_stage"] == STAGE and
            record["retire_only_unused_cap_usd"] == RETIRED_CAP and
            record["incurred_pending_uncertified_reservations_released"] is False and
            record["old_run_reopen_authorized"] is False and
            record["total_authority_usd"] == "19.30"):
        raise ValueError("approved unused-only scope changed")


def replay_proof():
    return dict(protocol=PROTOCOL, report_sha256=REPORT_SHA,
        isolated_report_matched=True, network_guard_self_test=True,
        retirement_binding_verified=True, inherited_provider_qualification_pass=False,
        publication_evidence=False, archive_sha256=ARCHIVE_SHA)


def certificate(entries, stamp):
    return dict(format="paper3-overload-unused-block-retirement-v2", stage=STAGE,
        stage_sha256=STAGE_SHA, group_sha256=GROUP_SHA, old_protocol=PROTOCOL,
        terminal_block0_sha256=TERMINAL_SHA, closure_block0_sha256=CLOSURE_SHA,
        original_archive_sha256=ARCHIVE_SHA, original_report_sha256=REPORT_SHA,
        genuine_export_proof_sha256=EXPORT_PROOF_SHA, verified_completed_export=replay_proof(),
        human_authorization_sha256=AUTHORIZATION_SHA, original_entries=entries,
        original_entries_sha256=ENTRIES_SHA, retired_unused_cap_usd=RETIRED_CAP,
        incurred_reservations_released=False, old_run_reopened=False,
        old_files_modified=False, launch_authorized=False, retired_at_unix=stamp)


def verify_certificate(root, record):
    root = Path(root)
    authorization(root)
    entries, stamp = record["original_entries"], record["retired_at_unix"]
    if (type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0 or
            type(entries) is not dict or len(entries) != ENTRY_COUNT or
            inventory_sha(entries) != ENTRIES_SHA or record != certificate(entries, stamp)):
        raise ValueError("retirement proof/inventory changed")
    for name, expected in entries.items():
        if Path(name).name != name or digest(root / "entries" / name) != expected:
            raise ValueError("incurred entry changed; never release uncertain costs")
    for folder, name, expected in (
        (previous_budget.STAGES, STAGE, STAGE_SHA),
        (previous_budget.GROUPS, GROUP, GROUP_SHA),
        (previous_budget.CLOSURES, GROUP + "-0", CLOSURE_SHA)):
        path = root / folder / (name + ".json")
        if path.is_symlink() or digest(path) != expected:
            raise ValueError("old allocation/closure changed")
    if (root / previous_budget.CLOSURES / (STAGE + ".json")).exists():
        raise ValueError("unstarted block cannot have a terminal closure")
    rows = previous_budget.RecoveryLedger(root, retirement_pins=old_retirement_pins(root))._entries()
    if any(row["stage"] == STAGE for row in rows):
        raise ValueError("attempted block cannot be retired as unstarted")
    return record


def verify_record(root, expected_sha256):
    previous_budget._sha(expected_sha256)
    path = Path(root) / DIRECTORY / (STAGE + ".json")
    if path.is_symlink() or digest(path) != expected_sha256:
        raise ValueError("retirement external pin changed")
    return verify_certificate(root, json.loads(path.read_text()))


def retire(repo):
    repo = Path(repo).resolve(strict=True)
    root, ledger = repo / RUN, repo / "results/paper3/pivot_b_budget"
    target = ledger / DIRECTORY / (STAGE + ".json")
    if target.exists():
        raise ValueError("already retired; never repeat")
    with (root / "coordinator.lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous_archive.freeze.verify(root, repo, PROTOCOL)
        for name in ("block-1", "sessions/block-1-start.json", "sessions/block-1-terminal.json"):
            if (root / name).exists():
                raise ValueError("old block1 started or ambiguous")
        if digest(root / "sessions/block-0-terminal.json") != TERMINAL_SHA:
            raise ValueError("old terminal changed")
        previous_retirement.previous_retirement._pid_gone(
            json.loads((root / "sessions/start.json").read_text())["pid"])
        proof_path, directory, zipped = repo / EXPORT_PROOF, repo / ARCHIVE, repo / (ARCHIVE + ".zip")
        if digest(proof_path) != EXPORT_PROOF_SHA or digest(zipped) != ARCHIVE_SHA:
            raise ValueError("genuine export proof/sealed ZIP changed")
        proof = previous_archive.journal.decode(json.loads(proof_path.read_text().splitlines()[-1]))
        metadata = previous_archive.portable.verify_bundle(directory, PROTOCOL)
        if proof != replay_proof() or metadata["report_sha256"] != REPORT_SHA:
            raise ValueError("genuine completed replay certificate differs")
        expected = {name[4:]: previous_archive.portable.safe(directory, name).read_bytes()
            for name in metadata["files"] if name.startswith("run/")}
        if previous_archive._json_files(root) != expected:
            raise ValueError("old run differs from genuinely replayed sealed evidence")
        original = previous_budget.RecoveryLedger(ledger, retirement_pins=old_retirement_pins(ledger))
        with original.locked():
            entries = inventory(ledger)
            if len(entries) != ENTRY_COUNT or inventory_sha(entries) != ENTRIES_SHA or target.exists():
                raise ValueError("financial baseline changed or already retired")
            record = certificate(entries, time.time())
            verify_certificate(ledger, record)
            target.parent.mkdir(exist_ok=True)
            atomic(target, record)
            pin = digest(target)
            verify_record(ledger, pin)
            return dict(certificate_sha256=pin, retired_unused_cap_usd=RETIRED_CAP,
                original_entries_verified=ENTRY_COUNT, existing_genuine_replay_verified=True,
                actual_new_model_calls=0, old_run_reopened=False)
