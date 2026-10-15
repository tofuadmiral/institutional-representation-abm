"""Prospective Qwen route-jurisdiction prerequisite, not a pilot result.

The prior Qwen3.5 route gate remains failed. This new native-reasoning
Qwen3-32B interface clarifies the legal-veto question and projects only
declared action fields. All twelve cases must pass before a distinct
institutional pilot may be considered. No retry, repair, replacement,
fallback, local model, or restart of a started run.
"""
# ruff: noqa: E402
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import paper3_electoral_accountability_pilot as channel
from paper3 import hosted_reasoning_channel_calls as service
from paper3 import route_jurisdiction_gate_v2 as gate
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure

t = channel.t
require = t.require
STAGE = "pivot_b_route_qwen_gate_v2"
CAP = Decimal("0.15")
STOP = Decimal("8")
SEED_BASE = 9400000
MAX_CALLS = 12
WORKERS = 2
BUDGET = channel.BUDGET
CONFIG = channel.CONFIG
PRIOR_ROOT = ROOT / "results/paper3/pivot_b_electoral_controlled_opportunity_v1"
PRIOR_EXPORT = ROOT / "results/paper3/pivot_b_electoral_controlled_opportunity_v1_export"
PRIOR_PROTOCOL = "98b0232fec7c4e22a7447f159d0d36eb7236427512da1d3f1c37a516fdfe65f2"
FAILED_ROUTE_EXPORT = ROOT / "results/paper3/pivot_b_route_gate_v1_bundle"
FAILED_ROUTE_PROTOCOL = "cc7ad27752fbe05cb04a4fb75df5150bb3f95bccefde9e4699905ee8f31370f2"


def cases():
    result = []
    for index, context in enumerate(gate.cases()):
        request = channel.request(context["messages"], SEED_BASE + index)
        reserve = channel.reservation(request)
        result.append(dict(id=context["name"],
                           context={key: value for key, value in context.items()
                                    if key != "messages"} | {"seed": SEED_BASE + index},
                           request=request, request_text=reserve["wire"],
                           request_sha256=t.sha(reserve["wire"].encode()),
                           input_token_bound=reserve["input_token_bound"],
                           reserved_usd=reserve["reserved_usd"]))
    require(len(result) == MAX_CALLS and len({row["id"] for row in result}) == MAX_CALLS,
            "gate case inventory")
    require(sum(Decimal(row["reserved_usd"]) for row in result) <= CAP,
            "full-case gate reservation exceeds cap")
    return result


def preflight():
    rows = cases()
    return dict(intended_calls=MAX_CALLS,
                full_case_reservation_usd=str(sum(Decimal(row["reserved_usd"])
                                                  for row in rows)),
                max_input_bound=max(row["input_token_bound"] for row in rows),
                cap_usd=str(CAP))


def score(row, case):
    result = dict(usable=False, valid_action=False, exact=False,
                  native_reasoning=None, reply=None, failure=None)
    if row.get("instrument_error") or "assessment" not in row:
        result["failure"] = "instrument_or_unfinished"
        return result
    assessed = service.assess(row, CONFIG)
    stream = assessed["stream"]
    native = service.native_evidence(stream)
    usable = (assessed["passed"] and stream["finish_reasons"] == ["stop"] and
              native["present"] and row["request"].get("reasoning") ==
              dict(enabled=True, exclude=False))
    result.update(usable=usable, native_reasoning=native)
    if not usable:
        result["failure"] = "transport_reasoning_or_completion"
        return result
    assessed_content = gate.score(row["final_content"], case["context"])
    result.update(valid_action=assessed_content["status"] == "completed",
                  exact=assessed_content["exact"],
                  reply=assessed_content.get("reply"),
                  failure=assessed_content.get("error"))
    return result


