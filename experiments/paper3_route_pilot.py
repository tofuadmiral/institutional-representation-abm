"""UNAPPROVED conditional route-jurisdiction discovery runner.

No pilot may be prepared or run unless the distinct 12-case route gate passes
and Fuad approves the new pilot cap. This is selected-profile mechanism
discovery, never a population or publication result by itself.
"""
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

from experiments import paper3_route_gate as gate_runner
from experiments import paper3_transport_diagnostic as t
from paper3 import hosted_reasoning_channel_calls as service
from paper3 import route_jurisdiction as game
from paper3 import route_jurisdiction_analysis as analysis
from paper3 import route_jurisdiction_requests as requests
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure


require = t.require
STAGE = "pivot_b_route_pilot_v1"
CAP = requests.PILOT_CAP
MAX_CALLS = 128
WORKERS = 2
BUDGET = gate_runner.BUDGET
GATE_ROOT = ROOT / "results/paper3/pivot_b_route_gate_v1"
CONFIG = gate_runner.CONFIG


def schedule():
    rows = requests.pilot_assignments()
    require(len(rows) == 8 and sum(x["intended_calls"] for x in rows) == MAX_CALLS,
            "episode schedule changed")
    return rows


def prerequisite(gate_root=GATE_ROOT):
    manifest, protocol = gate_runner.verify(gate_root)
    report = gate_runner.audit(gate_root)
    require(report["protocol"] == protocol and report["gate_passed"] and report["calls"] == 12,
            "distinct route gate did not pass")
    require(manifest["protocol"]["model_configuration"] == CONFIG,
            "gate model configuration differs")
    return dict(protocol=protocol, report=report,
                report_sha256=t.sha(t.canonical(report).encode()),
                action_request_template=requests.request([], 0, kind="action", stage="offer"),
                limitation="An engineering gate is not a behavioral or publication result.")


def prerequisite_paths(gate_root=GATE_ROOT):
    gate_root = Path(gate_root)
    paths = [ROOT / p for p in t.load(gate_root / "manifest.json")["sources"]]
    paths += [p for p in gate_root.rglob("*.json") if p.is_file()]
    paths += [p for p in (BUDGET / "entries").glob(gate_runner.STAGE + "-*.json")]
    paths += [BUDGET / "stages" / (gate_runner.STAGE + ".json")]
    return paths


def make_case(assignment, actor, stage, messages, index):
    profile = assignment["profile"]
    require(0 <= index < 16 and actor in profile["actors"] and
            stage in ("recommendation", "offer", "ballot", "review"),
            "invalid decision position")
    key = assignment["id"] + f"-{index:02d}"
    req = requests.request(messages, assignment["seed_base"] + index,
                           kind="action", stage=stage)
    reservation = requests.reservation(req)
    require(reservation["wire"] == t.canonical(req), "noncanonical request")
    return dict(id=key, context=dict(assignment=assignment["id"], profile=profile,
                                     arm=assignment["arm"], actor=actor,
                                     stage=stage, index=index),
                request=req, request_text=reservation["wire"],
                request_sha256=t.sha(reservation["wire"].encode()),
                input_token_bound=reservation["input_token_bound"],
                reserved_usd=reservation["reserved_usd"])


def score(row, case):
    report = dict(usable=False, valid_action=False, action=None,
                  native_reasoning=None, failure=None)
    if row.get("instrument_error") or "assessment" not in row:
        report["failure"] = "instrument_or_unfinished"
        return report
    assessed = service.assess(row, CONFIG)
    summary = assessed["stream"]
    native = service.native_evidence(summary)
    usable = (assessed["passed"] and summary["finish_reasons"] == ["stop"]
              and native["present"] and
              row["request"].get("reasoning") == dict(enabled=True, exclude=False))
    report.update(usable=usable, native_reasoning=native)
    if not usable:
        report["failure"] = "transport_reasoning_or_completion"
        return report
    try:
        action = game.validate_action(row["final_content"], case["context"]["stage"],
                                      case["context"]["profile"])
        report.update(valid_action=True, action=action)
    except (ValueError, TypeError, KeyError) as exc:
        report["failure"] = type(exc).__name__
    return report


def seed_audit(root=ROOT):
    planned = {a["seed_base"] + j for a in schedule() for j in range(16)}
    observed = set()
    inventory = []

    def walk(value, key=""):
        if isinstance(value, dict):
            for k, child in value.items():
                walk(child, k)
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif type(value) is int and "seed" in key.lower():
            observed.add(value)

    for base, dirs, files in os.walk(Path(root) / "results/paper3"):
        dirs[:] = [d for d in dirs if not any(x in d for x in
                   ("portable", "bundle", "export", "__pycache__", "code"))]
        for name in files:
            path = Path(base) / name
            if name == "manifest.json" or (path.parent.name == "calls" and name.endswith(".json")):
                value = t.load(path)
                walk(value.get("request", value))
                inventory.append((str(path.relative_to(root)), t.sha(path.read_bytes())))
    require(not planned & observed, "historical pilot seed overlap")
    return dict(planned=sorted(planned), overlap=[], historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()),
                pairing="Same profiles across arms; distinct requested seeds do not imply matched stochastic draws.")


