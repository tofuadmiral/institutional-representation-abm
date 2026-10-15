"""Explicit full-design operating interface; import/help perform no experiment.

Prepare freezes only; run requires an external protocol and an explicit block.
No auto-successor, restart, budget extension, credit purchase or case tuning.
All real launch permission comes from Fuad, not this CLI or a passing test.
"""
# ruff: noqa: E402
import argparse
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import paper3_transport_diagnostic as diagnostic
from paper3 import retrospective_anticipation_archive as archive
from paper3 import retrospective_anticipation_coordinator as coordinator
from paper3 import retrospective_anticipation_freeze as freeze
from paper3 import retrospective_anticipation_operating as operating
from paper3 import retrospective_contract_route_v2 as route
from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_extended_budget as budget

STAGE = "pivot_b_retrospective_anticipation_v1"


def locations():
    repo = ROOT.resolve(strict=True)
    return dict(repo=repo, root=repo / "results/paper3" / STAGE,
        ledger=repo / "results/paper3/pivot_b_budget",
        qualified=repo / "paper3/data/pivot_b_retrospective_score_ledger_gate_v1",
        qualified_zip=repo / "paper3/data/pivot_b_retrospective_score_ledger_gate_v1.zip")


def _root_check(root, paths):
    original = Path(root)
    journal.institution.require(not original.is_symlink() and
        original.resolve() == paths["root"].resolve(), "exact fresh operating root required")
    # No ancestor redirects into another experiment or credential directory.
    journal.institution.require(all(not p.is_symlink() for p in
        (paths["root"].parent, paths["root"].parent.parent)), "operating root ancestor symlink")


def full_funding(paths):
    ledger = budget.ExtendedLedger(paths["ledger"])
    with ledger.locked():
        rows = ledger._entries()
        full = budget.amount(journal.decode(freeze.specification())["bound"]["full_reservation_usd"])
        used, commitments = ledger._total(rows), ledger._commitments(rows)
        journal.institution.require(used + commitments + full <= budget.TOTAL_CAP,
            "full16-assignment budget admission denied; no key, fetch or partial pilot")
    return dict(full_bound_usd=str(full), accounted_usd=str(used),
                unused_commitments_usd=str(commitments), total_cap_usd=str(budget.TOTAL_CAP))


def observe_metadata():
    """Exactly one unauthenticated GET at admission, never background polling."""
    with diagnostic.opener().open(route.METADATA_URL, timeout=20) as response:
        metadata = json.load(response)
    observed = time.time()
    route.check_endpoint(metadata)
    return metadata, observed


def _own_source(manifest, paths):
    path = Path(__file__).resolve(strict=True)
    journal.institution.require(path == paths["repo"] / freeze.RUNNER_FILE and
        manifest["sources"].get(freeze.RUNNER_FILE) == journal._digest(path),
        "operating runner must be in frozen source closure")


def inspect(root, protocol):
    """Read-only source/readiness/human checks; no key or public metadata fetch."""
    paths = locations()
    _root_check(root, paths)
    manifest, _ = freeze.verify(root, paths["repo"], protocol)
    _own_source(manifest, paths)
    pin = manifest["operating_readiness"]
    journal.institution.require(pin is not None, "operating readiness required")
    operating.readiness_check(paths["repo"], paths["repo"] / pin["path"], pin["sha256"])
    freeze.authorization_check(paths["repo"], manifest["operating_authorization"])
    journal.institution.require(not list(Path(root).rglob("*.partial")), "interrupted evidence; no restart")
    lock = Path(root) / "coordinator.lock"
    if lock.exists():
        with lock.open("r+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return paths, manifest


def read_secret(repo):
    """Only the admitted run path invokes this. No value appears in output."""
    path = Path(repo) / ".env.local"
    info = path.lstat()
    journal.institution.require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
        info.st_mode & 0o077 == 0, "key file must be owner-owned, regular and owner-only")
    ignored = subprocess.run(["git", "check-ignore", "--quiet", "--", ".env.local"],
        cwd=repo, capture_output=True, check=False)
    journal.institution.require(ignored.returncode == 0, "key file must be git ignored")
    values = [line.split("=", 1)[1].strip().strip("\"'") for line in path.read_text().splitlines()
              if line.strip().startswith("OPENROUTER_API_KEY=")]
    journal.institution.require(len(values) == 1 and values[0] and
        not any(c.isspace() for c in values[0]), "invalid key file")
    return values[0]


