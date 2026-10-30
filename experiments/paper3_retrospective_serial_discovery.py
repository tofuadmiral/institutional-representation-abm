"""Accountability successor core; no CLI launch or automatic key loading.

Two complete matched-frame batches, all sixteen assigned institutions, unchanged
scientific screen. Transport is injected explicitly for fabricated integration
tests. Production requires an explicit frozen human approval and separately
reviewed launch adapter; never attach this to the closed zero-retry pilot.
"""
# ruff: noqa: E402
from __future__ import annotations

import argparse
from decimal import Decimal
import fcntl
from functools import cache
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import paper3_retrospective_keyed_discovery as closed
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_keyed_interface as interface
from paper3 import retrospective_serial_requests as requests
from paper3 import retrospective_serial_calls as transport
from paper3 import retrospective_serial_recovery as recovery
from paper3 import retrospective_deepseek_route as route
from paper3.pivot_b_budget import Ledger, atomic
from paper3.retrospective_serial_execution import StopLedger, STOP, jsonable, prior_inventory
from paper3.source_closure import closure

t, require = closed.t, closed.require
NAME = "pivot_b_retrospective_serial_v1"
CAP, WORKERS = recovery.PROPOSED_STAGE_CAP, 1
CONFIG = recovery.CONFIG
DIRECTORIES = ("calls", "attempts", "logicals", "recoveries", "episodes", "sessions")
EpisodeFailure = closed.EpisodeFailure
qualification_proof = closed.qualification_proof


def batch_stage(index):
    require(type(index) is int and index in (0, 1), "two batch indices")
    return NAME + f"-b{index}"


def batch_root(root, index):
    batch_stage(index)
    return Path(root) / "batches" / f"batch-{index}"


def scheduled(index):
    batch_stage(index)
    return tuple(a for a in requests.assignments() if a["seed"] == requests.FRAME_SEEDS[index])


def action_call(assignment, actor, identity, term, stage, context, index):
    request = requests.action_request(assignment, actor, identity, term, stage, context, index)
    bounded = route.reservation(request)
    maximum = next(r for r in requests.legal_history_bounds()["assignments"]
                   if r["id"] == assignment["id"])["input_bounds"][index]
    require(bounded["input_token_bound"] <= maximum, "history exceeds frozen bound")
    return dict(id=assignment["id"] + f"-{index:02d}", request=request, **bounded,
        request_sha256=t.sha(bounded["request_text"].encode()),
        context=dict(assignment_id=assignment["id"], actor=actor, identity=identity,
                     term=term, stage=stage, index=index))


def score(row, case):
    result = dict(usable=False, valid_action=False, exact=False, native_reasoning=None,
                  action=None, failure="instrument_or_unfinished")
    if row.get("instrument_error") or "assessment" not in row:
        return result
    assessed = transport.service.assess(row, CONFIG)
    native = transport.service.native_evidence(assessed["stream"])
    usable = assessed["passed"] and assessed["stream"]["finish_reasons"] == ["tool_calls"] and (
        native["present"] and row["request"]["reasoning"] == dict(enabled=True, exclude=False))
    result.update(usable=usable, native_reasoning=native)
    if usable:
        try:
            assignment = next(a for a in requests.assignments() if a["id"] == case["context"]["assignment_id"])
            action = interface.decode(assignment["game"], case["context"]["stage"], row["stream"])
            result.update(valid_action=True, exact=True, action=action, failure=None)
        except (ValueError, TypeError, KeyError) as exc:
            result["failure"] = str(exc)
    else:
        result["failure"] = "transport_reasoning_or_function_completion"
    return result


