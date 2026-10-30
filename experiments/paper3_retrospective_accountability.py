"""Joint qualification and two-term accountability discovery; no automatic successor.

18 serial competence calls, one serial 30-action completion check, then at
most four workers. Every assignment/failure is retained. No model retries,
output repair, role replacement, provider fallback or restart after admission.
"""
# ruff: noqa: E402
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import fcntl
from functools import cache
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import paper3_transport_diagnostic as t
from paper3 import hosted_reasoning_channel_calls as service
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_interface as interface
from paper3 import retrospective_qualification as qualification
from paper3 import retrospective_requests as requests
from paper3.retrospective_execution import StopLedger, jsonable, prior_inventory, verify_prior
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure

STAGE = "pivot_b_retrospective_accountability_v1"
BUDGET = ROOT / "results/paper3/pivot_b_budget"
WORKERS = 4
MAX_CALLS = 498
CONFIG = dict(models=[requests.MODEL, requests.MODEL_ALIAS], provider=requests.PROVIDER,
              output_bound=requests.OUTPUT_BOUND)
require = t.require


class EpisodeFailure(ValueError):
    pass


@cache
def gate_cases():
    return {row["id"]: row for row in qualification.cases()}


def pack_call(key, value, context):
    reservation = requests.reservation(value)
    return dict(id=key, request=value, context=context, **reservation,
                request_sha256=t.sha(reservation["request_text"].encode()))


@cache
def gate_calls():
    return tuple(pack_call("gate-" + row["id"], row["request"],
                            dict(kind="qualification", case_id=row["id"]))
                 for row in requests.gate_requests())


def action_call(assignment, actor, identity, term, stage, context, index):
    value = requests.action_request(assignment, actor, identity, term, stage, context, index)
    result = pack_call(assignment["id"] + f"-{index:02d}", value,
                       dict(kind="action", assignment_id=assignment["id"], actor=actor,
                            identity=identity, term=term, stage=stage, index=index))
    bound = next(row for row in requests.legal_history_bounds()["assignments"]
                 if row["id"] == assignment["id"])["input_bounds"][index]
    require(result["input_token_bound"] <= bound, "actual history exceeds frozen bound")
    return result


def score(row, case):
    result = dict(usable=False, valid_action=False, exact=False, native_reasoning=None,
                  action=None, failure="instrument_or_unfinished")
    if row.get("instrument_error") or "assessment" not in row:
        return result
    assessment = service.assess(row, CONFIG)
    stream = assessment["stream"]
    native = service.native_evidence(stream)
    usable = (assessment["passed"] and stream["finish_reasons"] == ["tool_calls"] and
              native["present"] and row["request"]["reasoning"] == dict(enabled=True, exclude=False))
    result.update(usable=usable, native_reasoning=native)
    if not usable:
        result["failure"] = "transport_reasoning_or_function_completion"
        return result
    if case["context"]["kind"] == "qualification":
        result.update(qualification.score(gate_cases()[case["context"]["case_id"]], row["stream"]))
    else:
        try:
            assignment = next(value for value in requests.assignments()
                              if value["id"] == case["context"]["assignment_id"])
            action = interface.decode(assignment["game"], case["context"]["stage"], row["stream"])
            result.update(valid_action=True, exact=True, action=action, failure=None)
        except (ValueError, KeyError, TypeError) as exc:
            result["failure"] = str(exc)
    return result


def seed_audit(root=ROOT):
    planned = {qualification.FRAME_SEED, requests.ORDER_SEED, *requests.FRAME_SEEDS,
               *(requests.GATE_SEED_BASE + i for i in range(18)),
               *(row["seed_base"] + i for row in requests.assignments() for i in range(30))}
    observed, inventory = set(), []

    def walk(value, key=""):
        if type(value) is dict:
            for name, child in value.items():
                walk(child, name)
        elif type(value) is list:
            for child in value:
                walk(child, key)
        elif type(value) is int and "seed" in key.lower():
            observed.add(value)

    for base, dirs, files in os.walk(Path(root) / "results/paper3"):
        dirs[:] = [name for name in dirs if not any(fragment in name for fragment in
                   ("portable", "bundle", "export", "replay", "__pycache__", "code"))]
        for name in files:
            path = Path(base) / name
            if name == "manifest.json" or (path.parent.name == "calls" and name.endswith(".json")):
                value = t.load(path)
                walk(value.get("request", value) if path.parent.name == "calls" else value)
                inventory.append((str(path.relative_to(root)), t.sha(path.read_bytes())))
    require(not planned & observed, "historical frame/request seed collision")
    return dict(planned=sorted(planned), overlap=[], historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()))


