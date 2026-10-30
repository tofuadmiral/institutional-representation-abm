"""Approved append-only retirement of recovery-v2's NEVER STARTED block1.

A new certificate, not an old closure or a release of incurred costs. Creation
requires actual isolated replay of the sealed original production archive,
byte-equal live old JSON, both locks, process absence, exact authority and every
current ledger entry. No study preparation, inference or launch is provided.
"""
import fcntl
import json
import math
from pathlib import Path
import time

from paper3 import retrospective_recovery_budget_v2 as predecessor
from paper3 import retrospective_recovery_retirement_v2 as original_retirement
from paper3.pivot_b_budget import atomic

PROTOCOL = "f81bc5019d840e7cb4fe147d084a4ad699523f382541f33dd485927c154d64fc"
GROUP = "anticipation-r2-f81bc5019d840e7cb4fe147d"
STAGE = GROUP + "-1"
STAGE_SHA = "044d002f50eb120a0d26711b3a5d1593de705248d39b3b3389b3d477dcc15416"
GROUP_SHA = "ec144d0c9776e648144b7d7192b4f9c3d8be2b80eab816cf1a793434f2a62008"
TERMINAL_SHA = "0cdbd77bb34312cecb959fc70ca65e2426b8a8e204eb4f448cad4ebb2e8c9d60"
CLOSURE_SHA = "b34b5ba32eb3c2e638b3b960921c6ac49f71a9661277af31d51833a18ee57562"
ARCHIVE_SHA = "b1312b3d91053821d9005b4a7e5382e928505fe9621e0d94519359e3a6680f75"
REPORT_SHA = "91601aea398f17fe2a61e8212ab54e2eda344cd8549134ee86759d573ac0351b"
ENTRIES_SHA = "3ea109e20b1291ccad21c886b511d45d98b10e5c46faf58ee1f8e15c33aa7117"
ENTRY_COUNT = 6721
AUTHORIZATION_FILE = "authority_extension_2026_10_16.json"
AUTHORIZATION_SHA = "a7fe6f79cb2f9ef2d98975a917706cbe76714208bbee0f384c7750a280525e11"
DIRECTORY = "resource_stage_abandonments_v1"
RETIRED_CAP = "4.39193944"
OLD_RETIREMENT_SHA = "ac9070f7ac2c0404a8150623a57f48452d05821325f3c5c58ffda1bdd7949028"
RUN = "results/paper3/pivot_b_retrospective_anticipation_recovery_v2"
ARCHIVE = "paper3/data/pivot_b_retrospective_anticipation_recovery_v2_batch0"
inventory = original_retirement.inventory
inventory_sha = original_retirement.inventory_sha
_pid_gone = original_retirement._pid_gone


def old_retirement_pins(root):
    path = Path(root) / original_retirement.DIRECTORY / (original_retirement.STAGE + ".json")
    if not path.exists():
        return {}
    if path.is_symlink() or predecessor._digest(path) != OLD_RETIREMENT_SHA:
        raise ValueError("original retirement pin changed")
    return {original_retirement.STAGE: OLD_RETIREMENT_SHA}


def replay_proof():
    return dict(protocol=PROTOCOL, report_sha256=REPORT_SHA, isolated_report_matched=True,
        network_guard_self_test=True, genuine_qualification_reproduced=True,
        original_retirement_report_reproduced=True, publication_evidence=False,
        archive_sha256=ARCHIVE_SHA)


def certificate(entries, stamp):
    return dict(format="paper3-resource-unstarted-block-retirement-v1", stage=STAGE,
        stage_sha256=STAGE_SHA, group_sha256=GROUP_SHA, old_protocol=PROTOCOL,
        terminal_block0_sha256=TERMINAL_SHA, closure_block0_sha256=CLOSURE_SHA,
        original_archive_sha256=ARCHIVE_SHA, recomputed_original_report_sha256=REPORT_SHA,
        human_authorization_sha256=AUTHORIZATION_SHA, original_entries=entries,
        original_entries_sha256=ENTRIES_SHA, retired_unused_cap_usd=RETIRED_CAP,
        actual_isolated_replay=replay_proof(), incurred_reservations_released=False,
        old_run_reopened=False, old_files_modified=False, launch_authorized=False,
        retired_at_unix=stamp)


def authorization(root):
    path = Path(root) / AUTHORIZATION_FILE
    if path.is_symlink() or predecessor._digest(path) != AUTHORIZATION_SHA:
        raise ValueError("direct total19/oldB1-only authorization changed")


