"""Append-only, explicitly approved retirement of ONE unstarted old block.

Never fabricates an old terminal/closure or releases an incurred reservation.
Creation requires the original production audit to reproduce its archived full
report, the old process to be gone, both locks, exact historical pins, and zero
second-block starts/actions. A fresh runner must freeze the returned record pin.
"""
import fcntl
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import time

from paper3 import retrospective_extended_budget as legacy
from paper3.pivot_b_budget import atomic

PROTOCOL = "534a472f1f0670df3a4affb48ff538e14a67862caa235ddfdc8d7b16d1830002"
GROUP = "anticipation-534a472f1f0670df3a4affb4"
STAGE = GROUP + "-1"
STAGE_SHA = "2b8e803c73741b4ee80599d56c839a21e1bcbc809b3d146e77193f7739ad75cc"
GROUP_SHA = "32915dfd18d65d8bfc7a7485f31276e306b8979a39f7a71932203a7b96a36b1a"
TERMINAL_SHA = "c7f260fb1b10eb9b2f61c0c6157a5ea47da7060cc200ff3eb126b2f2b5153018"
CLOSURE_SHA = "d4575dc5a3aa7941c7104148006a5ca82aa4497f7cf6f772d25a8463097c0668"
ARCHIVE_SHA = "2f27ca03dcd72bc365ebf6c705e13b318e9a525c484aad3f4db914b1ca78e27d"
REPORT_SHA = "196cdac5151de98bbace760f63474c13c7dc24bd1e095bde6bfeb1dbd4406146"
ENTRIES_SHA = "7bc008a60f6a8b036f78c7db7a884cd8d2cfe3c977784a73b0a9350e3bd4d4a9"
AUTHORIZATION_FILE = "results/paper3/pivot_b_retrospective_anticipation_recovery_v2_authorization.json"
AUTHORIZATION_SHA = "f00fb0a39a119aefb4c75e642f2393399597422baf221677c0e1969ca5aeb775"
DIRECTORY = "stage_abandonments"
RETIRED_CAP = "3.76458102"


def inventory(ledger_root):
    return {p.name: legacy._digest(p) for p in sorted((Path(ledger_root) / "entries").glob("*.json"))}