def specification():
    return dict(name=STAGE, assignments=schedule(), max_calls=MAX_CALLS,
                workers=WORKERS, cap_usd=str(CAP), budget_cap_usd="10.00",
                model_configuration=CONFIG,
                native_template=requests.request([], 0, kind="action", stage="offer"),
                new_gate_calls=0, inference_retries=0,
                receipt_offsets_seconds=[0, 20, 40, 60],
                failure_rule="Invalid/unusable content ends that episode with its full prefix. Two transport/accounting failures or any identity/source/budget breach stop NEW admissions; already admitted requests finish. No retry, repair, replacement, fallback or restart.",
                feasibility_gate="All eight assigned episodes complete, all 128 calls usable/native/certified and no global safety stop. Completion is not scientific success.",
                readout="All pre-vote policy/route choices, seven principal utilities and own-best regrets, votes, review, fixed-action replays, failures and finite missingness bounds; no complete-case-only claim.",
                limitations="Four theory-constructed discovery opportunities, one episode per arm/profile, one model/provider. Exact utility tables and a single proposer remain simplifications. Mechanical review cannot count as agent adaptation; no population or publication inference from this pilot.")


def prepare(root):
    root = Path(root)
    require(not root.exists(), "fresh pilot directory required")
    inherited = prerequisite()
    seeds = seed_audit()
    with t.opener().open(gate_runner.METADATA_URL, timeout=20) as response:
        metadata = json.load(response)
    gate_runner.check_endpoint(metadata)
    budget = Ledger(BUDGET).snapshot()
    require(budget["pending"] == 0 and Decimal(budget["accounted_usd"]) + CAP <= Decimal("10"),
            "pilot budget baseline")
    roots = [Path(__file__), ROOT / "analysis/paper3_contracts_archive.py",
             ROOT / "tests/test_paper3_route_pilot_runner.py",
             BUDGET / "authority.json", *prerequisite_paths()]
    paths = closure(ROOT, roots)
    snapshot = {str(p.relative_to(ROOT)): p.read_text() for p in paths}
    protocol = dict(**specification(), inherited_prerequisite=inherited,
                    seed_audit=seeds, pre_stage_budget=budget,
                    endpoint_metadata=metadata, metadata_observed_unix=time.time())
    manifest = dict(protocol=protocol, sources={p: t.sha(value.encode()) for p, value in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    for name in ("calls", "decisions", "episodes", "sessions"):
        (root / name).mkdir()
    atomic(root / "sources.json", snapshot)
    atomic(root / "manifest.json", manifest)
    return t.sha(t.canonical(manifest).encode())


def verify(root, code_root=ROOT):
    root = Path(root)
    manifest = t.load(root / "manifest.json")
    snapshot = t.load(root / "sources.json")
    require(set(snapshot) == set(manifest["sources"]), "pilot source inventory")
    for relative, expected in manifest["sources"].items():
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts, "unsafe pilot source")
        require(t.sha((Path(code_root) / path).read_bytes()) ==
                t.sha(snapshot[relative].encode()) == expected,
                "frozen pilot source changed: " + relative)
    require(all(manifest["protocol"].get(k) == value for k, value in specification().items()),
            "pilot specification changed")
    inherited = manifest["protocol"]["inherited_prerequisite"]
    require(inherited["report"]["gate_passed"] and inherited["report"]["calls"] == 12 and
            inherited["report_sha256"] == t.sha(t.canonical(inherited["report"]).encode()) and
            inherited["action_request_template"] == specification()["native_template"],
            "gate inheritance changed")
    require(manifest["protocol"]["seed_audit"]["planned"] ==
            sorted({a["seed_base"] + j for a in schedule() for j in range(16)}) and
            not manifest["protocol"]["seed_audit"]["overlap"], "pilot seed audit")
    gate_runner.check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, ledger_root=BUDGET, secret=None, send=None, lookup=None,
            clock=time.time, sleep=time.sleep):
    root = Path(root)
    manifest, protocol = verify(root)
    require(prerequisite() == manifest["protocol"]["inherited_prerequisite"],
            "gate replay changed")
    require(0 <= clock() - manifest["protocol"]["metadata_observed_unix"] <= 3600,
            "stale endpoint metadata")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(all(not list((root / name).iterdir()) for name in
                    ("calls", "decisions", "episodes", "sessions")),
                "already started; no restart")
        ledger = Ledger(ledger_root)
        require(ledger.snapshot() == manifest["protocol"]["pre_stage_budget"],
                "pre-stage accounting changed")
        ledger.allocate(STAGE, CAP)
        atomic(root / "sessions/start.json", dict(protocol=protocol,
                                                  pid=os.getpid(), started_unix=clock()))
        calls = service.Calls(root, ledger_root, STAGE, MAX_CALLS,
                              lambda: verify(root), score, CONFIG, secret,
                              send, lookup, clock, sleep)

        def one(assignment):
            if calls.stop.is_set():
                episode = dict(id=assignment["id"], status="not_started")
            else:
                index = 0

                def ask(messages):
                    nonlocal index
                    context = json.loads(messages[1]["content"].split("\n", 1)[0])
                    actor, stage = context["acting_for"], context["stage"]
                    case = make_case(assignment, actor, stage, messages, index)
                    index += 1
                    path = root / "decisions" / (case["id"] + ".json")
                    atomic(path, dict(case=case, result=dict(id=case["id"], status="prepared")))
                    status = calls.one(case)
                    atomic(path, dict(case=case, result=status))
                    if status["status"] != "recorded":
                        raise ValueError("request not recorded")
                    row = t.load(root / "calls" / (case["id"] + ".json"))
                    if not row["result"]["usable"]:
                        raise ValueError("unusable response")
                    return row["final_content"]

                try:
                    result = game.run_episode(assignment["profile"], assignment["arm"], ask)
                    episode = dict(id=assignment["id"], **result)
                except Exception as exc:
                    calls.stop.set()
                    episode = dict(id=assignment["id"], status="instrument_error",
                                   error_type=type(exc).__name__)
            atomic(root / "episodes" / (assignment["id"] + ".json"), episode)
            print(json.dumps(dict(event="route_episode_terminal", id=assignment["id"],
                                  status=episode["status"], budget=ledger.snapshot())), flush=True)
            return dict(id=assignment["id"], status=episode["status"])

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            episodes = list(pool.map(one, manifest["protocol"]["assignments"]))
        terminal = dict(protocol=protocol, episodes=episodes,
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
            terminal["protocol"] == protocol, "pilot terminal protocol mismatch")
    assignments = manifest["protocol"]["assignments"]
    require([e["id"] for e in terminal["episodes"]] == [a["id"] for a in assignments],
            "episode inventory changed")
    decisions = [t.load(p) for p in sorted((root / "decisions").glob("*.json"))]
    require(len(decisions) <= MAX_CALLS and
            {d["case"]["context"]["assignment"] for d in decisions} <=
            {a["id"] for a in assignments}, "unexpected pilot decisions")
    cases = [d["case"] for d in decisions]
    call_terminal = dict(results=[d["result"] for d in decisions])
    call_reports, cost = service.audit_records(root, ledger_root, STAGE, protocol,
                                               cases, call_terminal, score, CONFIG)
    require(cost <= CAP, "pilot stage cap exceeded")
    prior = Decimal(manifest["protocol"]["pre_stage_budget"]["accounted_usd"])
    require(prior + cost <= Decimal("10"), "fresh B cap exceeded")
    reports_by_id = {r["id"]: r for r in call_reports}
    records = {}
    for assignment, summary in zip(assignments, terminal["episodes"], strict=True):
        saved = t.load(root / "episodes" / (assignment["id"] + ".json"))
        require(saved["id"] == summary["id"] and saved["status"] == summary["status"],
                "episode terminal changed")
        indexed = [d for d in decisions if d["case"]["context"]["assignment"] == assignment["id"]]
        indexed.sort(key=lambda d: d["case"]["context"]["index"])
        if saved["status"] == "not_started":
            require(not indexed, "not-started episode has decisions")
        elif saved["status"] in ("completed", "failed"):
            index = 0

            def replay_ask(messages):
                nonlocal index
                require(index < len(indexed), "missing decision")
                context = json.loads(messages[1]["content"].split("\n", 1)[0])
                actor, stage = context["acting_for"], context["stage"]
                case = make_case(assignment, actor, stage, messages, index)
                entry = indexed[index]
                index += 1
                require(entry["case"] == case, "decision request changed")
                status = entry["result"]
                if status["status"] != "recorded":
                    raise ValueError("request not recorded")
                call = reports_by_id[case["id"]]
                if not call["result"]["usable"]:
                    raise ValueError("unusable response")
                return t.load(root / "calls" / (case["id"] + ".json"))["final_content"]

            actual = game.run_episode(assignment["profile"], assignment["arm"], replay_ask)
            require(actual == {k: v for k, v in saved.items() if k != "id"} and
                    index == len(indexed), "episode replay differs")
        else:
            require(saved["status"] == "instrument_error" and terminal["global_safety_stop"],
                    "unexplained episode state")
        records[(assignment["profile"]["name"], assignment["arm"])] = (
            dict(status="failed", error="instrument_error") if saved["status"] == "instrument_error"
            else {k: v for k, v in saved.items() if k != "id"})
    profiles = [p for p in requests.design.frame() if p["split"] == "discovery_candidate"]
    readout = analysis.readout(profiles, records)
    completed = sum(e["status"] == "completed" for e in terminal["episodes"])
    usable = sum(r["status"] == "recorded" and r["result"]["usable"] and
                 r["result"]["valid_action"] for r in call_reports)
    feasibility = (completed == 8 and usable == MAX_CALLS and
                   len(call_reports) == MAX_CALLS and not terminal["global_safety_stop"])
    return dict(protocol=protocol, assignments=terminal["episodes"], calls=call_reports,
                completed_episodes=completed, usable_actions=usable,
                feasibility_passed=feasibility, readout=readout,
                accounted_usd=str(cost), global_safety_stop=terminal["global_safety_stop"],
                caveat=specification()["limitations"])