@cache
def specification():
    bounds = requests.legal_history_bounds()
    require(all(Decimal(b["full_path_usd"]) <= CAP for b in bounds["batches"]), "full recovery-path bounds")
    return jsonable(dict(name=NAME,
        configuration=CONFIG, workers=WORKERS, pairs=requests.pairs(), assignments=requests.assignments(),
        batches=[dict(index=i, seed=seed, stage=batch_stage(i), cap_usd=str(CAP), assignments=scheduled(i))
                 for i, seed in enumerate(requests.FRAME_SEEDS)], bound_proof=bounds,
        order_seed=requests.ORDER_SEED, seed_base=requests.DECISION_SEED_BASE,
        maximum_logical=480, declared_attempt_slots=960, maximum_physical=530,
        maximum_reissues_per_batch=25, reissue_delay_seconds=300, physical_attempts_per_logical=2,
        cumulative_stop_usd="10", authorized_paid_batches=[0], new_gate_calls=0,
        serial_technical_calls=30, serial_request_overlap_allowed=False,
        recovery="Pinned upstream shared-pool HTTP429 only, no answer/usage/generation/receipt; identical wire/seed; keep all costs. Bad answers never reissued. New policy not approval to restart old runs.",
        admission="Both frames/all16 assignments frozen first. Serial-only throughout. Only batch0 paid scope is approved; batch1 requires new human authorization/freeze, technical completion and current ledger+3.20<=10, never conditioned on scientific direction.",
        scientific_screen="Unchanged two-sided selected-case interaction/regret screen. All16 complete; both frame directions agree, |mean|>=.04, aligned mean absolute interaction <=half conflict.",
        limitation="Selected cases/two sequential frames/one model; deterministic citizens, stipulated office incentives and stateless requests with public history. Incomplete remains inconclusive; a lead only proposes independent validation. Integration tests are not institutional evidence."))


def verify_prior_allowed(ledger_root, expected):
    current = {p.name: p for p in (Path(ledger_root) / "entries").glob("*.json")}
    require(set(expected) <= set(current), "prior ledger deleted")
    for name, digest in expected.items():
        require(t.sha(current[name].read_bytes()) == digest, "prior ledger changed")
    require(all(t.load(p)["stage"] in {batch_stage(0), batch_stage(1)}
                for name, p in current.items() if name not in expected), "unrelated spending")


def check_approval(value):
    require(type(value) is dict and set(value) == {"source", "response", "date", "thread_id", "policy"},
            "explicit human approval record required")
    require(value["source"] == "direct human user message" and value["response"] == "approved" and
            value["date"] == "2026-10-01" and value["thread_id"] == "01a09ba8-a109-7b62-a8a0-61519cfdea84" and
            value["policy"] == dict(kind="pre_answer_429_shared_pool_only", reissues_per_logical=1,
                maximum_reissues_per_batch=25, delay_seconds=300, identical_wire=True,
                retain_all_costs=True, retry_bad_answers=False, workers=1, cumulative_stop_usd="10",
                stage_cap_usd="3.20", authorized_batches=[0]),
            "approved transport/budget scope changed")