def inventory_sha(entries):
    return sha256(json.dumps(entries, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def certificate(entries, retired_at_unix):
    """Construct evidence only; callers cannot obtain live disposition via this."""
    return dict(format="paper3-approved-unstarted-block-retirement-v2", stage=STAGE,
        stage_sha256=STAGE_SHA, group_sha256=GROUP_SHA, old_protocol=PROTOCOL,
        terminal_block0_sha256=TERMINAL_SHA, closure_block0_sha256=CLOSURE_SHA,
        original_archive_sha256=ARCHIVE_SHA, recomputed_original_report_sha256=REPORT_SHA,
        human_authorization_sha256=AUTHORIZATION_SHA, original_entries=entries,
        original_entries_sha256=ENTRIES_SHA, retired_unused_cap_usd=RETIRED_CAP,
        incurred_reservations_released=False, old_run_reopened=False,
        old_files_modified=False, launch_authorized=False, retired_at_unix=retired_at_unix)


def verify_record(ledger_root, expected_sha256):
    """Cheap repeatable financial proof. Full old replay remains an archive duty."""
    ledger_root = Path(ledger_root)
    legacy._sha(expected_sha256)
    path = ledger_root / DIRECTORY / (STAGE + ".json")
    if path.is_symlink() or legacy._digest(path) != expected_sha256:
        raise ValueError("pinned retirement certificate changed")
    record = json.loads(path.read_text())
    return verify_certificate(ledger_root, record)


def verify_certificate(ledger_root, record):
    """Validate all bindings before any append-only certificate is written."""
    ledger_root = Path(ledger_root)
    stamp = record["retired_at_unix"]
    if type(stamp) not in (float, int) or not math.isfinite(stamp) or stamp < 0:
        raise ValueError("finite retirement timestamp required")
    entries = record["original_entries"]
    if (json.dumps(record, sort_keys=True) != json.dumps(certificate(entries, stamp), sort_keys=True) or
            inventory_sha(entries) != ENTRIES_SHA or len(entries) != 6556):
        raise ValueError("retirement authority/inventory scope changed")
    for name, digest in entries.items():
        if legacy._digest(ledger_root / "entries" / name) != digest:
            raise ValueError("retirement changed an original incurred reservation")
    for path, digest in (
        (ledger_root / "stages" / (STAGE + ".json"), STAGE_SHA),
        (ledger_root / "stage_groups" / (GROUP + ".json"), GROUP_SHA),
        (ledger_root / "stage_closures" / (GROUP + "-0.json"), CLOSURE_SHA)):
        if legacy._digest(path) != digest:
            raise ValueError("original allocation/closure evidence changed")
    if (ledger_root / "stage_closures" / (STAGE + ".json")).exists():
        raise ValueError("unstarted block cannot acquire an old terminal closure")
    if any(row["stage"] == STAGE for row in legacy.ExtendedLedger(ledger_root)._entries()):
        raise ValueError("attempted block cannot be retired as unstarted")
    return record


def _pid_gone(pid):
    if type(pid) is not int or pid <= 0:
        raise ValueError("exact original PID required")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    # Permission errors deliberately propagate: inability to inspect is not absence.
    raise ValueError("original process exists; no retirement")


def retire(repo):
    """ONE explicitly scoped bookkeeping action; never prepares/launches a study."""
    from paper3 import retrospective_anticipation_archive as archive
    from paper3 import retrospective_anticipation_coordinator as coordinator
    from paper3 import retrospective_episode_journal as journal
    from paper3 import retrospective_recovery_budget_v2 as extended

    repo = Path(repo).resolve(strict=True)
    root = repo / "results/paper3/pivot_b_retrospective_anticipation_v1"
    ledger_root = repo / "results/paper3/pivot_b_budget"
    target = ledger_root / DIRECTORY / (STAGE + ".json")
    if legacy._digest(repo / AUTHORIZATION_FILE) != AUTHORIZATION_SHA:
        raise ValueError("direct retirement approval changed")
    extended.RecoveryLedger(ledger_root)  # Exact $10->$12->$15->$17 chain.
    if target.exists() or (repo / "results/paper3/pivot_b_retrospective_anticipation_recovery_v2").exists():
        raise ValueError("already retired or successor state exists; no repeat")
    with (root / "coordinator.lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _pid_gone(journal.load(root / "sessions/start.json")["pid"])
        if any(p.exists() for p in (root / "block-1", root / "sessions/block-1-start.json",
                                   root / "sessions/block-1-terminal.json")):
            raise ValueError("old block1 state exists; no unstarted retirement")
        if legacy._digest(root / "sessions/block-0-terminal.json") != TERMINAL_SHA:
            raise ValueError("original terminal changed")
        zipped = repo / "paper3/data/pivot_b_retrospective_anticipation_v1_batch0.zip"
        if legacy._digest(zipped) != ARCHIVE_SHA:
            raise ValueError("original isolated-replayed archive changed")
        report = coordinator.audit(root, repo, ledger_root, PROTOCOL)
        if (archive.report_sha(report) != REPORT_SHA or
                report["blocks"][0]["evidence"]["report"]["global_safety_stop"] is not True or
                report["blocks"][1]["evidence"] is not None):
            raise ValueError("original production audit/terminal not reproduced")
        ledger = extended.RecoveryLedger(ledger_root)
        with ledger.locked():
            entries = inventory(ledger_root)
            if inventory_sha(entries) != ENTRIES_SHA or len(entries) != 6556:
                raise ValueError("financial state changed since approved original checkpoint")
            # Recheck after the expensive production audit, inside both locks.
            _pid_gone(journal.load(root / "sessions/start.json")["pid"])
            if target.exists() or any(p.exists() for p in (root / "block-1",
                root / "sessions/block-1-start.json", root / "sessions/block-1-terminal.json")):
                raise ValueError("ambiguous/concurrent old block or retirement")
            (ledger_root / DIRECTORY).mkdir(exist_ok=True)
            record = certificate(entries, time.time())
            verify_certificate(ledger_root, record)
            atomic(target, record)
            pin = legacy._digest(target)
            verify_record(ledger_root, pin)
            return dict(stage=STAGE, certificate_sha256=pin, retired_unused_cap_usd=RETIRED_CAP,
                incurred_reservations_released=False, old_files_modified=False, launch_authorized=False)