def prepare(root, *, readiness_sha256, authorization_sha256):
    paths = locations()
    _root_check(root, paths)
    journal.institution.require(not paths["root"].exists(), "fresh root only; never reprepare")
    pin = dict(path=freeze.READINESS_FILE, sha256=readiness_sha256)
    freeze.readiness_pin_check(pin)
    operating.readiness_check(paths["repo"], paths["repo"] / pin["path"], pin["sha256"])
    authorization = dict(path=freeze.AUTHORIZATION_FILE, sha256=authorization_sha256)
    approval = freeze.authorization_check(paths["repo"], authorization)
    full_funding(paths)  # Deny before GET, genuine proof or creation.
    operating.resolve_default_transport()
    metadata, _ = observe_metadata()
    protocol = freeze.prepare(root, paths["repo"], paths["ledger"], paths["qualified"],
        paths["qualified_zip"], approval=approval["scope"], metadata=metadata,
        operating_readiness=pin, operating_authorization=authorization)
    manifest, _ = freeze.verify(root, paths["repo"], protocol)
    _own_source(manifest, paths)
    return dict(protocol=protocol, frozen_sources=len(manifest["sources"]),
                actual_model_calls=0, allocation_authorized=False, launch_authorized=False)


def destinations(paths, batch):
    journal.institution.require(type(batch) is int and batch in (0, 1), "explicit batch required")
    suffix = "_batch0" if batch == 0 else "_complete"
    target = paths["repo"] / "paper3/data" / (STAGE + suffix)
    return target, target.with_suffix(".zip")


def run(root, protocol, batch):
    journal.institution.require(type(batch) is int and batch in (0, 1), "explicit batch required")
    paths, manifest = inspect(root, protocol)
    operating.resolve_default_transport()
    sessions = Path(root) / "sessions"
    journal.institution.require(not (sessions / f"block-{batch}-start.json").exists() and
        not (Path(root) / f"block-{batch}").exists(), "already started/ambiguous; never restart")
    partial_directory = partial_zip = None
    if batch == 0:
        journal.institution.require(not (sessions / "start.json").exists(), "pilot already started")
        full_funding(paths)
        current = budget.ExtendedLedger(paths["ledger"])
        with current.locked():
            rows = current._entries()
            journal.institution.require(freeze.inventory(paths["ledger"]) == manifest["prior_entries"] and
                str(current._total(rows)) == manifest["pre_stage_accounted_usd"] and
                str(current._commitments(rows)) == manifest["pre_stage_unused_commitments_usd"],
                "frozen financial baseline changed")
    else:
        journal.institution.require((sessions / "block-0-terminal.json").is_file(),
                                    "terminal first block required")
        partial_directory, partial_zip = destinations(paths, 0)
        journal.institution.require(partial_directory.is_dir() and partial_zip.is_file(),
                                    "actual partial archive required before key read")
    # The coordinator checks funding/locks again and observes the endpoint AFTER
    # expensive partial audit/replay, retaining its strict60-second freshness.
    secret = read_secret(paths["repo"])
    return operating.run_block(root, paths["repo"], paths["ledger"], protocol, batch,
        observe_metadata=observe_metadata, secret=secret,
        partial_directory=partial_directory, partial_zip=partial_zip)


def offline(root, protocol, operation, batch=None):
    paths, _ = inspect(root, protocol)
    if operation == "audit":
        journal.institution.require(batch is None, "audit includes both blocks")
        return coordinator.audit(root, paths["repo"], paths["ledger"], protocol)
    journal.institution.require(operation in ("close", "export") and type(batch) is int and
                                batch in (0, 1), "explicit terminal operation/batch required")
    if operation == "close":
        return coordinator.close_terminal_block(root, paths["repo"], paths["ledger"], protocol, batch)
    report = coordinator.audit(root, paths["repo"], paths["ledger"], protocol)
    journal.institution.require(report["blocks"][batch]["evidence"] is not None and
        (batch == 1 or report["blocks"][1]["evidence"] is None), "exact partial/full terminal export")
    target, zipped = destinations(paths, batch)
    return archive.export(root, paths["repo"], paths["ledger"], protocol,
        paths["qualified"], paths["qualified_zip"], target, zipped)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    actions = parser.add_mutually_exclusive_group(required=True)
    for operation in ("prepare", "run", "audit", "close", "export"):
        actions.add_argument("--" + operation, action="store_true")
    parser.add_argument("--expected-protocol")
    parser.add_argument("--readiness-sha256")
    parser.add_argument("--authorization-sha256")
    parser.add_argument("--batch", type=int, choices=(0, 1))
    args = parser.parse_args(argv)
    if args.prepare:
        if not args.readiness_sha256 or not args.authorization_sha256 or args.expected_protocol or args.batch is not None:
            parser.error("prepare requires both external readiness/authorization pins, no protocol/batch")
        result = prepare(args.root, readiness_sha256=args.readiness_sha256,
                         authorization_sha256=args.authorization_sha256)
    else:
        if not args.expected_protocol or args.readiness_sha256 or args.authorization_sha256:
            parser.error("run/offline operations require only the external protocol pin")
        if args.audit and args.batch is not None or not args.audit and args.batch is None:
            parser.error("audit covers both blocks; all other terminal/run operations require a batch")
        result = run(args.root, args.expected_protocol, args.batch) if args.run else offline(
            args.root, args.expected_protocol, "audit" if args.audit else "close" if args.close else "export", args.batch)
    print(journal.canonical(journal.encode(result)))


if __name__ == "__main__":
    main()
