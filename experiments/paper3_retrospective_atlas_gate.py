"""Fixed keyed accountability alternative-provider qualification only.

18 serial calls, $0.25 cap within the shared $8 conservative admission stop; original total authority remains $10. No inference
retry, repair, fallback, inherited pass, replacement case or automatic pilot.
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
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import paper3_transport_diagnostic as t
from paper3 import hosted_reasoning_channel_calls as service
from paper3 import retrospective_atlas_qualification as qualification
from paper3 import retrospective_atlas_route as route
from paper3.pivot_b_budget import Ledger, atomic
from paper3.retrospective_execution import StopLedger, jsonable, prior_inventory, verify_prior
from paper3.source_closure import closure

STAGE = "pivot_b_retrospective_atlas_gate_v1"
CAP = Decimal(".25")
BUDGET = ROOT / "results/paper3/pivot_b_budget"
CONFIG = dict(models=[route.MODEL, route.MODEL_ALIAS], provider=route.PROVIDER,
              output_bound=route.OUTPUT_BOUND)
require = t.require


@cache
def cases():
    return tuple(dict(**row, **(bound := route.reservation(row["request"])),
                      request_sha256=t.sha(bound["request_text"].encode()))
                 for row in route.requests())


def score(row, case):
    result = dict(usable=False, valid_action=False, exact=False,
                  native_reasoning=None, action=None, failure="instrument_or_unfinished")
    if row.get("instrument_error") or "assessment" not in row:
        return result
    assessed = service.assess(row, CONFIG)
    native = service.native_evidence(assessed["stream"])
    usable = (assessed["passed"] and assessed["stream"]["finish_reasons"] == ["tool_calls"]
              and native["present"] and row["request"]["reasoning"] == dict(enabled=True, exclude=False))
    result.update(usable=usable, native_reasoning=native)
    if usable:
        context = next(item for item in qualification.cases() if item["id"] == case["context"]["case_id"])
        result.update(qualification.score(context, row["stream"]))
    else:
        result["failure"] = "transport_reasoning_or_function_completion"
    return result


def seed_audit(root=ROOT):
    planned = {qualification.FRAME_SEED, *(route.SEED_BASE + i for i in range(18))}
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
    reserve = sum(Decimal(row["reserved_usd"]) for row in cases())
    require(len(cases()) == 18 and reserve <= CAP, "qualification call/cap bound")
    return jsonable(dict(name=STAGE, max_calls=18, workers=1, cap_usd=str(CAP),
        cumulative_stop_usd=str(route.STOP), frame_seed=qualification.FRAME_SEED,
        seed_base=route.SEED_BASE, configuration=CONFIG, cases=cases(),
        approval=dict(source="direct human user message", response="ok do it approved", date="2026-10-01", thread_id="01a09ba8-a109-7b62-a8a0-61519cfdea84", scope="Small alternative-provider reliability/native qualification only; cap0.25, no institutional allocation"),
        case_reuse=dict(source="keyed qualification generator", fresh_frame=True, no_inherited_pass=True),
        prior_failure="Retain closed serial DeepInfra FP4 partial-stream failure; its underlying cause is unknown.",
        selection="AtlasCloud FP8 selected prospectively for full parameter compatibility and equal advertised prices. Not claimed more reliable; quantization/provider both change, so no isolated provider effect.",
        expected_cases=qualification.cases(), full_reservation_usd=str(reserve),
        gate="All eighteen exact factual reports or legal actions, complete native reasoning, pinned route and certified billing.",
        failure="Stop serial admission on the first failure. No inference retries, repair, replacement, fallback or automatic bargaining run.",
        interface="Same keyed payoff cards/common verified district sums, zero-based IDs and own-ballot semantics; one valid automatic tool call, no prose fallback.",
        limitations="Prospective provider/quantization qualification on one fresh selected frame, twelve facts and six legal actions. Eighteen calls cannot establish long-run reliability. Not a randomized provider effect, strategic result, population evidence or publication evidence. No automatic institutional successor."))


def prepare(root, metadata=None, ledger_root=BUDGET):
    root = Path(root)
    require(not root.exists(), "fresh run directory required")
    seeds = seed_audit()
    if metadata is None:
        with t.opener().open(route.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    route.check_endpoint(metadata)
    before = Ledger(ledger_root).snapshot()
    require(Decimal(before["accounted_usd"]) + CAP <= route.STOP, "eight-dollar authority exceeded")
    roots = [Path(__file__), ROOT / "analysis/paper3_contracts_archive.py", BUDGET / "authority.json",
             ROOT / "tests/test_paper3_retrospective_keyed_interface.py",
             ROOT / "tests/test_paper3_retrospective_atlas_gate.py"]
    snapshot = {str(path.relative_to(ROOT)): path.read_text() for path in closure(ROOT, roots)}
    protocol = dict(**specification(), seed_audit=seeds, pre_stage_budget=before,
                    prior_ledger_entries=prior_inventory(ledger_root), endpoint_metadata=metadata,
                    metadata_observed_unix=time.time())
    manifest = dict(protocol=protocol, sources={name: t.sha(value.encode()) for name, value in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    for name in ("calls", "sessions"):
        (root / name).mkdir()
    atomic(root / "sources.json", snapshot)
    atomic(root / "manifest.json", manifest)
    return t.sha(t.canonical(manifest).encode())


def verify(root):
    manifest, sources = t.load(Path(root) / "manifest.json"), t.load(Path(root) / "sources.json")
    require(set(manifest["sources"]) == set(sources), "source inventory")
    for name, digest in manifest["sources"].items():
        path = Path(name)
        require(not path.is_absolute() and ".." not in path.parts, "unsafe source path")
        require(t.sha((ROOT / path).read_bytes()) == digest == t.sha(sources[name].encode()),
                "frozen source changed: " + name)
    require(all(t.canonical(manifest["protocol"].get(key)) == t.canonical(value)
                for key, value in specification().items()), "protocol changed")
    require(not manifest["protocol"]["seed_audit"]["overlap"], "seed overlap")
    route.check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, ledger_root=BUDGET, secret=None, send=None, lookup=None, clock=time.time, sleep=time.sleep):
    root = Path(root)
    manifest, protocol = verify(root)
    require(0 <= clock() - manifest["protocol"]["metadata_observed_unix"] <= 3600, "stale metadata")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not list((root / "calls").iterdir()) and not list((root / "sessions").iterdir()),
                "already started; never restart")
        ledger = StopLedger(ledger_root)
        require(ledger.snapshot() == manifest["protocol"]["pre_stage_budget"], "pre-stage budget changed")
        verify_prior(ledger_root, manifest["protocol"]["prior_ledger_entries"], STAGE)
        ledger.allocate(STAGE, CAP)
        atomic(root / "sessions/start.json", dict(pid=os.getpid(), protocol=protocol, started_unix=clock()))
        calls = service.Calls(root, ledger_root, STAGE, 18, lambda: verify(root), score,
                              CONFIG, secret, send, lookup, clock, sleep)
        calls.ledger = ledger
        results = []
        for case in cases():
            result = calls.one(case)
            results.append(result)
            if result["status"] == "recorded":
                row = t.load(root / "calls" / (case["id"] + ".json"))
                if not all(row["result"][field] for field in ("usable", "valid_action", "exact")):
                    calls.stop.set()
            elif result["status"] != "not_started":
                calls.stop.set()
        verify_prior(ledger_root, manifest["protocol"]["prior_ledger_entries"], STAGE)
        terminal = dict(protocol=protocol, results=results, global_safety_stop=calls.stop.is_set(),
                        budget=ledger.snapshot(), ended_unix=clock())
        atomic(root / "sessions/terminal.json", terminal)
        return terminal


def _audit_locked(root, ledger_root):
    root, ledger_root = Path(root), Path(ledger_root)
    manifest, protocol = verify(root)
    terminal = t.load(root / "sessions/terminal.json")
    require(t.load(root / "sessions/start.json")["protocol"] == terminal["protocol"] == protocol,
            "terminal protocol")
    verify_prior(ledger_root, manifest["protocol"]["prior_ledger_entries"], STAGE)
    reports, cost = service.audit_records(root, ledger_root, STAGE, protocol, cases(), terminal, score, CONFIG)
    physical = sorted((t.load(p) for p in (root / "calls").glob("*.json")), key=lambda row: row["admitted_unix"])
    require(all(a["ended_unix"] <= b["admitted_unix"] for a, b in zip(physical, physical[1:])), "serial request overlap")
    require([row["id"] for row in physical] == [case["id"] for case in cases()[:len(physical)]], "nonprefix physical calls")
    failed = False
    for report in reports:
        if failed:
            require(report["status"] == "not_started", "serial admission continued after failure")
        valid = (report["status"] == "recorded" and report["result"] and
                 all(report["result"][field] for field in ("usable", "valid_action", "exact")))
        failed |= not valid
    ledger = Ledger(ledger_root)
    entries = ledger._entries()
    used = ledger._total(entries)
    authority = t.load(ledger_root / "authority.json")
    budget = dict(budget_id=authority["budget_id"], cap_usd=authority["cap_usd"],
                  accounted_usd=str(used), remaining_usd=str(Decimal(authority["cap_usd"]) - used),
                  entries=len(entries), pending=sum(row["status"] != "settled" for row in entries),
                  uncertified=sum(row.get("certified") is False for row in entries))
    require(budget == terminal["budget"], "terminal budget changed")
    require(cost <= CAP and Decimal(budget["accounted_usd"]) <= route.STOP, "budget authority exceeded")
    passed = not failed and not terminal["global_safety_stop"]
    return dict(protocol=protocol, assignments=reports, calls=len(list((root / "calls").glob("*.json"))),
                gate_passed=passed, verdict="qualification_passed" if passed else "qualification_failed",
                accounted_usd=str(cost), cumulative_accounted_usd=budget["accounted_usd"],
                global_safety_stop=terminal["global_safety_stop"], publication_evidence=False,
                limitations=specification()["limitations"])


def audit(root, ledger_root=BUDGET):
    with Ledger(ledger_root).locked():
        return _audit_locked(root, ledger_root)


@cache
def archive_helper():
    spec = importlib.util.spec_from_file_location("_deepseek_gate_archive", ROOT / "analysis/paper3_contracts_archive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def export(root, ledger_root, target, destination, secret=None):
    root, ledger_root, target = (Path(path).resolve() for path in (root, ledger_root, target))
    helper = archive_helper()
    require(not target.exists() and not Path(destination).exists(), "archive destination exists")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with Ledger(ledger_root).locked():
            report = _audit_locked(root, ledger_root)
            contents = {"code/" + name: value.encode() for name, value in t.load(root / "sources.json").items()}
            for prefix, directory in (("run", root), ("ledger", ledger_root)):
                for path in directory.rglob("*"):
                    require(not path.is_symlink(), "symlink in archive")
                    if path.is_file() and path.suffix == ".json":
                        contents[prefix + "/" + str(path.relative_to(directory))] = path.read_bytes()
            contents["expected_report.json"] = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = ("# DeepSeek fixed-interface qualification\n\n"
        "A gate is not an institutional finding. All failures remain. Fresh replay: "
        "`python3 -I -S code/experiments/paper3_retrospective_atlas_gate.py . --replay "
        "--expected-protocol " + report["protocol"] + "`.\n").encode()
    for name, value in contents.items():
        helper.safe(target, name)
        helper.credentials(value, secret)
    metadata = dict(format=helper.FORMAT, experiment_family=STAGE, protocol=report["protocol"],
                    files={name: t.sha(value) for name, value in sorted(contents.items())})
    target.mkdir(parents=True, exist_ok=False)
    for name, value in contents.items():
        path = helper.safe(target, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(value)
    with (target / "bundle.json").open("x") as stream:
        json.dump(metadata, stream, sort_keys=True, indent=2)
    return dict(protocol=report["protocol"], files=len(contents), sha256=helper.archive(target, destination))


def replay(root, expected_protocol):
    root, helper = Path(root).resolve(), archive_helper()
    metadata = helper.verify_bundle(root, expected_protocol)
    require(metadata["experiment_family"] == STAGE and ROOT == root / "code", "isolated gate code required")
    sys.addaudithook(helper.offline_guard)
    report = audit(root / "run", root / "ledger")
    require(t.canonical(report) == t.canonical(t.load(root / "expected_report.json")), "replay report changed")
    return dict(**report, portable_replay=dict(exact_report_match=True, protocol=expected_protocol))


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
        result = dict(protocol=prepare(args.root))
    else:
        require(args.expected_protocol, "expected protocol required")
        if args.replay:
            result = replay(args.root, args.expected_protocol)
        else:
            require(verify(args.root)[1] == args.expected_protocol, "unexpected protocol")
            if args.run:
                result = execute(args.root, secret=t.read_key())
            elif args.audit:
                result = audit(args.root)
            else:
                require(args.target and args.archive, "archive paths required")
                result = export(args.root, BUDGET, args.target, args.archive, t.read_key())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

