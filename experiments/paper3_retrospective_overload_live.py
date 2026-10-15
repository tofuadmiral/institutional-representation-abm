"""Approved bounded production adapter; no qualification calls or run restart."""
# ruff: noqa: E402
import argparse
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import paper3_retrospective_overload_discovery as core
from paper3 import hosted_reasoning_calls as service

APPROVAL = dict(source="direct human user message", response="Approved", date="2026-10-01",
    thread_id="01a09ba8-a109-7b62-a8a0-61519cfdea84", policy=dict(
        kind="pre_answer_429_shared_pool_only", reissues_per_logical=1,
        maximum_reissues_per_batch=25, delay_seconds=60, identical_wire=True,
        retain_all_costs=True, retry_bad_answers=False, cumulative_stop_usd="8", stage_cap_usd="3.20"))


def endpoint():
    # Public metadata only: no API key or paid inference.
    with core.t.opener().open(core.route.METADATA_URL, timeout=20) as response:
        metadata = json.load(response)
    observed = time.time()
    core.route.check_endpoint(metadata)
    return metadata, observed


def prepare(root, ledger_root, *, metadata=None, observed=None):
    if metadata is None:
        metadata, observed = endpoint()
    return core.prepare(root, ledger_root, metadata, approval=APPROVAL,
        extra_roots=(Path(__file__).resolve(), ROOT / "tests/test_paper3_retrospective_overload_live.py"),
        metadata_observed_unix=observed)


def execute(root, batch, ledger_root, expected_protocol, *, metadata=None, observed=None,
            send=None, lookup=None, secret=None, clock=time.time, sleep=time.sleep):
    manifest, protocol = core.verify(root)
    core.require(protocol == expected_protocol, "unexpected protocol")
    core.require(manifest["protocol"]["paid_launch_authorized"] is True and
                 manifest["protocol"]["human_approval"] == APPROVAL, "production approval missing/changed")
    if metadata is None:
        metadata, observed = endpoint()
    if send is None:
        core.require(lookup is None and secret is None, "no partial live transport override")
        secret = core.t.read_key()
        send, lookup = service.transmit, core.t.receipt_lookup
    core.require(callable(lookup), "receipt transport required")
    return core.execute(root, batch, ledger_root, send=send, lookup=lookup, secret=secret,
        metadata=metadata, metadata_observed_unix=observed, clock=clock, sleep=sleep)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--ledger-root", type=Path, default=core.closed.BUDGET)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("prepare", "run", "audit", "export", "replay"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--batch", type=int, choices=(0, 1))
    parser.add_argument("--expected-protocol")
    parser.add_argument("--target", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.prepare:
        result = dict(protocol=prepare(args.root, args.ledger_root))
    else:
        core.require(args.expected_protocol is not None, "expected protocol required")
        if args.replay:
            result = core.auditor().replay(args.root, args.expected_protocol)
        else:
            core.require(core.verify(args.root)[1] == args.expected_protocol, "unexpected protocol")
            if args.run:
                core.require(args.batch is not None, "explicit batch required; no automatic successor")
                result = execute(args.root, args.batch, args.ledger_root, args.expected_protocol)
            elif args.audit:
                result = core.audit(args.root, args.ledger_root)
            else:
                core.require(args.target is not None and args.archive is not None, "export paths required")
                result = core.auditor().export(args.root, args.ledger_root, args.target, args.archive)
    # No credentials or raw messages in terminal output.
    if args.audit or args.replay:
        result = {k: result[k] for k in ("protocol", "completed", "calls", "recoveries",
                  "accounted_usd", "cumulative_accounted_usd", "publication_evidence")}
    print(json.dumps(core.jsonable(result), indent=2))


if __name__ == "__main__":
    main()
