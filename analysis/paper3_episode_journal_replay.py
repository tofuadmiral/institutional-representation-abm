"""Offline component replay; a production source/authority wrapper is still needed.

Runs with stdlib-only Python -I -S in an extracted fabricated evidence bundle.
Pinned inventory/full-report hashes are supplied by the parent fixture, not
invented from a saved scientific summary. Never invokes any inference backend.
"""
import argparse
from pathlib import Path
import sys


def deny_network(event, args):
    if event in ("socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.bind"):
        raise RuntimeError("network prohibited during journal replay")


def main():
    sys.dont_write_bytecode = True
    sys.addaudithook(deny_network)
    import socket
    try:
        socket.getaddrinfo("127.0.0.1", 1)
    except RuntimeError as exc:
        if str(exc) != "network prohibited during journal replay":
            raise
    else:
        raise ValueError("network audit guard self-test failed")
    code = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(code))
    from paper3 import retrospective_episode_journal as journal
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--expected-protocol", required=True)
    parser.add_argument("--expected-report-sha256", required=True)
    parser.add_argument("--maximum-reissues", type=int, required=True)
    args = parser.parse_args()
    journal._protocol(args.inventory_sha256)
    journal._protocol(args.expected_report_sha256)
    journal.institution.require(journal._digest(args.inventory) == args.inventory_sha256,
                                "external inventory pin changed")
    inventory = journal.decode(journal.load(args.inventory))
    report = journal.audit(args.root.resolve(strict=True), args.ledger.resolve(strict=True),
        args.stage, inventory, args.expected_protocol,
        verify=lambda: ({}, args.expected_protocol), maximum_reissues=args.maximum_reissues)
    digest = journal.physical.t.sha(journal.canonical(journal.encode(report)).encode())
    journal.institution.require(digest == args.expected_report_sha256, "full isolated report differs")
    print(journal.canonical(dict(component_replay_matched=True, report_sha256=digest,
        journal_events=report["events_replayed"], completed=report["report"]["completed"],
        content_failed=report["report"]["content_failed"],
        global_safety_stop=report["report"]["global_safety_stop"],
        accounted_usd=report["physical_accounted_usd"], physical_attempts=report["physical_attempts"],
        physical_reissues=report["physical_reissues"], network_prohibited=True,
        network_guard_self_test=True,
        production_source_freeze_verified=False, publication_evidence=False)))


if __name__ == "__main__":
    main()