@cache
def specification():
    return jsonable(dict(name=STAGE, max_calls=MAX_CALLS, workers=WORKERS,
        cap_usd=str(requests.CAP), cumulative_stop_usd=str(requests.STOP), configuration=CONFIG,
        qualification_calls=gate_calls(), pairs=requests.pairs(), assignments=requests.assignments(),
        bound_proof=requests.legal_history_bounds(),
        seeds=dict(frame=requests.FRAME_SEEDS, qualification_frame=qualification.FRAME_SEED,
                   gate_base=requests.GATE_SEED_BASE, decision_base=requests.DECISION_SEED_BASE,
                   order=requests.ORDER_SEED, deliberate_pairing="same 30 per-stage seeds within each block"),
        interface="server auto; client exactly one submit_decision function; no prose fallback",
        inference_retries=0, receipt_offsets_seconds=[0, 20, 40, 60],
        gate="All eighteen exact/valid with complete native reasoning and certified billing; then one complete serial episode before four workers.",
        failure="Any unusable, invalid, factually wrong, uncertified or over-budget call stops new admissions. Retain all assignments and partial terms. Never restart.",
        scientific_screen="Two-sided: all sixteen episodes complete and qualified; both matched-block conflict-minus-aligned interactions have same nonzero sign; absolute mean >=0.04 normalized regret; mean absolute aligned interaction <= half conflict.",
        limitations="Two opportunity-conditioned blocks, one trajectory and model route; conditional support benchmark is not an equilibrium prediction. A lead only proposes independent validation, never publication evidence."))


