"""Unfrozen full-design coordinator with explicit hooks; NO live CLI or key read.

No actual successor is approved/prepared here. Private fabricated tests only.
Budget/qualification/readiness and genuine human authority remain prerequisites
to any future operating wrapper. Batch1 requires actual isolated replay of
batch0, not a favorable scientific result. No inference repair or case tuning.
"""
from copy import deepcopy
import fcntl
import json
import math
from pathlib import Path
import os
import time

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_audit as science
from paper3 import retrospective_anticipation_design as design
from paper3 import retrospective_anticipation_freeze as freeze
from paper3 import retrospective_contract_route_v2 as route
from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_extended_budget as budget
from paper3 import retrospective_independent_calls as transport
from paper3 import retrospective_independent_execution as execution
from paper3.pivot_b_budget import atomic


def layout(root, ledger, protocol):
    journal._protocol(protocol)
    group = "anticipation-" + protocol[:24]
    rows = tuple(dict(seed=seed, root=Path(root) / f"block-{index}", ledger=Path(ledger),
        stage=group + f"-{index}", maximum_reissues=1) for index, seed in enumerate(design.FRAME_SEEDS))
    return group, rows


def _case(key, request):
    bound = route.reservation(request)
    payload = json.loads(request["messages"][1]["content"])
    return dict(id=key, request=deepcopy(request), **bound,
        request_sha256=transport.t.sha(bound["request_text"].encode()), context=dict(stage=payload["stage"]))


def _allocation(root, ledger, protocol, manifest):
    value = journal.load(Path(root) / "sessions/allocation.json")
    group, blocks = layout(root, ledger, protocol)
    institution.require(set(value) == {"protocol", "group", "group_sha256", "stage_pins"} and
        value["protocol"] == protocol and value["group"] == group and
        set(value["stage_pins"]) == {b["stage"] for b in blocks} and
        budget._digest(Path(ledger) / "stage_groups" / (value["group"] + ".json")) == value["group_sha256"],
        "pinned whole-pilot allocation changed")
    scoped = budget.ExtendedLedger(ledger, stage_pins=value["stage_pins"])
    spec = journal.decode(manifest["specification"])
    for block, bound in zip(blocks, spec["bound"]["blocks"], strict=True):
        record = scoped._stage(block["stage"])
        institution.require(record["group"] == group and record["prior_entries"] == manifest["prior_entries"] and
            budget.amount(record["cap_usd"]) == budget.amount(bound["full_reservation_usd"]),
            "whole-pilot caps/prior evidence differ from freeze")
    return value, scoped


def audit(root, repo, ledger_root, protocol):
    """Saved run state supplies no outcomes: all science is recomputed from actions."""
    root = Path(root)
    manifest, _ = freeze.verify(root, repo, protocol)
    _, ledger = _allocation(root, ledger_root, protocol, manifest)
    pilot_start = journal.load(root / "sessions/start.json")
    institution.require(pilot_start["protocol"] == protocol and type(pilot_start["pid"]) is int and
        pilot_start["pid"] > 0, "pilot start provenance changed")
    _, planned = layout(root, ledger_root, protocol)
    blocks = []
    for index, block in enumerate(planned):
        present = block["root"].exists()
        start = root / "sessions" / f"block-{index}-start.json"
        terminal = root / "sessions" / f"block-{index}-terminal.json"
        if present or start.exists():
            institution.require(present and start.is_file() and terminal.is_file(),
                                "interrupted block; preserve without restart")
            begin, end = journal.load(start), journal.load(terminal)
            institution.require(begin["protocol"] == end["protocol"] == protocol and
                type(begin["batch"]) is int and begin["batch"] == end["batch"] == index and
                type(end["batch"]) is int and begin["stage"] == block["stage"] and
                type(begin["metadata_observed_unix"]) in (int, float) and
                0 <= begin["started_unix"] - begin["metadata_observed_unix"] <= 60,
                "block start/terminal provenance changed")
            route.check_endpoint(begin["endpoint_metadata"])
        else:
            institution.require(not terminal.exists(), "unstarted block with terminal")
        blocks.append(dict(block, root=block["root"] if present else None))
    spec = journal.decode(manifest["specification"])
    result = science.audit(spec["assignments"], tuple(blocks), protocol,
        verify=lambda: freeze.verify(root, repo, protocol), minimum_effect=spec["minimum_effect"],
        aligned_fraction=spec["aligned_fraction"])
    for index, block in enumerate(result["blocks"]):
        if block["evidence"] is not None:
            end = journal.load(root / "sessions" / f"block-{index}-terminal.json")
            institution.require(journal.canonical(journal.encode(block["evidence"])) ==
                journal.canonical(end["evidence"]),
                                "recomputed full block evidence differs from terminal")
        closure = Path(ledger_root) / "stage_closures" / (planned[index]["stage"] + ".json")
        if closure.exists():
            institution.require(block["evidence"] is not None, "unrun block cannot be financially closed")
            record = journal.load(closure)
            terminal = root / "sessions" / f"block-{index}-terminal.json"
            institution.require(record["terminal_evidence_sha256"] == journal._digest(terminal) and
                ledger._closed(planned[index]["stage"], ledger.stage_pins()[planned[index]["stage"]]) and
                type(record["closed_unix"]) in (int, float) and math.isfinite(record["closed_unix"]) and
                record["closed_unix"] >= journal.load(terminal)["completed_unix"],
                "financial closure differs from audited terminal")
    result["budget"] = ledger.snapshot()
    result["production_source_protocol_verified"] = True
    result["whole_group"] = journal.load(root / "sessions/allocation.json")
    return result