def seed_audit(root=ROOT):
    planned = set(range(SEED_BASE, SEED_BASE + MAX_CALLS))
    observed, inventory = set(), []

    def walk(value, key=""):
        if isinstance(value, dict):
            for name, child in value.items():
                walk(child, name)
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif type(value) is int and "seed" in key.lower():
            observed.add(value)

    for base_dir, dirs, files in os.walk(Path(root) / "results/paper3"):
        dirs[:] = [name for name in dirs if not any(fragment in name for fragment in
                   ("portable", "bundle", "export", "replay", "__pycache__", "code"))]
        for name in files:
            path = Path(base_dir) / name
            if name != "manifest.json" and not (path.parent.name == "calls" and
                                                 name.endswith(".json")):
                continue
            value = t.load(path)
            walk(value.get("request", value) if path.parent.name == "calls" else value)
            inventory.append((str(path.relative_to(root)), t.sha(path.read_bytes())))
    require(not planned & observed, "historical request seed overlap")
    return dict(planned_unique=sorted(planned), overlap=[],
                historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()))


def prior_done():
    require((PRIOR_ROOT / "sessions/terminal.json").is_file() and
            (PRIOR_EXPORT / "bundle.json").is_file() and
            (FAILED_ROUTE_EXPORT / "bundle.json").is_file(),
            "prior runs not terminal/archived")
    helper = channel.archive_source.archive_helpers()
    require(helper.verify_bundle(PRIOR_EXPORT, PRIOR_PROTOCOL)["experiment_family"] ==
            "pivot_b_electoral_controlled_opportunity_v1", "prior archive changed")
    require(helper.verify_bundle(FAILED_ROUTE_EXPORT, FAILED_ROUTE_PROTOCOL)[
            "experiment_family"] == "pivot_b_route_gate_v1",
            "failed route archive changed")
    report = t.load(PRIOR_EXPORT / "expected_report.json")
    old_report = t.load(FAILED_ROUTE_EXPORT / "expected_report.json")
    require(report["protocol"] == PRIOR_PROTOCOL and
            report["discovery_screen"]["selected_case_lead"] is False and
            old_report["protocol"] == FAILED_ROUTE_PROTOCOL and
            old_report["gate_passed"] is False,
            "historical result identity")
    return dict(prior_protocol=PRIOR_PROTOCOL,
                prior_report_sha256=t.sha(t.canonical(report).encode()),
                failed_route_protocol=FAILED_ROUTE_PROTOCOL,
                failed_route_report_sha256=t.sha(t.canonical(old_report).encode()))


def specification():
    return dict(name=STAGE, cases=cases(), workers=WORKERS,
                max_calls=MAX_CALLS, cap_usd=str(CAP),
                conservative_budget_stop_usd=str(STOP),
                model_configuration=CONFIG, seed_base=SEED_BASE,
                preflight=preflight(),
                gate_rule="All 12 cases must have usable native-reasoning answers, valid projected fields, exact facts/selected actions and billing-certified receipts. Stop new admissions on the first wrong or invalid answer; already admitted requests finish. This qualifies an interface, not a treatment effect.",
                interface_change="New Qwen3-32B/DeepInfra FP8 route and native JSON-object output, 16,384-token completion cap, explicit review_veto_applies legal-authority question replacing ambiguous review_binding, and prospective projection onto declared action fields. The old Qwen3.5 route-gate score remains failed and unchanged.",
                failure_rule="Two transport/accounting failures or any identity/source/credential/budget/instrument breach stop admissions. No inference retry, response repair, replacement, model fallback or restart.",
                limitations="A passing gate shows selected rule arithmetic and legal actions only. It cannot establish strategic competence, institutional behavior, generality or a Paper 3 finding. A larger pilot needs its own design, freeze and cost cap.")


