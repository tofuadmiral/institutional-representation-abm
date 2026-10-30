"""Offline portable production evidence; no transport, key read or launch CLI.

Export an idle audited block snapshot. Recompute the genuine prior qualification
and every physical, financial, controller and scientific record in fresh bundled
Python -I -S. Hashes establish consistency, not provider authenticity or results.
"""
import fcntl
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from paper3 import retrospective_resource_coordinator_v1 as coordinator
from paper3 import retrospective_resource_freeze_v1 as freeze
from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_resource_budget_v1 as budget
from paper3 import retrospective_qualification_inheritance as qualification
from paper3 import retrospective_resource_late_qualification_v1 as late_qualification
from paper3 import retrospective_resource_retirement_v1 as retirement

def _helper():
    # analysis/__init__.py eagerly imports NumPy. Load the existing stdlib-only
    # helper directly, as the original qualification runner does; do not edit it.
    path = Path(__file__).resolve().parents[1] / "analysis/paper3_contracts_archive.py"
    spec = importlib.util.spec_from_file_location("_recovery_portable_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


portable = _helper()
FAMILY = "paper3-resource-accountability-portable-v1"
ENTRY = "analysis/paper3_resource_replay_v1.py"


def _retirement_bundle(directory, archive):
    """Whole old snapshot and pinned ZIP, not a cached retirement assertion."""
    directory, archive = Path(directory), Path(archive)
    portable.require(not directory.is_symlink() and not archive.is_symlink() and
        qualification.file_sha(archive) == retirement.ARCHIVE_SHA, "original retirement ZIP changed")
    metadata = portable.verify_bundle(directory, retirement.PROTOCOL)
    portable.require(metadata["experiment_family"] == "paper3-anticipation-recovery-portable-v2" and
        metadata["report_sha256"] == retirement.REPORT_SHA, "original retirement report/family changed")
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        portable.require(len(names) == len(set(names)) and
            set(names) == set(metadata["files"]) | {"bundle.json"}, "original retirement ZIP inventory")
        for name in names:
            portable.require(zipped.read(name) == portable.safe(directory, name).read_bytes(),
                             "original retirement extraction differs from pinned ZIP")
    return metadata


def _replay_retirement(directory, archive):
    """Replay the old archive's actual bundled code IN this already isolated process.

    A second subprocess would violate the installed network/process guard.
    The nested module's __file__ is its original archived path; every old source
    and original historical ledger is checked by that unchanged production audit.
    """
    _retirement_bundle(directory, archive)
    path = Path(directory) / "code/paper3/retrospective_recovery_archive_v2.py"
    spec = importlib.util.spec_from_file_location("_original_retirement_archive", path)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    certificate = original.replay(directory, retirement.PROTOCOL)
    portable.require(certificate["report_sha256"] == retirement.REPORT_SHA and
        certificate["isolated_report_matched"] is True and
        certificate["genuine_qualification_reproduced"] is True,
        "original full retirement audit did not reproduce")
    return certificate


def report_sha(report):
    return portable.sha(journal.canonical(journal.encode(report)).encode())


def _json_files(directory):
    directory = Path(directory)
    portable.require(not directory.is_symlink() and not list(directory.rglob("*.partial")),
                     "interrupted/symlink evidence; no export")
    result = {}
    for path in sorted(directory.rglob("*")):
        portable.require(not path.is_symlink(), "symlink evidence; no export")
        if path.is_file() and path.suffix == ".json":
            result[path.relative_to(directory).as_posix()] = path.read_bytes()
    return result


def _snapshot(ledger):
    # Caller already holds the financial lock. Never nest snapshot()'s flock.
    rows = ledger._entries()
    used, commitments = ledger._total(rows), ledger._commitments(rows)
    return dict(budget_id=budget.BUDGET_ID, cap_usd=str(budget.TOTAL_CAP),
        original_cap_usd="10.00", authority_extension_sha256=budget.EXTENSION_SHA,
        accounted_usd=str(used), remaining_usd=str(budget.TOTAL_CAP-used), entries=len(rows),
        unspent_active_stage_caps_usd=str(commitments),
        available_for_new_stages_usd=str(budget.TOTAL_CAP-used-commitments),
        pending=sum(r["status"] != "settled" for r in rows),
        uncertified=sum(r.get("certified") is False for r in rows))


def build(root, repo, ledger_root, protocol, qualified_directory, qualified_zip, target, *, secret=None):
    root, repo, ledger_root, target = (Path(p).resolve() for p in (root, repo, ledger_root, target))
    portable.require(not target.exists() and not target.is_relative_to(root) and
        not target.is_relative_to(ledger_root), "fresh separate archive destination required")
    # Lock an EXISTING coordinator file; never turn an unstarted run into started state.
    with (root / "coordinator.lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = coordinator.audit(root, repo, ledger_root, protocol)
        portable.require(report["blocks"][0]["evidence"] is not None, "terminal first block required")
        manifest, _ = freeze.verify(root, repo, protocol)
        spec = journal.decode(manifest["specification"])
        proof = qualification.prove(qualified_directory, qualified_zip, spec["assignments"],
                                    allow_menu_bound_instantiation=True)
        portable.require(journal.canonical(journal.encode(proof)) ==
            journal.canonical(manifest["qualification_proof"]), "full qualification proof differs")
        content = {"code/"+name: text.encode()
                   for name, text in journal.load(root / "sources.json").items()}
        portable.require("code/"+ENTRY in content and
            "code/paper3/retrospective_resource_archive_v1.py" in content,
            "replay/export code must be in the prospective source freeze")
        content.update({"run/"+name: data for name, data in _json_files(root).items()})
        ledger = budget.RecoveryLedger(ledger_root, retirement_pins=manifest["retirement_pins"])
        with ledger.locked():
            portable.require(_snapshot(ledger) == report["budget"], "ledger changed during audit/export")
            content.update({"ledger/"+name: data for name, data in _json_files(ledger_root).items()})
        content["ledger/ledger.lock"] = b""
        # Embed the ENTIRE genuine qualification, not a cached gate-passed assertion.
        metadata = qualification.qualified.archive_helper().verify_bundle(qualified_directory, qualification.PROTOCOL)
        for name in (*metadata["files"], "bundle.json"):
            content["qualified/"+name] = portable.safe(qualified_directory, name).read_bytes()
        content["qualified.zip"] = Path(qualified_zip).read_bytes()
        portable.require(portable.sha(content["qualified.zip"]) == qualification.ARCHIVE_SHA,
                         "qualification archive changed during export")
        retired = repo / "paper3/data/pivot_b_retrospective_anticipation_recovery_v2_batch0"
        retired_zip = retired.with_suffix(".zip")
        old_metadata = _retirement_bundle(retired, retired_zip)
        for name in (*old_metadata["files"], "bundle.json"):
            content["retired/"+name] = portable.safe(retired, name).read_bytes()
        content["retired.zip"] = retired_zip.read_bytes()
        late = repo / "paper3/data/pivot_b_retrospective_late_context_bounded_gate_v1"
        late_zip = late.with_suffix(".zip")
        late_proof = late_qualification.prove(late, late_zip, spec["assignments"])
        portable.require(late_proof == manifest["late_qualification_proof"], "late gate proof differs")
        late_metadata = portable.verify_bundle(late, late_qualification.PROTOCOL)
        for name in (*late_metadata["files"], "bundle.json"):
            content["late-qualified/" + name] = portable.safe(late, name).read_bytes()
        content["late-qualified.zip"] = late_zip.read_bytes()
        content["expected_report.json"] = journal.canonical(journal.encode(report)).encode()
    content["README.md"] = ("# Paper 3 anticipation — evidence snapshot\n\n"
        "Selected-case discovery, not population or publication evidence. All 16 assignments, "
        "failed/unrun terms, seven district and 63 citizen outcomes and full reservations remain. "
        "A partial archive keeps the unrun second block missing; it never supplies outcomes.\n\n"
        "Standard library only; no credentials, weights, site packages or original checkout. Run:\n\n"
        "`python3 -I -S code/"+ENTRY+" . --expected-protocol "+protocol+"`\n\n"
        "Replay verifies every source, the entire original qualification, physical attempts, "
        "journal, controller, both scientific horizons and historical financial snapshot. "
        "Network and child-process denial is self-tested. This executes trusted bundled code; "
        "it is not a sandbox for arbitrary downloaded Python. No new inference is made.\n").encode()
    for name, data in content.items():
        portable.safe(target, name)
        portable.credentials(data, secret)
    metadata = dict(format=portable.FORMAT, experiment_family=FAMILY, protocol=protocol,
        report_sha256=report_sha(report), qualified_archive_sha256=qualification.ARCHIVE_SHA,
        retired_archive_sha256=retirement.ARCHIVE_SHA,
        retired_report_sha256=retirement.REPORT_SHA,
        files={name: portable.sha(data) for name, data in sorted(content.items())})
    target.mkdir(parents=True, exist_ok=False)
    for name, data in content.items():
        path = portable.safe(target, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    with (target / "bundle.json").open("x") as stream:
        json.dump(metadata, stream, sort_keys=True, indent=2)
    return metadata


def replay(root, protocol):
    """Called ONLY by fresh isolated bundled entry; no parent-checkout replay."""
    root = Path(root).resolve(strict=True)
    portable.require(sys.flags.isolated == 1 and sys.flags.no_site == 1 and
        Path(__file__).resolve() == root / "code/paper3/retrospective_resource_archive_v1.py",
        "fresh isolated bundled Python required")
    metadata = portable.verify_bundle(root, protocol)
    portable.require(metadata["experiment_family"] == FAMILY and
        metadata["qualified_archive_sha256"] == qualification.ARCHIVE_SHA and
        metadata["retired_archive_sha256"] == retirement.ARCHIVE_SHA and
        metadata["retired_report_sha256"] == retirement.REPORT_SHA, "archive family/pin changed")
    manifest, _ = freeze.verify(root / "run", root / "code", protocol)
    proof = qualification.prove(root / "qualified", root / "qualified.zip",
        journal.decode(manifest["specification"])["assignments"], allow_menu_bound_instantiation=True)
    portable.require(journal.canonical(journal.encode(proof)) ==
        journal.canonical(manifest["qualification_proof"]), "genuine bundled qualification proof differs")
    _replay_retirement(root / "retired", root / "retired.zip")
    late = late_qualification.prove(root / "late-qualified", root / "late-qualified.zip",
        journal.decode(manifest["specification"])["assignments"])
    portable.require(late == manifest["late_qualification_proof"], "bundled late gate proof differs")
    report = coordinator.audit(root / "run", root / "code", root / "ledger", protocol)
    portable.require(journal.canonical(journal.encode(report)) ==
        journal.canonical(journal.load(root / "expected_report.json")) and
        report_sha(report) == metadata["report_sha256"], "ENTIRE bundled report differs")
    portable.verify_bundle(root, protocol)  # Replay must not change archived files.
    return dict(protocol=protocol, report_sha256=report_sha(report), isolated_report_matched=True,
        network_guard_self_test=True, genuine_qualification_reproduced=True,
        original_retirement_report_reproduced=True,
        publication_evidence=False)


def isolated_certificate(target, archive, protocol):
    """Actually extract and execute, never infer success from a cached flag."""
    target, archive = Path(target).resolve(strict=True), Path(archive).resolve(strict=True)
    metadata = portable.verify_bundle(target, protocol)
    portable.require(metadata["experiment_family"] == FAMILY, "unexpected archive family")
    with tempfile.TemporaryDirectory(prefix="paper3-anticipation-replay-") as temporary:
        extracted = Path(temporary).resolve()
        with zipfile.ZipFile(archive) as zipped:
            names = zipped.namelist()
            portable.require(len(names) == len(set(names)) and
                set(names) == set(metadata["files"]) | {"bundle.json"}, "ZIP inventory differs")
            for name in names:
                path = portable.safe(extracted, name)
                data = zipped.read(name)
                expected = portable.sha((target / "bundle.json").read_bytes()) if name == "bundle.json" else metadata["files"][name]
                portable.require(portable.sha(data) == expected, "ZIP payload differs")
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as stream:
                    stream.write(data)
        child = subprocess.run([sys.executable, "-I", "-S", str(extracted / "code" / ENTRY),
            str(extracted), "--expected-protocol", protocol], cwd=extracted, capture_output=True,
            text=True, timeout=3600, check=True)
        certificate = json.loads(child.stdout)
    portable.require(certificate["protocol"] == protocol and
        certificate["report_sha256"] == metadata["report_sha256"] and
        certificate["isolated_report_matched"] is True and certificate["network_guard_self_test"] is True and
        certificate["genuine_qualification_reproduced"] is True and
        certificate["original_retirement_report_reproduced"] is True, "actual isolated replay did not certify")
    return dict(certificate, archive_sha256=qualification.file_sha(archive))


def export(root, repo, ledger, protocol, qualified_directory, qualified_zip, target, archive, *, secret=None):
    portable.require(not Path(archive).exists(), "archive exists; never overwrite")
    metadata = build(root, repo, ledger, protocol, qualified_directory, qualified_zip, target, secret=secret)
    portable.archive(target, archive)
    certificate = isolated_certificate(target, archive, protocol)
    portable.require(certificate["report_sha256"] == metadata["report_sha256"], "export report pin changed")
    return certificate
