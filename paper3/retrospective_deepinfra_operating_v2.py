"""Prospective default transport bridge; no CLI, key read, preparation or launch.

Prospective freezes may pin this bridge and its exact readiness record. Component
freezes without operating readiness cannot use it. Offline
tests exercise the DEFAULT backend resolution that earlier injected-hook tests
missed. No compatibility proof or arbitrary callback supplies launch authority.
"""
import json
from pathlib import Path
import re
import time

from experiments import paper3_transport_diagnostic as diagnostic
from paper3 import hosted_reasoning_transport_v2 as hosted
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_deepinfra_archive_v2 as archive
from paper3 import retrospective_deepinfra_coordinator_v2 as coordinator
from paper3 import retrospective_deepinfra_freeze_v2 as freeze
from paper3 import retrospective_episode_journal as journal
from paper3.retrospective_source_closure import closure

READINESS_FORMAT = "paper3-deepinfra-overload-readiness-v2"
REQUIRED_CHECKS = {
    "overload": [".venv/bin/python", "-m", "pytest",
        "tests/test_paper3_retrospective_deepinfra_overload_v2.py",
        "tests/test_paper3_retrospective_deepinfra_retirement_v2.py",
        "tests/test_paper3_retrospective_deepinfra_pipeline_v2.py",
        "-q", "--tb=short", "--show-capture=no", "-x"],
}


def readiness_inventory(repo):
    """Exact current implementation AND complete-file test-source inventory."""
    repo = Path(repo).resolve(strict=True)
    roots = freeze.source_roots(repo) + [repo / "paper3/retrospective_deepinfra_operating_v2.py"]
    roots += [repo / argument for command in REQUIRED_CHECKS.values()
              for argument in command[3:] if argument.endswith(".py")]
    return {path.relative_to(repo).as_posix():journal._digest(path)
            for path in closure(repo, roots)}


def readiness_check(repo, record_path, expected_sha256):
    """Verify externally pinned OFFLINE evidence, not human or launch authority.

No record is generated here, no test is silently run, and no key/network/stage
is touched. The operating agent must save genuine completed command outputs,
with exact before/after source inventory equality, before preparation. Hashes
cannot establish authentic execution by themselves; fabricated unit-test
records remain fabricated, and none is created in the actual research results.
"""
    repo = Path(repo).resolve(strict=True)
    original = Path(record_path)
    institution.require(not original.is_symlink(), "readiness symlink refused")
    path = original.resolve(strict=True)
    institution.require(path.is_relative_to(repo), "readiness outside repository")
    journal._protocol(expected_sha256)
    data = path.read_bytes()
    institution.require(journal.physical.t.sha(data) == expected_sha256,
                        "external readiness pin changed")
    record = json.loads(data)
    institution.require(set(record) == {"format", "sources_before", "sources_after",
        "specification_sha256", "checks", "actual_model_calls"} and
        record["format"] == READINESS_FORMAT and
        type(record["actual_model_calls"]) is int and record["actual_model_calls"] == 0,
        "offline readiness scope changed")
    current = readiness_inventory(repo)
    institution.require(record["sources_before"] == record["sources_after"] == current and
        record["specification_sha256"] == journal.physical.t.sha(
            journal.canonical(freeze.specification()).encode()),
        "readiness source/specification changed")
    institution.require(type(record["checks"]) is dict and set(record["checks"]) == set(REQUIRED_CHECKS),
                        "all whole-file readiness checks required")
    for name, command in REQUIRED_CHECKS.items():
        evidence = record["checks"][name]
        institution.require(type(evidence) is dict and
            set(evidence) == {"argv", "returncode", "stdout", "stderr"} and
            evidence["argv"] == command and type(evidence["returncode"]) is int and
            evidence["returncode"] == 0 and type(evidence["stdout"]) is str and
            type(evidence["stderr"]) is str and not evidence["stderr"].strip() and
            re.search(r"(?:^|\n)[1-9][0-9]* passed in [0-9]+(?:\.[0-9]+)?s"
                      r"(?: \([0-9]+:[0-9]{2}:[0-9]{2}\))?\s*$",
                      evidence["stdout"]) is not None and
            not re.search(r"\b(?:failed|errors?|skipped|deselected|xfailed|xpassed)\b",
                          evidence["stdout"], re.IGNORECASE),
            "incomplete, filtered or unsuccessful readiness check: " + name)
    return dict(path=path.relative_to(repo).as_posix(), sha256=expected_sha256,
        sources_verified=True, offline_checks_verified=True,
        authentic_execution_proved_by_hash=False, actual_model_calls=0,
        allocation_authorized=False, launch_authorized=False, publication_evidence=False)


def resolve_default_transport():
    """Resolve the actual qualified entry points BEFORE any financial admission."""
    send, lookup = hosted.transmit, diagnostic.receipt_lookup
    institution.require(callable(send) and callable(lookup), "default transport entry points unavailable")
    return send, lookup


def run_block(root, repo, ledger, protocol, batch, *, metadata=None, metadata_observed_unix=None,
              observe_metadata=None, secret=None, partial_directory=None, partial_zip=None,
              clock=time.time, sleep=time.sleep):
    """Explicit serial block with real default hooks and actual partial replay.

The outer operating runner must establish genuine scope approval, reviewed
readiness, full funding and original process/start state before calling. This
bridge reads no credentials and does not prepare, allocate directly or retry.
The coordinator independently rechecks frozen sources, funding and start state.
"""
    institution.require(type(batch) is int and batch in (0, 1), "explicit batch required")
    send, lookup = resolve_default_transport()
    repo = Path(repo).resolve(strict=True)
    path = Path(__file__).resolve(strict=True)
    institution.require(path.is_relative_to(repo), "operating source outside frozen repository")
    manifest, _ = freeze.verify(root, repo, protocol)
    name = path.relative_to(repo).as_posix()
    institution.require(manifest["sources"].get(name) == journal._digest(path),
                        "operating bridge must be in the prospective source freeze")
    pin = manifest.get("operating_readiness")
    institution.require(pin is not None, "verified operating readiness required before admission")
    freeze.readiness_pin_check(pin)
    readiness_check(repo, repo / pin["path"], pin["sha256"])
    authorization = manifest.get("operating_authorization")
    institution.require(authorization is not None, "pinned operating human authorization required")
    institution.require(freeze.authorization_check(repo) == authorization, "operating authority differs")
    if batch == 0:
        institution.require(partial_directory is None and partial_zip is None,
                            "first block cannot supply a partial certificate")
        certify = None
    else:
        institution.require(partial_directory is not None and partial_zip is not None,
                            "second block requires actual partial archive paths")
        # Resolve both before allocation/admission; ambiguous/missing evidence stops.
        target = Path(partial_directory).resolve(strict=True)
        zipped = Path(partial_zip).resolve(strict=True)
        institution.require(target.is_dir() and zipped.is_file(), "partial archive paths invalid")
        def certify(partial):
            certificate = archive.isolated_certificate(target, zipped, protocol)
            institution.require(certificate["report_sha256"] == archive.report_sha(partial),
                                "actual partial replay differs from current audited block")
            return certificate
    return coordinator.run_block(root, repo, ledger, protocol, batch,
        metadata=metadata, metadata_observed_unix=metadata_observed_unix,
        observe_metadata=observe_metadata,
        send=send, lookup=lookup, certify_partial=certify,
        secret=secret, clock=clock, sleep=sleep)