def prepare(root, metadata=None, ledger_root=BUDGET):
    root = Path(root)
    require(not root.exists(), "fresh run directory required")
    seeds = seed_audit()
    if metadata is None:
        with t.opener().open(requests.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    requests.check_endpoint(metadata)
    budget = Ledger(ledger_root).snapshot()
    require(Decimal(budget["accounted_usd"]) + requests.CAP <= requests.STOP,
            "stage cap exceeds eight-dollar stop")
    entries = prior_inventory(ledger_root)
    roots = [Path(__file__), ROOT / "analysis/paper3_retrospective_accountability_audit.py",
             ROOT / "analysis/paper3_contracts_archive.py", BUDGET / "authority.json",
             *(ROOT / "tests" / ("test_paper3_retrospective_" + name + ".py") for name in
               ("accountability", "electorates", "interface", "qualification", "readout", "requests", "runner"))]
    snapshot = {str(path.relative_to(ROOT)): path.read_text() for path in closure(ROOT, roots)}
    protocol = dict(**specification(), seed_audit=seeds, pre_stage_budget=budget,
                    prior_ledger_entries=entries, endpoint_metadata=metadata,
                    metadata_observed_unix=time.time())
    manifest = dict(protocol=protocol, sources={key: t.sha(value.encode()) for key, value in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    for name in ("calls", "decisions", "episodes", "sessions"):
        (root / name).mkdir()
    atomic(root / "sources.json", snapshot)
    atomic(root / "manifest.json", manifest)
    return t.sha(t.canonical(manifest).encode())


def verify(root, code_root=ROOT):
    manifest, snapshot = t.load(Path(root) / "manifest.json"), t.load(Path(root) / "sources.json")
    require(set(snapshot) == set(manifest["sources"]), "source inventory")
    for relative, sha in manifest["sources"].items():
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts, "unsafe source path")
        require(t.sha((Path(code_root) / path).read_bytes()) == t.sha(snapshot[relative].encode()) == sha,
                "frozen source changed: " + relative)
    require(all(t.canonical(manifest["protocol"].get(key)) == t.canonical(value)
                for key, value in specification().items()), "protocol changed")
    requests.check_endpoint(manifest["protocol"]["endpoint_metadata"])
    require(not manifest["protocol"]["seed_audit"]["overlap"], "seed overlap")
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, ledger_root=BUDGET, secret=None, send=None, lookup=None, clock=time.time, sleep=time.sleep):
    root = Path(root)
    manifest, protocol = verify(root)
    require(0 <= clock() - manifest["protocol"]["metadata_observed_unix"] <= 3600, "stale metadata")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(all(not list((root / name).iterdir()) for name in ("calls", "decisions", "episodes", "sessions")),
                "already started; no restart")
        ledger = StopLedger(ledger_root)
        require(ledger.snapshot() == manifest["protocol"]["pre_stage_budget"], "pre-stage accounting changed")
        verify_prior(ledger_root, manifest["protocol"]["prior_ledger_entries"], STAGE)
        ledger.allocate(STAGE, requests.CAP)
        atomic(root / "sessions/start.json", dict(protocol=protocol, pid=os.getpid(), started_unix=clock()))
        calls = service.Calls(root, ledger_root, STAGE, MAX_CALLS, lambda: verify(root), score,
                              CONFIG, secret, send, lookup, clock, sleep)
        calls.ledger = ledger

        def decide(call):
            path = root / "decisions" / (call["id"] + ".json")
            atomic(path, dict(case=call, result=dict(id=call["id"], status="prepared")))
            result = calls.one(call)
            atomic(path, dict(case=call, result=result))
            if result["status"] != "recorded":
                calls.stop.set()
                raise EpisodeFailure("request_not_recorded")
            row = t.load(root / "calls" / (call["id"] + ".json"))
            if not (row["result"]["usable"] and row["result"]["valid_action"] and
                    row["result"]["exact"] and row["assessment"]["receipt_certified"]):
                calls.stop.set()
                raise EpisodeFailure("unusable_invalid_inexact_or_uncertified")
            return row["result"]["action"]

        qualification_results = []
        for call in gate_calls():
            if calls.stop.is_set():
                qualification_results.append(dict(id=call["id"], status="not_started"))
            else:
                try:
                    decide(call)
                    status = "passed"
                except EpisodeFailure:
                    status = "failed"
                except Exception:
                    calls.stop.set()
                    status = "instrument_error"
                qualification_results.append(dict(id=call["id"], status=status))
        qualified = all(row["status"] == "passed" for row in qualification_results)
        atomic(root / "sessions/qualification.json", dict(protocol=protocol, results=qualification_results,
                                                          passed=qualified))

        def one(assignment):
            terms = [None, None]
            saved = dict(id=assignment["id"], status="not_started", terms=terms, outcome=None)
            if not calls.stop.is_set() and qualified:
                def on_term(term):
                    terms[term.index] = jsonable(term)
                    atomic(root / "episodes" / (assignment["id"] + ".json"),
                           dict(id=assignment["id"], status="in_progress", terms=terms, outcome=None))
                def ask(actor, identity, term, stage, context, index):
                    return decide(action_call(assignment, actor, identity, term, stage, context, index))
                try:
                    outcome = institution.episode(assignment["game"], assignment["arm"], ask, on_term)
                    saved.update(status="completed", outcome=jsonable(outcome))
                except EpisodeFailure as exc:
                    saved.update(status="failed", error=str(exc))
                except Exception as exc:
                    calls.stop.set()
                    saved.update(status="instrument_error", error=type(exc).__name__)
            atomic(root / "episodes" / (assignment["id"] + ".json"), saved)
            print(json.dumps(dict(event="accountability_episode_terminal", id=saved["id"],
                                  status=saved["status"])), flush=True)
            return dict(id=saved["id"], status=saved["status"])

        scheduled = requests.assignments()
        first = one(scheduled[0])
        serial_passed = first["status"] == "completed"
        if qualified and serial_passed and not calls.stop.is_set():
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                rest = list(pool.map(one, scheduled[1:]))
        else:
            rest = [one(assignment) for assignment in scheduled[1:]]
        verify_prior(ledger_root, manifest["protocol"]["prior_ledger_entries"], STAGE)
        terminal = dict(protocol=protocol, qualification=qualification_results, qualified=qualified,
                        episodes=[first, *rest], serial_episode_passed=serial_passed,
                        global_safety_stop=calls.stop.is_set(), transport_failures=calls.transport_failures,
                        budget=ledger.snapshot(), ended_unix=clock())
        atomic(root / "sessions/terminal.json", terminal)
        return terminal


@cache
def offline_module(relative):
    """Load explicit frozen tools without Paper 1's scientific package imports."""
    require(relative in ("analysis/paper3_retrospective_accountability_audit.py",
                         "analysis/paper3_contracts_archive.py"), "undeclared offline tool")
    name = "_retrospective_" + Path(relative).stem
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def audit(root, ledger_root=BUDGET):
    return offline_module("analysis/paper3_retrospective_accountability_audit.py").audit(root, ledger_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    for name in ("prepare", "run", "audit", "export", "replay"):
        mode.add_argument("--" + name, action="store_true")
    parser.add_argument("--expected-protocol")
    parser.add_argument("--target", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.prepare:
        print(json.dumps(dict(protocol=prepare(args.root))))
        return
    require(args.expected_protocol, "expected protocol required")
    if args.replay:
        result = offline_module("analysis/paper3_retrospective_accountability_audit.py").replay(
            args.root, args.expected_protocol)
    else:
        require(verify(args.root)[1] == args.expected_protocol, "unexpected protocol")
        if args.export:
            require(args.target and args.archive, "archive paths required")
            result = offline_module("analysis/paper3_retrospective_accountability_audit.py").export(
                args.root, BUDGET, args.target, args.archive, t.read_key())
        else:
            result = audit(args.root) if args.audit else execute(args.root, secret=t.read_key())
    print(json.dumps(jsonable(result), indent=2))


if __name__ == "__main__":
    main()
