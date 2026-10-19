"""One directly approved unused-block retirement; no inference or run restart."""
import fcntl
import json
import math
from pathlib import Path
import time

from paper3 import retrospective_resource_archive_v1 as original_archive
from paper3 import retrospective_resource_budget_v1 as original_budget
from paper3 import retrospective_resource_retirement_v1 as previous_retirement
from paper3.pivot_b_budget import atomic

PROTOCOL = "c6670ffdf43d14226db7253fb3fc0353e4b42e68952f6d33e55558ea017d5159"
GROUP = "resource-r1-c6670ffdf43d14226db7253f"
STAGE = GROUP + "-1"
STAGE_SHA = "fb332f8c148f0eebc2d4dabe7d512f32f0879b088036193a274130c08ca48db3"
GROUP_SHA = "6a08bfc63398f644ba1677d21dd29574f31f474b7f76264b96e0d6da514b3e2a"
CLOSURE_SHA = "554f79c5531e4d10ed2387b6d5675cf8578d2514f56417a272f86502d1fce6e5"
TERMINAL_SHA = "113d9948afb4f81a7e90af114269c01651cfbc57130b1dee87e8391e2b5bb46b"
ARCHIVE_SHA = "e37ea582b07fa546c82b4c80b1774405009ab27fa4c3c055e19dcf7377c85bfb"
REPORT_SHA = "1d217eaf647bb7e49e74d73d391739db0a66abae1b5a8229925e92024ba04dff"
ENTRIES_SHA = "5941f7f3e1fa6b4c8ccb1fb6bd614edc921e28be8fbaea7fc8c61224ae105bc7"
ENTRY_COUNT = 6787
AUTHORIZATION_FILE = "deepinfra_migration_authorization_2026_10_19.json"
AUTHORIZATION_SHA = "5cf99d7a53f8aac89db1588d4da942df65c895d9cbb18e1a51aae274832138c5"
PREVIOUS_RETIREMENT_SHA = "04c8df6dfbf089084d84a46f8b738076f790b2377009f7ddab285f9e97b76778"
DIRECTORY = "deepinfra_stage_abandonments_v1"
RETIRED_CAP = "4.39399734"
RUN = "results/paper3/pivot_b_retrospective_resource_pilot_v1"
ARCHIVE = "paper3/data/pivot_b_retrospective_resource_pilot_v1_batch0"
inventory = previous_retirement.inventory
inventory_sha = previous_retirement.inventory_sha
digest = original_budget._digest


def authorization(root):
    path = Path(root) / AUTHORIZATION_FILE
    if path.is_symlink() or digest(path) != AUTHORIZATION_SHA:
        raise ValueError("new direct provider/unused-block authority changed")
    record = json.loads(path.read_text())
    if (record["retire_only_unstarted_stage"] != STAGE or
        record["retire_only_unused_cap_usd"] != RETIRED_CAP or
        record["incurred_pending_uncertified_reservations_released"] is not False or
        record["old_run_reopen_authorized"] is not False or
        record["total_authority_usd"] != "19.00"):
        raise ValueError("retirement scope changed")


def replay_proof():
    return dict(protocol=PROTOCOL, archive_sha256=ARCHIVE_SHA, report_sha256=REPORT_SHA,
        isolated_report_matched=True, network_guard_self_test=True,
        genuine_qualification_reproduced=True, original_retirement_report_reproduced=True,
        publication_evidence=False)


def certificate(entries, stamp):
    return dict(format="paper3-deepinfra-unstarted-block-retirement-v1", stage=STAGE,
        stage_sha256=STAGE_SHA, group_sha256=GROUP_SHA, old_protocol=PROTOCOL,
        terminal_block0_sha256=TERMINAL_SHA, closure_block0_sha256=CLOSURE_SHA,
        original_archive_sha256=ARCHIVE_SHA, recomputed_original_report_sha256=REPORT_SHA,
        human_authorization_sha256=AUTHORIZATION_SHA, original_entries=entries,
        original_entries_sha256=ENTRIES_SHA, retired_unused_cap_usd=RETIRED_CAP,
        actual_isolated_replay=replay_proof(), incurred_reservations_released=False,
        old_run_reopened=False, old_files_modified=False, launch_authorized=False,
        retired_at_unix=stamp)