def prepare(root, ledger_root, metadata, qualification_archive=closed.QUALIFICATION,
            qualification_protocol=closed.QUALIFICATION_PROTOCOL, qualification_sha=closed.QUALIFICATION_SHA,
            *, approval=None, extra_roots=(), metadata_observed_unix=None):
    """Freeze locally; no metadata fetch, calls or budget allocation."""
    root = Path(root)
    require(not root.exists(), "fresh parent required")
    proof = qualification_proof(qualification_archive, qualification_protocol, qualification_sha)
    route.check_endpoint(metadata)
    if approval is not None:
        check_approval(approval)
        require(ROOT / "experiments/paper3_retrospective_serial_live.py" in extra_roots and
                ROOT / "tests/test_paper3_retrospective_serial_live.py" in extra_roots,
                "production adapter/tests must be frozen")
    before = Ledger(ledger_root).snapshot()
    require(Decimal(before["accounted_usd"]) + CAP <= STOP, "first batch exceeds ten-dollar stop")
    require(not any((Path(ledger_root) / "stages" / (batch_stage(i) + ".json")).exists()
                    for i in (0, 1)), "previous stage; no restart")
    seeds = requests.seed_audit(ROOT)
    roots = [Path(__file__), ROOT / "analysis/paper3_retrospective_serial_discovery_audit.py",
             ROOT / "analysis/paper3_retrospective_keyed_discovery_audit.py",
             ROOT / "analysis/paper3_contracts_archive.py", closed.BUDGET / "authority.json",
             ROOT / "tests/test_paper3_retrospective_serial_discovery.py",
             *extra_roots,
             *(ROOT / n for n in proof["source_hashes"])]
    sources = {str(p.relative_to(ROOT)): p.read_text() for p in closure(ROOT, roots)}
    observed = time.time() if metadata_observed_unix is None else metadata_observed_unix
    require(0 <= time.time() - observed <= 3600, "stale prepare metadata")
    protocol = dict(**specification(), integration_only=approval is None,
                    paid_launch_authorized=approval is not None, human_approval=approval,
                    qualification_proof=proof, seed_audit=seeds,
                    pre_stage_budget=before, prior_ledger_entries=prior_inventory(ledger_root),
                    endpoint_metadata=metadata, metadata_observed_unix=observed)
    manifest = dict(protocol=protocol, sources={n: t.sha(s.encode()) for n, s in sources.items()})
    root.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(qualification_archive, root / "qualification.zip")
    for i in (0, 1):
        for name in DIRECTORIES:
            (batch_root(root, i) / name).mkdir(parents=True, exist_ok=False)
    atomic(root / "sources.json", sources)
    atomic(root / "manifest.json", manifest)
    return t.sha(t.canonical(manifest).encode())