def close_terminal_block(root, repo, ledger_root, protocol, batch):
    """Free only an unused stage cap, never an incurred/uncertified reservation.

Full physical/controller/scientific audit must pass first. This is terminal
financial bookkeeping, not scientific success or authority to restart/run.
Original records and all request costs remain, including safely failed attempts.
"""
    institution.require(type(batch) is int and batch in (0, 1), "explicit terminal batch")
    root = Path(root)
    with (root / "coordinator.lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = audit(root, repo, ledger_root, protocol)
        institution.require(before["blocks"][batch]["evidence"] is not None,
                            "unstarted/interrupted block cannot release allocation")
        manifest, _ = freeze.verify(root, repo, protocol)
        _, ledger = _allocation(root, ledger_root, protocol, manifest)
        _, planned = layout(root, ledger_root, protocol)
        terminal = root / "sessions" / f"block-{batch}-terminal.json"
        ledger.close(planned[batch]["stage"], journal._digest(terminal))
        after = audit(root, repo, ledger_root, protocol)
        institution.require(journal.canonical(journal.encode({k:v for k,v in before.items() if k != "budget"})) ==
            journal.canonical(journal.encode({k:v for k,v in after.items() if k != "budget"})) and
            before["budget"]["accounted_usd"] == after["budget"]["accounted_usd"] and
            before["budget"]["pending"] == after["budget"]["pending"] and
            before["budget"]["uncertified"] == after["budget"]["uncertified"],
            "terminal bookkeeping changed science or incurred costs")
        return after


def _fresh_endpoint(metadata, observed, clock):
    institution.require(type(observed) in (int, float) and math.isfinite(observed) and
        0 <= clock() - observed <= 60, "fresh explicit endpoint observation required")
    route.check_endpoint(metadata)


def _observe_endpoint(observe_metadata, clock):
    result = observe_metadata()
    institution.require(type(result) is tuple and len(result) == 2,
                        "explicit endpoint metadata/time pair required")
    _fresh_endpoint(*result, clock)
    return result


def run_block(root, repo, ledger_root, protocol, batch, *, metadata=None, metadata_observed_unix=None,
              send, lookup, observe_metadata=None, certify_partial=None, secret=None,
              clock=time.time, sleep=time.sleep):
    """One explicit serial block. Missing/ambiguous starts NEVER permit restart.

All16assignments/full funds precede batch0. Safe typed content failures remain
episode-local; a global unsafe stop prevents batch1. A future production wrapper
must provide a REAL fresh isolated archive replay callback, frozen in its source
closure. This component does not convert arbitrary callbacks into live authority.
"""
    root, repo, ledger_root = Path(root), Path(repo).resolve(), Path(ledger_root)
    institution.require(type(batch) is int and batch in (0, 1) and callable(send) and callable(lookup),
                        "explicit batch/transport hooks")
    manifest, _ = freeze.verify(root, repo, protocol)
    late_observation = observe_metadata is not None
    if late_observation:
        institution.require(callable(observe_metadata) and metadata is None and
                            metadata_observed_unix is None, "one explicit endpoint observation mode required")
    else:
        _fresh_endpoint(metadata, metadata_observed_unix, clock)
    group, blocks = layout(root, ledger_root, protocol)
    sessions = root / "sessions"
    sessions.mkdir(exist_ok=True)
    with (root / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        institution.require(not list(root.rglob("*.partial")), "partial persistence; never resume")
        start = sessions / f"block-{batch}-start.json"
        institution.require(not start.exists() and not blocks[batch]["root"].exists(),
                            "block already started/ambiguous; never restart")
        if batch == 0:
            institution.require(not (sessions / "start.json").exists() and
                not blocks[1]["root"].exists(), "pilot already started; never restart")
            # Recheck history while excluding ONLY this externally pinned fresh freeze.
            history = repo / "results/paper3"
            args = dict(current_freeze=root, expected_protocol=protocol) if root.resolve().is_relative_to(history) else {}
            institution.require(journal.canonical(design.seed_audit(repo, **args)) ==
                journal.canonical(manifest["seed_audit"]),
                                "historical seed inventory changed before launch")
            if late_observation:
                metadata, metadata_observed_unix = _observe_endpoint(observe_metadata, clock)
            _fresh_endpoint(metadata, metadata_observed_unix, clock)
            atomic(sessions / "start.json", dict(protocol=protocol, pid=os.getpid(), started_unix=clock()))
            ledger = budget.ExtendedLedger(ledger_root)
            spec = journal.decode(manifest["specification"])
            caps = {block["stage"]: bound["full_reservation_usd"]
                    for block, bound in zip(blocks, spec["bound"]["blocks"], strict=True)}
            allocation = ledger.allocate_group(group, caps, expected_baseline=dict(
                prior_entries=manifest["prior_entries"], accounted_usd=manifest["pre_stage_accounted_usd"],
                unused_commitments_usd=manifest["pre_stage_unused_commitments_usd"]))
            atomic(sessions / "allocation.json", dict(protocol=protocol, **allocation))
        else:
            institution.require(callable(certify_partial), "actual isolated batch0 replay required")
            partial = audit(root, repo, ledger_root, protocol)
            first = partial["blocks"][0]["evidence"]
            institution.require(first is not None and not first["report"]["global_safety_stop"],
                                "unsafe/incomplete previous block; no successor")
            institution.require(clock() >= journal.load(sessions / "block-0-terminal.json")["completed_unix"],
                                "batch1 precedes batch0 terminal")
            certificate = certify_partial(partial)
            expected = transport.t.sha(journal.canonical(journal.encode(partial)).encode())
            institution.require(type(certificate) is dict and certificate["protocol"] == protocol and
                certificate["report_sha256"] == expected and certificate["isolated_report_matched"] is True and
                certificate["network_guard_self_test"] is True, "isolated partial replay did not match")
            journal._protocol(certificate["archive_sha256"])
        _, ledger = _allocation(root, ledger_root, protocol, manifest)
        def verify():
            result = freeze.verify(root, repo, protocol)
            _allocation(root, ledger_root, protocol, result[0])
            return result
        spec = journal.decode(manifest["specification"])
        items = tuple(a for a in spec["assignments"] if a["seed"] == blocks[batch]["seed"])
        by_id = {a["id"] + f"-{i:02d}":a for a in items for i in range(30)}
        def classify(row, case):
            assignment = by_id[case["context"]["logical_id"]]
            return execution.classify(row, case["request"], assignment["game"], case["context"]["stage"])
        # Batch1 audit/replay can take MINUTES. Observe once after those checks,
        # not before them; retain the same60-second start freshness requirement.
        if batch == 1 and late_observation:
            metadata, metadata_observed_unix = _observe_endpoint(observe_metadata, clock)
        _fresh_endpoint(metadata, metadata_observed_unix, clock)
        if batch == 1:
            atomic(sessions / "partial-replay.json", certificate)
        atomic(start, dict(protocol=protocol, batch=batch, stage=blocks[batch]["stage"], pid=os.getpid(),
            started_unix=clock(), metadata_observed_unix=metadata_observed_unix, endpoint_metadata=metadata))
        bridge = transport.Calls(blocks[batch]["root"], ledger, blocks[batch]["stage"], verify, classify,
            send=send, lookup=lookup, maximum_logical=240, maximum_reissues=1,
            secret=secret, clock=clock, sleep=sleep)
        writer = None
        try:
            writer = journal.Journal(blocks[batch]["root"], items, protocol, verify=verify)
            execution.execute(items, respond=lambda request, key: bridge.one(_case(key, request)),
                verify=lambda: journal._guard(verify, protocol), persist=writer.append)
        finally:
            if writer is not None:
                writer.close()
            bridge.close()
        evidence = journal.audit(blocks[batch]["root"], ledger_root, blocks[batch]["stage"], items,
                                 protocol, verify=verify, maximum_reissues=1)
        atomic(sessions / f"block-{batch}-terminal.json", dict(protocol=protocol, batch=batch,
            completed_unix=clock(), evidence=journal.encode(evidence)))
    return audit(root, repo, ledger_root, protocol)