def verify_certificate(root, record):
    root = Path(root)
    authorization(root)
    stamp = record["retired_at_unix"]
    entries = record["original_entries"]
    if (type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0 or
        type(entries) is not dict or len(entries) != ENTRY_COUNT or
        inventory_sha(entries) != ENTRIES_SHA or
        record != certificate(entries, stamp)):
        raise ValueError("retirement certificate/inventory changed")
    for name, expected in entries.items():
        if Path(name).name != name or digest(root / "entries" / name) != expected:
            raise ValueError("incurred entry changed; never release uncertain cost")
    for folder, name, expected in (
        (original_budget.STAGES, STAGE, STAGE_SHA),
        (original_budget.GROUPS, GROUP, GROUP_SHA),
        (original_budget.CLOSURES, GROUP + "-0", CLOSURE_SHA)):
        path = root / folder / (name + ".json")
        if path.is_symlink() or digest(path) != expected:
            raise ValueError("original allocation/closure changed")
    if (root / original_budget.CLOSURES / (STAGE + ".json")).exists():
        raise ValueError("unstarted block cannot have a terminal closure")
    for entry in original_budget.RecoveryLedger(root, retirement_pins={
            previous_retirement.STAGE: PREVIOUS_RETIREMENT_SHA})._entries():
        if entry["stage"] == STAGE:
            raise ValueError("attempted block cannot be retired as unstarted")
    return record


def verify_record(root, expected_sha256):
    original_budget._sha(expected_sha256)
    path = Path(root) / DIRECTORY / (STAGE + ".json")
    if path.is_symlink() or digest(path) != expected_sha256:
        raise ValueError("external retirement certificate pin changed")
    return verify_certificate(root, json.loads(path.read_text()))


def _old_state(repo, root, ledger):
    authorization(ledger)
    original_archive.freeze.verify(root, repo, PROTOCOL)
    for name in ("block-1", "sessions/block-1-start.json", "sessions/block-1-terminal.json"):
        if (root / name).exists():
            raise ValueError("second block started or ambiguous")
    if digest(root / "sessions/block-0-terminal.json") != TERMINAL_SHA:
        raise ValueError("original terminal changed")
    previous_retirement._pid_gone(json.loads((root / "sessions/start.json").read_text())["pid"])


def retire(repo):
    """Execute once only after actual old isolated replay; preserve every charge."""
    repo = Path(repo).resolve(strict=True)
    root, ledger_root = repo / RUN, repo / "results/paper3/pivot_b_budget"
    target = ledger_root / DIRECTORY / (STAGE + ".json")
    if target.exists():
        raise ValueError("already retired; never repeat")
    with (root / "coordinator.lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _old_state(repo, root, ledger_root)
        directory, zipped = repo / ARCHIVE, repo / (ARCHIVE + ".zip")
        if digest(zipped) != ARCHIVE_SHA:
            raise ValueError("sealed original ZIP changed")
        metadata = original_archive.portable.verify_bundle(directory, PROTOCOL)
        expected = {name[4:]: original_archive.portable.safe(directory, name).read_bytes()
            for name in metadata["files"] if name.startswith("run/")}
        if metadata["report_sha256"] != REPORT_SHA or original_archive._json_files(root) != expected:
            raise ValueError("live original run differs from sealed evidence")
        proof = original_archive.isolated_certificate(directory, zipped, PROTOCOL)
        if proof != replay_proof():
            raise ValueError("actual complete isolated replay failed")
        ledger = original_budget.RecoveryLedger(ledger_root, retirement_pins={
            previous_retirement.STAGE: PREVIOUS_RETIREMENT_SHA})
        with ledger.locked():
            _old_state(repo, root, ledger_root)
            entries = inventory(ledger_root)
            if len(entries) != ENTRY_COUNT or inventory_sha(entries) != ENTRIES_SHA or target.exists():
                raise ValueError("baseline changed or retirement already exists")
            record = certificate(entries, time.time())
            verify_certificate(ledger_root, record)
            target.parent.mkdir(exist_ok=True)
            atomic(target, record)
            sha = digest(target)
            verify_record(ledger_root, sha)
            return dict(certificate_sha256=sha, retired_unused_cap_usd=RETIRED_CAP,
                original_entries_unchanged=ENTRY_COUNT, incurred_reservations_released=False,
                old_run_reopened=False, old_files_modified=False, actual_isolated_replay=proof)