def archive_helpers():
    return gate_runner.archive_helpers()


def export(root, ledger_root, target, destination, secret=None):
    helper = archive_helpers()
    root, ledger_root, target = map(lambda p: Path(p).resolve(), (root, ledger_root, target))
    require((root / "sessions/terminal.json").is_file(), "not terminal")
    require(not target.exists() and not Path(destination).exists(), "archive destination exists")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with Ledger(ledger_root).locked():
            report = audit(root, ledger_root)
            _, protocol = verify(root)
            contents = {"code/" + p: value.encode()
                        for p, value in t.load(root / "sources.json").items()}
            for prefix, directory in (("run", root), ("ledger", ledger_root)):
                for path in directory.rglob("*"):
                    require(not path.is_symlink(), "symlink in archive source")
                    if path.is_file() and path.suffix == ".json":
                        contents[prefix + "/" + str(path.relative_to(directory))] = path.read_bytes()
            contents["expected_report.json"] = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = (
        "# Paper 3 route-jurisdiction discovery pilot\n\n"
        "Four constructed profiles, two arms, at most 128 institutional calls. "
        "Retains all eight assignments, failures and seven-principal outcomes. "
        "A completed pilot is mechanism discovery, not publication evidence.\n\n"
        "Inspect trusted source; then run from a fresh extracted directory:\n\n"
        "`python3 -I -S code/experiments/paper3_route_pilot.py . --replay "
        "--expected-protocol " + protocol + "`\n\n"
        "No key, network, model weights or original checkout is needed. "
        "Hashes prove consistency, not provider authenticity or generalization.\n").encode()
    for relative, data in contents.items():
        helper.safe(target, relative)
        helper.credentials(data, secret)
    metadata = dict(format=helper.FORMAT, experiment_family=STAGE, protocol=protocol,
                    files={p: t.sha(data) for p, data in sorted(contents.items())})
    target.mkdir(parents=True, exist_ok=False)
    for relative, data in contents.items():
        path = helper.safe(target, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    with (target / "bundle.json").open("x") as stream:
        json.dump(metadata, stream, sort_keys=True, indent=2)
    return dict(protocol=protocol, files=len(contents), sha256=helper.archive(target, destination))


def replay(root, expected_protocol):
    helper = archive_helpers()
    root = Path(root).resolve()
    metadata = helper.verify_bundle(root, expected_protocol)
    require(metadata["experiment_family"] == STAGE, "wrong archive family")
    require(ROOT == root / "code", "replay requires bundled isolated source")
    sys.addaudithook(helper.offline_guard)
    require(verify(root / "run")[1] == expected_protocol, "pilot protocol changed")
    report = audit(root / "run", root / "ledger")
    require(report == t.load(root / "expected_report.json"), "archived pilot report differs")
    return dict(**report, portable_replay=dict(protocol=expected_protocol, exact_report_match=True))


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
    require(args.expected_protocol, "explicit expected protocol required")
    if args.replay:
        value = replay(args.root, args.expected_protocol)
    else:
        require(verify(args.root)[1] == args.expected_protocol, "unexpected protocol")
        if args.export:
            require(args.target and args.archive, "archive paths required")
            value = export(args.root, BUDGET, args.target, args.archive, t.read_key())
        else:
            value = audit(args.root) if args.audit else execute(args.root, secret=t.read_key())
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