def prepare(root, metadata=None, ledger_root=BUDGET):
    root = Path(root)
    require(not root.exists(), "fresh route-gate directory required")
    prior = prior_done()
    inherited = channel.prerequisite()
    seeds = seed_audit()
    if metadata is None:
        with t.opener().open(channel.gate.channel.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    channel.check_endpoint(metadata)
    budget = Ledger(ledger_root).snapshot()
    require(budget["pending"] == 0 and
            Decimal(budget["accounted_usd"]) + CAP < STOP,
            "pre-stage conservative $8 stop")
    paths = closure(ROOT, [Path(__file__),
                           ROOT / "analysis/paper3_contracts_archive.py",
                           ROOT / "tests/test_paper3_route_qwen_gate_v2.py",
                           BUDGET / "authority.json"])
    snapshot = {str(path.relative_to(ROOT)): path.read_text() for path in paths}
    protocol = dict(**specification(), prior_terminal_archives=prior,
                    inherited_prerequisite=inherited, seed_audit=seeds,
                    pre_stage_budget=budget, endpoint_metadata=metadata,
                    metadata_observed_unix=time.time())
    manifest = dict(protocol=protocol,
                    sources={name: t.sha(value.encode())
                             for name, value in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    for name in ("calls", "sessions"):
        (root / name).mkdir()
    atomic(root / "sources.json", snapshot)
    atomic(root / "manifest.json", manifest)
    return t.sha(t.canonical(manifest).encode())


def verify(root, code_root=ROOT):
    root = Path(root)
    manifest, snapshot = t.load(root / "manifest.json"), t.load(root / "sources.json")
    require(set(snapshot) == set(manifest["sources"]), "source inventory")
    for relative, expected in manifest["sources"].items():
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts,
                "unsafe frozen source")
        require(t.sha((Path(code_root) / path).read_bytes()) ==
                t.sha(snapshot[relative].encode()) == expected,
                "frozen route-gate source changed: " + relative)
    require(all(manifest["protocol"].get(key) == value
                for key, value in specification().items()),
            "route-gate specification changed")
    require(manifest["protocol"]["prior_terminal_archives"][
            "failed_route_protocol"] == FAILED_ROUTE_PROTOCOL and
            manifest["protocol"]["inherited_prerequisite"]["native_template"] ==
            channel.request([], 0) and
            manifest["protocol"]["seed_audit"]["planned_unique"] ==
            list(range(SEED_BASE, SEED_BASE + MAX_CALLS)) and
            not manifest["protocol"]["seed_audit"]["overlap"],
            "history/config/seed inventory changed")
    channel.check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, ledger_root=BUDGET, secret=None, send=None, lookup=None,
            clock=time.time, sleep=time.sleep):
    root = Path(root)
    manifest, protocol = verify(root)
    require(prior_done() == manifest["protocol"]["prior_terminal_archives"] and
            channel.prerequisite() == manifest["protocol"]["inherited_prerequisite"],
            "prerequisite changed")
    require(0 <= clock() - manifest["protocol"]["metadata_observed_unix"] <= 3600,
            "stale endpoint metadata")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not list((root / "sessions").iterdir()) and
                not list((root / "calls").iterdir()),
                "already started; no restart")
        ledger = Ledger(ledger_root)
        require(ledger.snapshot() == manifest["protocol"]["pre_stage_budget"],
                "shared budget changed since freeze")
        ledger.allocate(STAGE, CAP)
        atomic(root / "sessions/start.json", dict(protocol=protocol,
                                                  pid=os.getpid(),
                                                  started_unix=clock()))
        calls = service.Calls(root, ledger_root, STAGE, MAX_CALLS,
                              lambda: verify(root), score, CONFIG, secret,
                              send, lookup, clock, sleep)

        def one(case):
            result = calls.one(case)
            if result["status"] == "recorded":
                saved = t.load(root / "calls" / (case["id"] + ".json"))
                finding = saved["result"]
                if not (finding["usable"] and finding["valid_action"] and
                        finding["exact"]):
                    calls.stop.set()
            return result

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(one, manifest["protocol"]["cases"]))
        terminal = dict(protocol=protocol, results=results,
                        global_safety_stop=calls.stop.is_set(),
                        transport_failures=calls.transport_failures,
                        budget=ledger.snapshot(), ended_unix=clock())
        atomic(root / "sessions/terminal.json", terminal)
        return terminal


