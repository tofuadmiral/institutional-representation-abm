"""Portable new-route evidence; actual isolated replay, no inherited model pass.

The separately executed retirement certificate pins the old archive/report and
all original incurred entries. This archive reproduces that financial binding
and the ENTIRE new run from raw actions, not a cached qualification result.
"""
import fcntl
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_deepinfra_coordinator_v1 as coordinator
from paper3 import retrospective_deepinfra_freeze_v1 as freeze
from paper3 import retrospective_deepinfra_budget_v1 as budget
from paper3 import retrospective_deepinfra_retirement_v1 as retirement


def _helper():
    path = Path(__file__).resolve().parents[1] / "analysis/paper3_contracts_archive.py"
    spec = importlib.util.spec_from_file_location("_deepinfra_portable", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


portable = _helper()
FAMILY = "paper3-deepinfra-accountability-portable-v1"
ENTRY = "analysis/paper3_deepinfra_replay_v1.py"


def report_sha(report):
    return portable.sha(journal.canonical(journal.encode(report)).encode())


def _json_files(directory):
    directory = Path(directory)
    portable.require(not directory.is_symlink() and not list(directory.rglob("*.partial")),
                     "partial or symlink evidence; no export")
    result = {}
    for path in sorted(directory.rglob("*")):
        portable.require(not path.is_symlink(), "symlink evidence")
        if path.is_file() and path.suffix == ".json":
            result[path.relative_to(directory).as_posix()] = path.read_bytes()
    return result


def _snapshot(ledger):
    rows = ledger._entries()
    used, held = ledger._total(rows), ledger._commitments(rows)
    return dict(budget_id=budget.BUDGET_ID, cap_usd=str(budget.TOTAL_CAP), original_cap_usd="10.00",
        authority_extension_sha256=budget.EXTENSION_SHA, accounted_usd=str(used),
        remaining_usd=str(budget.TOTAL_CAP-used), entries=len(rows),
        unspent_active_stage_caps_usd=str(held),
        available_for_new_stages_usd=str(budget.TOTAL_CAP-used-held),
        pending=sum(r["status"] != "settled" for r in rows),
        uncertified=sum(r.get("certified") is False for r in rows))


def build(root, repo, ledger_root, protocol, qualified_directory, qualified_zip, target, *, secret=None):
    root, repo, ledger_root, target = (Path(p).resolve() for p in (root,repo,ledger_root,target))
    portable.require(not target.exists() and not target.is_relative_to(root) and
                     not target.is_relative_to(ledger_root), "new separate destination required")
    with (root/"coordinator.lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = coordinator.audit(root,repo,ledger_root,protocol)
        portable.require(report["blocks"][0]["evidence"] is not None, "terminal first block required")
        manifest,_ = freeze.verify(root,repo,protocol)
        content = {"code/"+name:text.encode() for name,text in journal.load(root/"sources.json").items()}
        portable.require("code/"+ENTRY in content, "actual isolated replay code must be frozen")
        content.update({"run/"+name:data for name,data in _json_files(root).items()})
        ledger = budget.RecoveryLedger(ledger_root,retirement_pins=manifest["retirement_pins"])
        with ledger.locked():
            portable.require(_snapshot(ledger) == report["budget"], "ledger changed during export")
            content.update({"ledger/"+name:data for name,data in _json_files(ledger_root).items()})
        content["ledger/ledger.lock"] = b""
        content["expected_report.json"] = journal.canonical(journal.encode(report)).encode()
    content["README.md"] = (
        "# Paper 3 DeepInfra FP4 discovery evidence\n\n"
        "All 16 assignments, failures, missing outcomes, both terms and citizen harms remain. "
        "No inherited provider qualification, publication or population claim.\n\n"
        "Offline standard-library replay: `python3 -I -S code/"+ENTRY+
        " . --expected-protocol "+protocol+"`\n\n"
        "Replay checks raw actions, source freeze and full historical financial ledger. "
        "The pinned retirement certificate records a separately executed old-archive replay; "
        "this bundle does not claim to rerun that older model study or establish new provider reliability.\n"
    ).encode()
    for name,data in content.items():
        portable.safe(target,name)
        portable.credentials(data,secret)
    metadata = dict(format=portable.FORMAT, experiment_family=FAMILY, protocol=protocol,
        report_sha256=report_sha(report),
        migration_retirement_sha256=budget.MIGRATION_CERTIFICATE_SHA,
        retired_archive_sha256=retirement.ARCHIVE_SHA,
        inherited_provider_qualification_pass=False,
        files={name:portable.sha(data) for name,data in sorted(content.items())})
    target.mkdir(parents=True,exist_ok=False)
    for name,data in content.items():
        path = portable.safe(target,name)
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    with (target/"bundle.json").open("x") as stream:
        json.dump(metadata,stream,sort_keys=True,indent=2)
    return metadata


def replay(root,protocol):
    root = Path(root).resolve(strict=True)
    portable.require(sys.flags.isolated == 1 and sys.flags.no_site == 1 and
        Path(__file__).resolve() == root/"code/paper3/retrospective_deepinfra_archive_v1.py",
        "actual fresh isolated bundled replay required")
    metadata = portable.verify_bundle(root,protocol)
    portable.require(metadata["experiment_family"] == FAMILY and
        metadata["migration_retirement_sha256"] == budget.MIGRATION_CERTIFICATE_SHA and
        metadata["inherited_provider_qualification_pass"] is False, "archive binding changed")
    retirement.verify_record(root/"ledger",budget.MIGRATION_CERTIFICATE_SHA)
    report = coordinator.audit(root/"run",root/"code",root/"ledger",protocol)
    portable.require(journal.canonical(journal.encode(report)) ==
        journal.canonical(journal.load(root/"expected_report.json")) and
        report_sha(report) == metadata["report_sha256"], "ENTIRE replay report differs")
    portable.verify_bundle(root,protocol)
    return dict(protocol=protocol, report_sha256=report_sha(report), isolated_report_matched=True,
        network_guard_self_test=True, retirement_binding_verified=True,
        inherited_provider_qualification_pass=False, publication_evidence=False)


def isolated_certificate(target,archive,protocol):
    target,archive = Path(target).resolve(strict=True),Path(archive).resolve(strict=True)
    metadata = portable.verify_bundle(target,protocol)
    with tempfile.TemporaryDirectory(prefix="paper3-deepinfra-replay-") as temporary:
        extracted = Path(temporary).resolve()
        with zipfile.ZipFile(archive) as zipped:
            names = zipped.namelist()
            portable.require(zipped.testzip() is None and len(names) == len(set(names)) and
                set(names) == set(metadata["files"]) | {"bundle.json"}, "ZIP CRC/inventory differs")
            for info in zipped.infolist():
                portable.require((info.external_attr >> 16) & 0o170000 != 0o120000,"ZIP symlink")
                path = portable.safe(extracted,info.filename)
                data = zipped.read(info)
                expected = portable.sha((target/"bundle.json").read_bytes()) if info.filename == "bundle.json" else metadata["files"][info.filename]
                portable.require(portable.sha(data) == expected, "ZIP member differs")
                path.parent.mkdir(parents=True,exist_ok=True)
                with path.open("xb") as stream:
                    stream.write(data)
        child = subprocess.run([sys.executable,"-I","-S",str(extracted/"code"/ENTRY),
            str(extracted),"--expected-protocol",protocol],cwd=extracted,capture_output=True,
            text=True,timeout=3600,check=True)
        certificate = json.loads(child.stdout)
    portable.require(certificate == dict(protocol=protocol,report_sha256=metadata["report_sha256"],
        isolated_report_matched=True,network_guard_self_test=True,retirement_binding_verified=True,
        inherited_provider_qualification_pass=False,publication_evidence=False), "actual replay did not certify")
    return dict(certificate,archive_sha256=journal._digest(archive))


def export(root,repo,ledger,protocol,qualified_directory,qualified_zip,target,archive,*,secret=None):
    portable.require(not Path(archive).exists(), "never overwrite archive")
    build(root,repo,ledger,protocol,qualified_directory,qualified_zip,target,secret=secret)
    portable.archive(target,archive)
    return isolated_certificate(target,archive,protocol)