def verify_certificate(root, record):
    root = Path(root)
    authorization(root)
    stamp = record["retired_at_unix"]
    if type(stamp) not in (float, int) or not math.isfinite(stamp) or stamp < 0:
        raise ValueError("finite retirement timestamp required")
    entries = record["original_entries"]
    if (json.dumps(record, sort_keys=True) != json.dumps(certificate(entries, stamp), sort_keys=True)
        or type(entries) is not dict or len(entries) != ENTRY_COUNT or inventory_sha(entries) != ENTRIES_SHA):
        raise ValueError("retirement authority/inventory scope changed")
    for name, digest in entries.items():
        if predecessor._digest(root / "entries" / name) != digest:
            raise ValueError("retirement changed an incurred reservation")
    for path, digest in (
        (root / predecessor.STAGES / (STAGE + ".json"), STAGE_SHA),
        (root / predecessor.GROUPS / (GROUP + ".json"), GROUP_SHA),
        (root / predecessor.CLOSURES / (GROUP + "-0.json"), CLOSURE_SHA)):
        if path.is_symlink() or predecessor._digest(path) != digest:
            raise ValueError("original allocation/closure evidence changed")
    if (root / predecessor.CLOSURES / (STAGE + ".json")).exists():
        raise ValueError("unstarted block cannot acquire a terminal closure")
    if any(r["stage"] == STAGE for r in predecessor.RecoveryLedger(
            root, retirement_pins=old_retirement_pins(root))._entries()):
        raise ValueError("attempted block cannot be retired as unstarted")
    return record


def verify_record(root, expected_sha256):
    root = Path(root)
    predecessor._sha(expected_sha256)
    path = root / DIRECTORY / (STAGE + ".json")
    if path.is_symlink() or predecessor._digest(path) != expected_sha256:
        raise ValueError("pinned retirement certificate changed")
    return verify_certificate(root, json.loads(path.read_text()))


def _old_state(repo, root, ledger_root):
    authorization(ledger_root)
    manifest = json.loads((root / "manifest.json").read_text())
    original_retirement.legacy._sha(PROTOCOL)
    from experiments import paper3_transport_diagnostic as t
    if t.sha(t.canonical(manifest).encode()) != PROTOCOL:
        raise ValueError("old manifest changed")
    for name, digest in manifest["sources"].items():
        if predecessor._digest(repo / name) != digest:
            raise ValueError("old frozen source changed")
    _pid_gone(json.loads((root / "sessions/start.json").read_text())["pid"])
    if any(p.exists() for p in (root / "block-1", root / "sessions/block-1-start.json",
                                root / "sessions/block-1-terminal.json")):
        raise ValueError("old block1 state exists; no unstarted retirement")
    if predecessor._digest(root / "sessions/block-0-terminal.json") != TERMINAL_SHA:
        raise ValueError("original terminal changed")


def retire(repo):
    """ONE approved bookkeeping action; never reopens/prepares/launches a study."""
    from paper3 import retrospective_recovery_archive_v2 as archive
    repo = Path(repo).resolve(strict=True)
    root, ledger_root = repo / RUN, repo / "results/paper3/pivot_b_budget"
    target = ledger_root / DIRECTORY / (STAGE + ".json")
    if target.exists():
        raise ValueError("already retired; no repeat")
    with (root / "coordinator.lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _old_state(repo, root, ledger_root)
        zipped, directory = repo / (ARCHIVE + ".zip"), repo / ARCHIVE
        if predecessor._digest(zipped) != ARCHIVE_SHA:
            raise ValueError("original archive changed")
        metadata = archive.portable.verify_bundle(directory, PROTOCOL)
        if metadata["report_sha256"] != REPORT_SHA:
            raise ValueError("original archived report changed")
        # The production old audit requires its historical ledger, not current
        # unrelated gate spending. Compare every old JSON then replay its actual
        # sealed code/ledger in a fresh isolated interpreter, never a cached flag.
        expected = {name[4:]: archive.portable.safe(directory, name).read_bytes()
                    for name in metadata["files"] if name.startswith("run/")}
        if archive._json_files(root) != expected:
            raise ValueError("live old run differs from sealed original JSON")
        proof = archive.isolated_certificate(directory, zipped, PROTOCOL)
        if proof != replay_proof():
            raise ValueError("actual full old isolated replay did not reproduce")
        ledger = predecessor.RecoveryLedger(ledger_root,
            retirement_pins=old_retirement_pins(ledger_root))
        with ledger.locked():
            _old_state(repo, root, ledger_root)
            entries = inventory(ledger_root)
            if inventory_sha(entries) != ENTRIES_SHA or len(entries) != ENTRY_COUNT:
                raise ValueError("financial inventory changed; no retrospective release")
            if target.exists():
                raise ValueError("retirement already exists; no repeat")
            record = certificate(entries, time.time())
            verify_certificate(ledger_root, record)
            (ledger_root / DIRECTORY).mkdir(exist_ok=True)
            atomic(target, record)
            digest = predecessor._digest(target)
            verify_record(ledger_root, digest)
            return dict(stage=STAGE, certificate_sha256=digest,
                retired_unused_cap_usd=RETIRED_CAP, incurred_reservations_released=False,
                old_files_modified=False, launch_authorized=False, actual_isolated_replay=proof)