def audit(root, ledger_root=BUDGET):
    root = Path(root)
    manifest, protocol = verify(root)
    terminal = t.load(root / "sessions/terminal.json")
    require(t.load(root / "sessions/start.json")["protocol"] ==
            terminal["protocol"] == protocol, "terminal protocol")
    assigned = manifest["protocol"]["cases"]
    calls, cost = service.audit_records(root, ledger_root, STAGE, protocol,
                                        assigned, terminal, score, CONFIG)
    require(cost <= CAP and
            Decimal(manifest["protocol"]["pre_stage_budget"]["accounted_usd"]) +
            cost < STOP, "stage/budget cap exceeded")
    passed = (len(calls) == MAX_CALLS and
              all(row["status"] == "recorded" and row["result"]["usable"] and
                  row["result"]["valid_action"] and row["result"]["exact"]
                  for row in calls) and not terminal["global_safety_stop"])
    return dict(protocol=protocol, assignments=calls,
                recorded=sum(row["status"] == "recorded" for row in calls),
                exact=sum(row["status"] == "recorded" and
                          row["result"]["exact"] for row in calls),
                gate_passed=passed, accounted_usd=str(cost),
                global_safety_stop=terminal["global_safety_stop"],
                caveat=specification()["limitations"])


def export(root, ledger_root, target, destination, secret=None):
    helper = channel.archive_source.archive_helpers()
    root, ledger_root, target = map(lambda path: Path(path).resolve(),
                                    (root, ledger_root, target))
    require((root / "sessions/terminal.json").is_file(), "not terminal")
    require(not target.exists() and not Path(destination).exists(),
            "archive destination exists")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with Ledger(ledger_root).locked():
            report = audit(root, ledger_root)
            _, protocol = verify(root)
            contents = {"code/" + relative: value.encode()
                        for relative, value in t.load(root / "sources.json").items()}
            for prefix, directory in (("run", root), ("ledger", ledger_root)):
                for path in directory.rglob("*"):
                    require(not path.is_symlink(), "symlink in archive source")
                    if path.is_file() and path.suffix == ".json":
                        contents[prefix + "/" +
                                 str(path.relative_to(directory))] = path.read_bytes()
            contents["expected_report.json"] = (
                json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = (
        "# Qwen route-jurisdiction gate v2\n\n"
        "All 12 rule/action checks and failures retained; this is not a paper "
        "result. From fresh extraction run `python3 -I -S "
        "code/experiments/paper3_route_qwen_gate_v2.py . --replay "
        "--expected-protocol " + protocol + "`.\n").encode()
    for relative, data in contents.items():
        helper.safe(target, relative)
        helper.credentials(data, secret)
    metadata = dict(format=helper.FORMAT, experiment_family=STAGE,
                    protocol=protocol,
                    files={name: t.sha(data) for name, data in sorted(contents.items())})
    target.mkdir(parents=True, exist_ok=False)
    for relative, data in contents.items():
        path = helper.safe(target, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    with (target / "bundle.json").open("x") as stream:
        json.dump(metadata, stream, sort_keys=True, indent=2)
    return dict(protocol=protocol, files=len(contents),
                sha256=helper.archive(target, destination))


def replay(root, expected_protocol):
    helper = channel.archive_source.archive_helpers()
    root = Path(root).resolve()
    metadata = helper.verify_bundle(root, expected_protocol)
    require(metadata["experiment_family"] == STAGE, "wrong archive family")
    require(ROOT == root / "code", "isolated replay requires bundled code")
    sys.addaudithook(helper.offline_guard)
    require(verify(root / "run")[1] == expected_protocol,
            "frozen route-gate protocol changed")
    report = audit(root / "run", root / "ledger")
    require(report == t.load(root / "expected_report.json"),
            "archived report differs")
    return dict(**report, portable_replay=dict(protocol=expected_protocol,
                                              exact_report_match=True))


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
        print(prepare(args.root))
        return
    require(args.expected_protocol, "expected protocol required")
    if args.replay:
        print(json.dumps(replay(args.root, args.expected_protocol), indent=2))
        return
    require(verify(args.root)[1] == args.expected_protocol,
            "unexpected protocol")
    if args.export:
        require(args.target and args.archive, "archive paths required")
        value = export(args.root, BUDGET, args.target, args.archive, t.read_key())
    else:
        value = audit(args.root) if args.audit else execute(args.root,
                                                            secret=t.read_key())
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
