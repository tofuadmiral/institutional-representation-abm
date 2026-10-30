"""Fresh-population discovery of anticipatory binding citizen ratification.

Nine independently drawn synthetic games, each with a matched 4/9-versus-5/9
citizen-approval variant, crossed with advisory/binding referendum authority.
Every district cardinal sum is identical within a pair. No policy case is
selected or repaired after model output; this is discovery, not confirmation.
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

from experiments import paper3_direct_ratification_gate as gate
from experiments import paper3_constituent_b_gptoss_action_gate as archive_source
from paper3 import direct_ratification as prior_game
from paper3 import ratification_threshold_institution as game
from paper3 import ratification_population_schedule as design
from paper3 import ratification_population_analysis as analysis
from paper3 import hosted_reasoning_channel_calls as service
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure

t = gate.t
require = t.require
STAGE = "pivot_b_ratification_population_discovery_v1"
CAP = Decimal("3.50")
STOP = Decimal("8")
MAX_CALLS = 576
WORKERS = 4
BUDGET = gate.BUDGET
CONFIG = gate.CONFIG
GATE_ROOT = ROOT / "results/paper3/pivot_b_direct_ratification_gate_v1"
GATE_ARCHIVE = ROOT / "results/paper3/pivot_b_direct_ratification_gate_v1_export"
GATE_PROTOCOL = "31c206dd1f114e2864da65de89f3d023d082e48a0c50ddf08c1f9ecf9efb1b0f"


class EpisodeFailure(ValueError):
    """An incomplete arm, preserved without content repair."""


def assignments():
    rows = design.assignments("discovery")
    require(len(rows) == 36 and
            sum(x["intended_calls"] for x in rows) == MAX_CALLS,
            "assignment inventory")
    return rows

def prerequisite(gate_root=GATE_ROOT, archive_root=GATE_ARCHIVE):
    helper = archive_source.archive_helpers()
    require(helper.verify_bundle(archive_root, GATE_PROTOCOL)["experiment_family"] ==
            gate.STAGE, "gate archive changed")
    require(gate.verify(gate_root, code_root=Path(archive_root) / "code")[1] ==
            GATE_PROTOCOL, "gate frozen protocol changed")
    report = t.load(Path(archive_root) / "expected_report.json")
    require(report["gate_passed"] and report["calls"] == 10,
            "direct-ratification gate did not pass")
    for case in gate.cases():
        require(request(case["request"]["messages"],
                        case["request"]["seed"]) == case["request"],
                "native request configuration differs from gate")
    return dict(protocol=GATE_PROTOCOL,
                report_sha256=t.sha(t.canonical(report).encode()),
                native_template=request([], 0))


def prerequisite_paths(gate_root=GATE_ROOT, ledger_root=BUDGET,
                       archive_root=GATE_ARCHIVE):
    paths = [Path(gate_root) / name for name in
             ("manifest.json", "sources.json", "sessions/terminal.json")]
    paths += list((Path(ledger_root) / "entries").glob(gate.STAGE + "-*.json"))
    paths.append(Path(ledger_root) / "stages" / (gate.STAGE + ".json"))
    paths += [Path(archive_root) / name for name in
              ("bundle.json", "expected_report.json")]
    return paths


def profiles():
    return design.profiles("discovery")


def request(messages, seed):
    return gate.channel.request_for(messages, seed)


def reservation(value):
    wire = t.canonical(value)
    bound = len(wire.encode()) + 1024
    require(bound + CONFIG["output_bound"] <= gate.channel.CONTEXT,
            "conservative Qwen context bound")
    cost = ((Decimal(bound) * gate.channel.PRICE_IN +
             Decimal(CONFIG["output_bound"]) * gate.channel.PRICE_OUT) /
            Decimal(1000000))
    return dict(wire=wire, input_token_bound=bound, reserved_usd=str(cost))


def make_case(assignment, actor, stage, messages, index):
    require(0 <= index < design.CALLS_PER_EPISODE and
            actor in prior_game.ACTORS and stage in prior_game.STAGES,
            "decision position")
    key = assignment["id"] + f"-{index:02d}"
    req = request(messages, assignment["seed_base"] + index)
    reserve = reservation(req)
    require(reserve["wire"] == t.canonical(req), "noncanonical request")
    return dict(id=key,
                context=dict(kind="action", stage=stage, actor=actor,
                             index=index, profile_id=assignment["profile_id"],
                             arm=assignment["arm"]),
                request=req, request_text=reserve["wire"],
                request_sha256=t.sha(reserve["wire"].encode()),
                input_token_bound=reserve["input_token_bound"],
                reserved_usd=reserve["reserved_usd"])


def score(row, case):
    result = dict(usable=False, valid_action=False, correct=None,
                  native_reasoning=None, action=None, failure=None)
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
    try:
        action = game.parse_action(row["final_content"],
                                   case["context"]["stage"])
        result.update(valid_action=True, action=action, correct=True)
    except (ValueError, TypeError, KeyError) as exc:
        result["failure"] = type(exc).__name__
    return result


def scripted_preflight():
    profile_map = profiles()
    reserves = []
    for assignment in assignments():
        profile = profile_map[assignment["profile_id"]]

        def scripted(actor, stage, messages, index):
            reserves.append(reservation(request(messages,
                                                assignment["seed_base"] + index)))
            if stage in ("draft", "final"):
                return '{"policy":"C","message":"' + "x" * 1500 + '"}'
            if stage == "response":
                return ('{"support":true,"preferred_policy":"C",'
                        '"message":"' + "x" * 1500 + '"}')
            return '{"vote":true}'

        result = game.episode(profile, assignment["arm"], scripted)
        require(result["calls"] == design.CALLS_PER_EPISODE,
                "scripted episode length")
    total = sum(Decimal(row["reserved_usd"]) for row in reserves)
    require(len(reserves) == MAX_CALLS and total <= CAP,
            "scripted full-path reservation exceeds cap")
    return dict(intended_calls=MAX_CALLS,
                full_output_scripted_reservations_usd=str(total),
                max_input_bound=max(row["input_token_bound"] for row in reserves),
                cap_usd=str(CAP))


def seed_audit(root=ROOT):
    planned = {assignment["seed_base"] + i for assignment in assignments()
               for i in range(design.CALLS_PER_EPISODE)}
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

    for base, dirs, files in os.walk(Path(root) / "results/paper3"):
        dirs[:] = [name for name in dirs if not any(fragment in name for fragment in
                   ("portable", "bundle", "export", "replay", "__pycache__", "code"))]
        for name in files:
            path = Path(base) / name
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


def check_endpoint(metadata):
    row = gate.channel.check_metadata(metadata)
    require(row.get("uptime_last_30m") is not None and
            row["uptime_last_30m"] >= 99 and
            row.get("uptime_last_5m") is not None and
            row["uptime_last_5m"] >= 95,
            "Qwen endpoint uptime below pilot threshold")
    return row


def specification():
    return dict(name=STAGE, assignments=assignments(), workers=WORKERS,
                max_calls=MAX_CALLS, cap_usd=str(CAP), budget_stop_usd=str(STOP),
                model_configuration=CONFIG, inherited_gate_protocol=GATE_PROTOCOL,
                scripted_preflight=scripted_preflight(), new_gate_calls=0,
                inference_retries=0, receipt_offsets_seconds=[0, 20, 40, 60],
                failure_rule="Four workers. Invalid or unusable action ends only its episode; retain all assigned cells and prefixes. Two transport/accounting failures or any source/identity/credential/budget/instrument breach stop new admissions. No retry, repair, replacement, fallback or restart.",
                feasibility_gate="All 36 episodes and 576 decisions complete with native reasoning, valid actions and certified charges. Feasibility is not scientific success.",
                discovery_screen="Across nine complete four-corner payoff games, at least seven have a positive binding-by-veto alternative-proposal interaction, at most one negative; binding veto proposes an alternative in at least seven games, and each other corner proposes an alternative in at most two. Missing games make the screen indeterminate; enactment-only changes fail.",
                limitations="Nine prospectively generated opportunity-conditioned synthetic payoff games, not a population of real electorates. The four corners of each game are paired; calls and citizens are not independent games. One Qwen model/provider; this discovery screen is not paper confirmation. Citizen ballots are deterministic. Exact district sums are supplied uniformly.")

def prepare(root, *, metadata=None, ledger_root=BUDGET,
            gate_root=GATE_ROOT, archive_root=GATE_ARCHIVE):
    root = Path(root)
    require(not root.exists(), "fresh population discovery directory required")
    inherited = prerequisite(gate_root, archive_root)
    seeds = seed_audit()
    if metadata is None:
        with t.opener().open(gate.channel.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    check_endpoint(metadata)
    budget = Ledger(ledger_root).snapshot()
    require(budget["pending"] == 0 and
            Decimal(budget["accounted_usd"]) + CAP < STOP,
            "pre-stage conservative spending stop")
    paths = closure(ROOT, [Path(__file__),
                           ROOT / "analysis/paper3_contracts_archive.py",
                           ROOT / "tests/test_paper3_ratification_population_discovery.py",
                           BUDGET / "authority.json",
                           *prerequisite_paths(gate_root, ledger_root,
                                               archive_root)])
    snapshot = {str(path.relative_to(ROOT)): path.read_text() for path in paths}
    protocol = dict(**specification(), inherited_prerequisite=inherited,
                    seed_audit=seeds, pre_stage_budget=budget,
                    endpoint_metadata=metadata,
                    metadata_observed_unix=time.time())
    manifest = dict(protocol=protocol,
                    sources={name: t.sha(value.encode())
                             for name, value in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    for name in ("calls", "decisions", "episodes", "sessions"):
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
                "frozen population source changed: " + relative)
    require(all(manifest["protocol"].get(key) == value
                for key, value in specification().items()),
            "population specification changed")
    inherited = manifest["protocol"]["inherited_prerequisite"]
    require(inherited["protocol"] == GATE_PROTOCOL and
            inherited["native_template"] == request([], 0),
            "gate native configuration changed")
    expected_seeds = sorted({a["seed_base"] + i for a in assignments()
                             for i in range(design.CALLS_PER_EPISODE)})
    require(manifest["protocol"]["seed_audit"]["planned_unique"] ==
            expected_seeds and not manifest["protocol"]["seed_audit"]["overlap"],
            "seed audit changed")
    check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, ledger_root=BUDGET, gate_root=GATE_ROOT,
            archive_root=GATE_ARCHIVE, secret=None, send=None, lookup=None,
            clock=time.time, sleep=time.sleep):
    root = Path(root)
    manifest, protocol = verify(root)
    require(prerequisite(gate_root, archive_root) ==
            manifest["protocol"]["inherited_prerequisite"],
            "live gate prerequisite changed")
    require(0 <= clock() - manifest["protocol"]["metadata_observed_unix"] <= 3600,
            "stale endpoint metadata")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(all(not list((root / name).iterdir()) for name in
                    ("calls", "decisions", "episodes", "sessions")),
                "already started; no restart")
        ledger = Ledger(ledger_root)
        require(ledger.snapshot() == manifest["protocol"]["pre_stage_budget"],
                "pre-stage budget changed")
        ledger.allocate(STAGE, CAP)
        atomic(root / "sessions/start.json", dict(protocol=protocol,
                                                  pid=os.getpid(), started_unix=clock()))
        calls = service.Calls(root, ledger_root, STAGE, MAX_CALLS,
                              lambda: verify(root), score, CONFIG, secret,
                              send, lookup, clock, sleep)
        profile_map = profiles()

        def one(assignment):
            if calls.stop.is_set():
                saved = dict(id=assignment["id"], status="not_started")
            else:
                profile = profile_map[assignment["profile_id"]]

                def ask(actor, stage, messages, index):
                    case = make_case(assignment, actor, stage, messages, index)
                    path = root / "decisions" / (case["id"] + ".json")
                    atomic(path, dict(case=case,
                                      result=dict(id=case["id"], status="prepared")))
                    result = calls.one(case)
                    atomic(path, dict(case=case, result=result))
                    if result["status"] != "recorded":
                        raise EpisodeFailure("request_not_recorded")
                    row = t.load(root / "calls" / (case["id"] + ".json"))
                    if not (row["result"]["usable"] and
                            row["result"]["valid_action"]):
                        raise EpisodeFailure("unusable_or_invalid_action")
                    return row["final_content"]

                try:
                    saved = dict(id=assignment["id"], status="completed",
                                 **game.episode(profile, assignment["arm"], ask))
                except EpisodeFailure as exc:
                    saved = dict(id=assignment["id"], status="failed",
                                 error=str(exc))
                except Exception as exc:
                    calls.stop.set()
                    saved = dict(id=assignment["id"], status="instrument_error",
                                 error=type(exc).__name__)
            atomic(root / "episodes" / (assignment["id"] + ".json"), saved)
            print(json.dumps(dict(event="population_discovery_episode_terminal",
                                  id=assignment["id"], status=saved["status"],
                                  budget=ledger.snapshot())), flush=True)
            return dict(id=assignment["id"], status=saved["status"])

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            summaries = list(pool.map(one, manifest["protocol"]["assignments"]))
        terminal = dict(protocol=protocol, episodes=summaries,
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
    scheduled = manifest["protocol"]["assignments"]
    require([x["id"] for x in terminal["episodes"]] ==
            [x["id"] for x in scheduled], "episode inventory")
    decisions = [t.load(path) for path in sorted((root / "decisions").glob("*.json"))]
    cases = [row["case"] for row in decisions]
    require(len(cases) <= MAX_CALLS and
            len({row["id"] for row in cases}) == len(cases),
            "decision inventory")
    calls, cost = service.audit_records(
        root, ledger_root, STAGE, protocol, cases,
        dict(results=[row["result"] for row in decisions]), score, CONFIG)
    require(cost <= CAP and
            Decimal(manifest["protocol"]["pre_stage_budget"]["accounted_usd"]) +
            cost < STOP, "stage/budget cap exceeded")
    by_id = {row["id"]: row for row in calls}
    profile_map = profiles()
    records = {}
    for assignment, summary in zip(scheduled, terminal["episodes"], strict=True):
        saved = t.load(root / "episodes" / (assignment["id"] + ".json"))
        require(saved["id"] == summary["id"] and
                saved["status"] == summary["status"], "episode terminal changed")
        indexed = [row for row in decisions
                   if row["case"]["id"].startswith(assignment["id"] + "-")]
        indexed.sort(key=lambda row: row["case"]["context"]["index"])
        if saved["status"] == "not_started":
            require(not indexed, "not-started episode has decisions")
        elif saved["status"] in ("completed", "failed"):
            position = 0

            def replay_ask(actor, stage, messages, index):
                nonlocal position
                require(index == position and position < len(indexed),
                        "missing decision")
                case = make_case(assignment, actor, stage, messages, index)
                row = indexed[position]
                position += 1
                require(row["case"] == case, "population request changed")
                if row["result"]["status"] != "recorded":
                    raise EpisodeFailure("request_not_recorded")
                call = by_id[case["id"]]
                if not (call["result"]["usable"] and
                        call["result"]["valid_action"]):
                    raise EpisodeFailure("unusable_or_invalid_action")
                return t.load(root / "calls" / (case["id"] + ".json"))["final_content"]

            profile = profile_map[assignment["profile_id"]]
            try:
                actual = game.episode(profile, assignment["arm"], replay_ask)
                require(saved["status"] == "completed" and
                        actual == {key: value for key, value in saved.items()
                                   if key not in ("id", "status")} and
                        position == len(indexed), "completed replay differs")
            except EpisodeFailure as exc:
                require(saved["status"] == "failed" and
                        saved["error"] == str(exc) and position == len(indexed),
                        "failed replay differs")
        else:
            require(saved["status"] == "instrument_error" and
                    terminal["global_safety_stop"], "unexplained instrument state")
        records[assignment["id"]] = dict(
            complete=saved["status"] == "completed",
            outcome=saved.get("outcome"), failure=saved.get("error"),
            status=saved["status"])
    readout = analysis.readout("discovery", records)
    completed = sum(row["status"] == "completed"
                    for row in terminal["episodes"])
    usable = sum(row["status"] == "recorded" and
                 row["result"]["usable"] and row["result"]["valid_action"]
                 for row in calls)
    feasible = (completed == 36 and usable == MAX_CALLS and
                len(calls) == MAX_CALLS and not terminal["global_safety_stop"])
    return dict(protocol=protocol, assignments=terminal["episodes"],
                calls=calls, completed_episodes=completed,
                usable_actions=usable, feasibility_passed=feasible,
                readout=readout,
                discovery_triage=readout["strict_discovery_lead"],
                accounted_usd=str(cost),
                global_safety_stop=terminal["global_safety_stop"],
                caveat=specification()["limitations"])


def export(root, ledger_root, target, destination, secret=None):
    helper = archive_source.archive_helpers()
    root, ledger_root, target = map(lambda p: Path(p).resolve(),
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
                        contents[prefix + "/" + str(path.relative_to(directory))] = (
                            path.read_bytes())
            contents["expected_report.json"] = (
                json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = (
        "# Fresh-population citizen-ratification discovery\n\n"
        "Retain all 36 assignments, failures, person-level outcomes and "
        "finite missingness bounds. Nine independent synthetic games, not a real electorate sample. "
        "From fresh extraction run `python3 -I -S "
        "code/experiments/paper3_ratification_population_discovery.py . "
        "--replay --expected-protocol " + protocol + "`.\n").encode()
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
    helper = archive_source.archive_helpers()
    root = Path(root).resolve()
    metadata = helper.verify_bundle(root, expected_protocol)
    require(metadata["experiment_family"] == STAGE, "wrong archive family")
    require(ROOT == root / "code", "isolated replay requires bundled code")
    sys.addaudithook(helper.offline_guard)
    require(verify(root / "run")[1] == expected_protocol,
            "frozen population protocol changed")
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
        result = export(args.root, BUDGET, args.target, args.archive, t.read_key())
    else:
        result = audit(args.root) if args.audit else execute(args.root,
                                                             secret=t.read_key())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