def verify(root):
    root = Path(root)
    manifest, sources = t.load(root / "manifest.json"), t.load(root / "sources.json")
    require(set(manifest["sources"]) == set(sources), "source inventory")
    for name, digest in manifest["sources"].items():
        path = Path(name)
        require(not path.is_absolute() and ".." not in path.parts, "unsafe source path")
        require(t.sha((ROOT / path).read_bytes()) == digest == t.sha(sources[name].encode()),
                "frozen source changed: " + name)
    require(all(t.canonical(manifest["protocol"].get(k)) == t.canonical(v)
                for k, v in specification().items()), "protocol changed")
    mode = manifest["protocol"]
    if mode["paid_launch_authorized"] is True:
        check_approval(mode["human_approval"])
        require(mode["integration_only"] is False and
                {"experiments/paper3_retrospective_serial_live.py",
                 "tests/test_paper3_retrospective_serial_live.py"} <= set(sources), "production closure/mode")
    else:
        require(mode["paid_launch_authorized"] is False and mode["integration_only"] is True and
                mode["human_approval"] is None, "fabricated mode changed")
    proof = manifest["protocol"]["qualification_proof"]
    require(t.sha((root / "qualification.zip").read_bytes()) == proof["archive_sha256"], "qualification archive changed")
    require(proof["exact_offline_replay"] is True and proof["new_gate_calls"] == 0 and
            proof["native_configuration_equal"] is True, "qualified flags")
    require(not manifest["protocol"]["seed_audit"]["overlap"], "seed overlap")
    route.check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, batch, ledger_root, *, send, lookup, secret=None, metadata=None,
            clock=time.time, sleep=time.sleep, metadata_observed_unix=None):
    """Injected-transport integration only; no automatic key/network resolution."""
    require(callable(send) and callable(lookup), "explicit test transports required")
    root, local = Path(root), batch_root(root, batch)
    manifest, protocol = verify(root)
    if manifest["protocol"]["paid_launch_authorized"]:
        require(batch in manifest["protocol"]["authorized_paid_batches"],
                "second paid stage requires new human approval and a separate authorization freeze")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(all(not list((local / n).iterdir()) for n in DIRECTORIES), "batch started; no restart")
        if batch == 1:
            previous = audit(root, ledger_root)
            require(previous["batches"][0]["complete"] and not previous["batches"][0]["global_safety_stop"],
                    "previous batch incomplete or failed")
        if manifest["protocol"]["paid_launch_authorized"]:
            require(metadata is not None and metadata_observed_unix is not None, "fresh production metadata required")
        metadata = manifest["protocol"]["endpoint_metadata"] if metadata is None else metadata
        route.check_endpoint(metadata)
        observed = clock() if metadata_observed_unix is None else metadata_observed_unix
        proof = manifest["protocol"]["qualification_proof"]
        require(qualification_proof(root / "qualification.zip", proof["protocol"], proof["archive_sha256"]) == proof,
                "qualification proof changed")
        ledger = StopLedger(ledger_root)
        verify_prior_allowed(ledger_root, manifest["protocol"]["prior_ledger_entries"])
        before = ledger.snapshot()
        require(batch != 0 or before == manifest["protocol"]["pre_stage_budget"], "pre-stage budget changed")
        require(Decimal(before["accounted_usd"]) + CAP <= STOP, "batch cap exceeds ten-dollar stop")
        require(0 <= clock() - observed <= 3600, "stale batch metadata")
        ledger.allocate(batch_stage(batch), CAP)
        atomic(local / "sessions/start.json", dict(protocol=protocol, batch=batch, pid=os.getpid(),
            started_unix=clock(), pre_batch_budget=before, prior_ledger_entries=prior_inventory(ledger_root),
            endpoint_metadata=metadata, metadata_observed_unix=observed))
        calls = transport.Calls(local, ledger_root, batch_stage(batch), lambda: verify(root), score,
                                send=send, lookup=lookup, secret=secret, clock=clock, sleep=sleep)

        def one(assignment):
            terms = [None, None]
            saved = dict(id=assignment["id"], status="not_started", terms=terms, outcome=None)
            if not calls.stop.is_set():
                def on_term(term):
                    terms[term.index] = jsonable(term)
                    atomic(local / "episodes" / (assignment["id"] + ".json"),
                           dict(id=assignment["id"], status="in_progress", terms=terms, outcome=None))

                def ask(actor, identity, term, stage, context, index):
                    result = calls.one(action_call(assignment, actor, identity, term, stage, context, index))
                    if result["status"] != "recorded":
                        raise EpisodeFailure("logical_action_failed")
                    return result["action"]
                try:
                    outcome = institution.episode(assignment["game"], assignment["arm"], ask, on_term)
                    saved.update(status="completed", outcome=jsonable(outcome))
                except EpisodeFailure as exc:
                    saved.update(status="failed", error=str(exc))
                except Exception as exc:
                    calls.halt(assignment["id"], "controller_instrument_error")
                    saved.update(status="instrument_error", error=type(exc).__name__)
            atomic(local / "episodes" / (assignment["id"] + ".json"), saved)
            return dict(id=saved["id"], status=saved["status"])

        assignments = scheduled(batch)
        first = one(assignments[0])
        serial_passed = first["status"] == "completed"
        rest = [one(a) for a in assignments[1:]]
        verify_prior_allowed(ledger_root, manifest["protocol"]["prior_ledger_entries"])
        terminal = dict(protocol=protocol, batch=batch, episodes=[first, *rest], serial_episode_passed=serial_passed,
                        global_safety_stop=calls.stop.is_set(), recovery_count=calls.recoveries,
                        budget=ledger.snapshot(), ended_unix=clock())
        atomic(local / "sessions/terminal.json", terminal)
        return terminal


@cache
def auditor():
    spec = importlib.util.spec_from_file_location("_overload_discovery_audit",
                ROOT / "analysis/paper3_retrospective_serial_discovery_audit.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def audit(root, ledger_root):
    return auditor().audit(root, ledger_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--expected-protocol", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--audit", action="store_true")
    modes.add_argument("--replay", action="store_true")
    parser.add_argument("--ledger-root", type=Path)
    args = parser.parse_args()
    if args.replay:
        result = auditor().replay(args.root, args.expected_protocol)
    else:
        require(args.ledger_root is not None, "explicit ledger path required")
        require(verify(args.root)[1] == args.expected_protocol, "unexpected protocol")
        result = audit(args.root, args.ledger_root)
    print(json.dumps(jsonable(result), indent=2))


if __name__ == "__main__":
    main()
