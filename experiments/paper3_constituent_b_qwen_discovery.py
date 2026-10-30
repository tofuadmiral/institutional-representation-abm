"""Seven-profile Qwen constituent-institution mechanism-discovery pilot.

This reuses the historically reliable Qwen3-32B/DeepInfra native-reasoning,
JSON-object channel. Local legal-action checks and all citizen outcomes remain
substantive. One invalid episode is retained, not used to stop other arms.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import fcntl
from functools import lru_cache
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import paper3_qwen_channel_gate as gate
from experiments import paper3_constituent_b_gptoss_action_gate as archive_source
from paper3 import coalition_contracts as game
from paper3 import constituent_b_gptoss_discovery_analysis as analysis
from paper3 import constituent_b_institution as institution
from paper3 import constituent_b_qwen_design as design
from paper3 import constituent_b_qwen_requests as requests
from paper3 import hosted_reasoning_channel_calls as service
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure


t = gate.t
require = t.require
STAGE = "pivot_b_qwen_constituent_discovery_v1"
CAP = requests.CAP
MAX_CALLS = requests.MAX_CALLS
WORKERS = 4
BUDGET = gate.BUDGET
GATE_ROOT = ROOT / "results/paper3/pivot_b_qwen_channel_gate_v1"
GATE_ARCHIVE = ROOT / "results/paper3/pivot_b_qwen_channel_gate_v1_portable"
GATE_PROTOCOL = "30585cdf44e1626620cab265d092432fe9aa585404e7f32376b13f5ac60f3388"
CONFIG = gate.CONFIG


class EpisodeFailure(ValueError):
    """An individual incomplete episode, preserved rather than repaired."""


def assignments():
    rows = design.assignments()
    require(len(rows) == 21 and sum(x["intended_calls"] for x in rows) == MAX_CALLS,
            "Qwen constituent assignment inventory changed")
    return rows


def prerequisite(gate_root=GATE_ROOT, archive_root=GATE_ARCHIVE):
    require(archive_source.archive_helpers().verify_bundle(
        archive_root, GATE_PROTOCOL)["experiment_family"] == gate.STAGE,
        "Qwen channel archive changed")
    require(gate.verify(gate_root, code_root=Path(archive_root) / "code")[1] ==
            GATE_PROTOCOL, "Qwen channel prerequisite protocol changed")
    report = t.load(Path(archive_root) / "expected_report.json")
    require(report["gate_passed"] and report["calls"] == 16,
            "Qwen channel prerequisite did not pass")
    for case in gate.cases():
        require(requests.request(case["request"]["messages"],
                                 case["request"]["seed"]) == case["request"],
                "native Qwen request configuration differs")
    return dict(protocol=GATE_PROTOCOL, report=report,
                report_sha256=t.sha(t.canonical(report).encode()),
                native_template=requests.request([], 0))


def prerequisite_paths(gate_root=GATE_ROOT, ledger_root=BUDGET,
                       archive_root=GATE_ARCHIVE):
    paths = [ROOT / value for value in t.load(Path(gate_root) / "manifest.json")["sources"]]
    paths += [path for path in Path(gate_root).rglob("*.json") if path.is_file()]
    paths += list((Path(ledger_root) / "entries").glob(gate.STAGE + "-*.json"))
    paths.append(Path(ledger_root) / "stages" / (gate.STAGE + ".json"))
    paths += [path for path in Path(archive_root).rglob("*") if path.is_file()]
    return paths


def prepared_profiles():
    return {row["prepared"]["contract_profile"]["id"]: row
            for row in design.profiles()}


def make_case(assignment, actor, stage, messages, index):
    require(0 <= index < 30 and actor in game.ACTORS and
            stage in ("draft", "response", "final", "consent",
                      "first_vote", "second_vote"), "invalid decision position")
    key = assignment["id"] + f"-{index:02d}"
    req = requests.request(messages, assignment["seed_base"] + index)
    reserve = requests.reservation(req)
    require(reserve["wire"] == t.canonical(req), "noncanonical request")
    return dict(id=key,
                context=dict(kind="compound", stage=stage, actor=actor,
                             index=index, profile_id=assignment["profile_id"],
                             arm=assignment["arm"], dominant_projects=None),
                request=req, request_text=reserve["wire"],
                request_sha256=t.sha(reserve["wire"].encode()),
                input_token_bound=reserve["input_token_bound"],
                reserved_usd=reserve["reserved_usd"])


def score(row, case):
    return gate.score(row, case)


def seed_audit(root=ROOT):
    planned = {assignment["seed_base"] + i for assignment in assignments()
               for i in range(30)}
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
        dirs[:] = [d for d in dirs if not any(fragment in d for fragment in
                   ("portable", "bundle", "export", "__pycache__", "code"))]
        for name in files:
            path = Path(base) / name
            if name != "manifest.json" and not (path.parent.name == "calls" and
                                                 name.endswith(".json")):
                continue
            value = t.load(path)
            walk(value.get("request", value) if path.parent.name == "calls" else value)
            inventory.append((str(path.relative_to(root)), t.sha(path.read_bytes())))
    require(not planned & observed, "historical Qwen constituent seed overlap")
    return dict(planned_unique=sorted(planned), intended_calls=MAX_CALLS,
                paired_across_arms=True, overlap=[], historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()))


def check_endpoint(metadata):
    row = gate.check_metadata(metadata)
    require(row.get("uptime_last_30m") is not None and
            row["uptime_last_30m"] >= 99 and
            row.get("uptime_last_5m") is not None and
            row["uptime_last_5m"] >= 95,
            "recent Qwen endpoint uptime below predeclared launch threshold")
    return row


@lru_cache(maxsize=1)
def specification():
    return dict(name=STAGE, assignments=assignments(), workers=WORKERS,
                max_calls=MAX_CALLS, cap_usd=str(CAP), budget_cap_usd="8.00",
                model_configuration=CONFIG,
                native_template=requests.request([], 0),
                inherited_prerequisite_protocol=GATE_PROTOCOL,
                scripted_preflight=requests.scripted_preflight(),
                new_gate_calls=0, inference_retries=0,
                receipt_offsets_seconds=[0, 20, 40, 60],
                failure_rule="Four workers. Invalid/unusable action ends only its own episode; all 21 assignments remain. The service stops new admissions after two transport/accounting failures or any source/identity/credential/budget/instrument breach. No retry, replacement, repair, fallback or restart.",
                feasibility_gate="All 21 episodes and 630 decisions complete with native reasoning, locally legal actions and certified charges. Feasibility is not scientific success.",
                scientific_screen="Descriptive within-profile pre-vote offer/consent/requested-ballot changes across both exchange types with all controls and 63 citizens retained; mechanical ballot overrides alone never count. Missing arms receive finite bounds, not silent deletion.",
                limitations="Seven constructed utility structures, one model/provider, paired requested seeds but not guaranteed common draws. No population inference; calls and citizens within a game are not independent units.")


def prepare(root, *, metadata=None, ledger_root=BUDGET, gate_root=GATE_ROOT):
    root = Path(root)
    require(not root.exists(), "fresh Qwen constituent directory required")
    inherited = prerequisite(gate_root)
    seeds = seed_audit()
    if metadata is None:
        with t.opener().open(gate.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    check_endpoint(metadata)
    budget = Ledger(ledger_root).snapshot()
    require(budget["pending"] == 0 and
            Decimal(budget["accounted_usd"]) + CAP <= Decimal("8"),
            "Qwen discovery pre-stage spending stop")
    paths = closure(ROOT, [Path(__file__),
                           ROOT / "analysis/paper3_contracts_archive.py",
                           ROOT / "tests/test_paper3_constituent_b_qwen_discovery.py",
                           BUDGET / "authority.json",
                           *prerequisite_paths(gate_root, ledger_root)])
    snapshot = {str(path.relative_to(ROOT)): path.read_text() for path in paths}
    protocol = dict(**specification(), inherited_prerequisite=inherited,
                    seed_audit=seeds, pre_stage_budget=budget,
                    endpoint_metadata=metadata, metadata_observed_unix=time.time())
    manifest = dict(protocol=protocol,
                    sources={name: t.sha(value.encode()) for name, value in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    for name in ("calls", "decisions", "episodes", "sessions"):
        (root / name).mkdir()
    atomic(root / "sources.json", snapshot)
    atomic(root / "manifest.json", manifest)
    return t.sha(t.canonical(manifest).encode())


def verify(root, code_root=ROOT):
    root = Path(root)
    manifest, snapshot = t.load(root / "manifest.json"), t.load(root / "sources.json")
    require(set(snapshot) == set(manifest["sources"]), "source inventory changed")
    for relative, expected in manifest["sources"].items():
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts,
                "unsafe frozen source")
        require(t.sha((Path(code_root) / path).read_bytes()) ==
                t.sha(snapshot[relative].encode()) == expected,
                "frozen Qwen constituent source changed: " + relative)
    require(all(manifest["protocol"].get(key) == value
                for key, value in specification().items()),
            "Qwen constituent specification changed")
    inherited = manifest["protocol"]["inherited_prerequisite"]
    require(inherited["protocol"] == GATE_PROTOCOL and
            inherited["report"]["gate_passed"] and
            inherited["report_sha256"] ==
            t.sha(t.canonical(inherited["report"]).encode()) and
            inherited["native_template"] == requests.request([], 0),
            "Qwen prerequisite evidence changed")
    expected_seeds = sorted({a["seed_base"] + i for a in assignments()
                             for i in range(30)})
    require(manifest["protocol"]["seed_audit"]["planned_unique"] ==
            expected_seeds and not manifest["protocol"]["seed_audit"]["overlap"],
            "Qwen constituent seed audit changed")
    check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, ledger_root=BUDGET, gate_root=GATE_ROOT, secret=None,
            send=None, lookup=None, clock=time.time, sleep=time.sleep):
    root = Path(root)
    manifest, protocol = verify(root)
    require(prerequisite(gate_root) == manifest["protocol"]["inherited_prerequisite"],
            "live Qwen prerequisite changed")
    require(0 <= clock() - manifest["protocol"]["metadata_observed_unix"] <= 3600,
            "stale Qwen endpoint metadata")
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
        profiles = prepared_profiles()

        def one(assignment):
            if calls.stop.is_set():
                saved = dict(id=assignment["id"], status="not_started")
            else:
                prepared = profiles[assignment["profile_id"]]["prepared"]

                def ask(actor, stage, messages, index):
                    case = make_case(assignment, actor, stage, messages, index)
                    path = root / "decisions" / (case["id"] + ".json")
                    atomic(path, dict(case=case, result=dict(id=case["id"],
                                                              status="prepared")))
                    result = calls.one(case)
                    atomic(path, dict(case=case, result=result))
                    if result["status"] != "recorded":
                        raise EpisodeFailure("request_not_recorded")
                    row = t.load(root / "calls" / (case["id"] + ".json"))
                    if not (row["result"]["usable"] and row["result"]["valid_action"]):
                        raise EpisodeFailure("unusable_or_invalid_action")
                    return row["final_content"]

                try:
                    saved = dict(id=assignment["id"], status="completed",
                                 **institution.episode(prepared, assignment["arm"], ask))
                except EpisodeFailure as exc:
                    saved = dict(id=assignment["id"], status="failed", error=str(exc))
                except Exception as exc:
                    calls.stop.set()
                    saved = dict(id=assignment["id"], status="instrument_error",
                                 error=type(exc).__name__)
            atomic(root / "episodes" / (assignment["id"] + ".json"), saved)
            print(json.dumps(dict(event="constituent_qwen_episode_terminal",
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
            terminal["protocol"] == protocol, "terminal protocol mismatch")
    scheduled = manifest["protocol"]["assignments"]
    require([row["id"] for row in terminal["episodes"]] ==
            [row["id"] for row in scheduled], "episode inventory changed")
    decisions = [t.load(path) for path in sorted((root / "decisions").glob("*.json"))]
    cases = [row["case"] for row in decisions]
    require(len(cases) <= MAX_CALLS and len({x["id"] for x in cases}) == len(cases),
            "unexpected decision inventory")
    calls, cost = service.audit_records(
        root, ledger_root, STAGE, protocol, cases,
        dict(results=[row["result"] for row in decisions]), score, CONFIG)
    require(cost <= CAP and
            Decimal(manifest["protocol"]["pre_stage_budget"]["accounted_usd"]) +
            cost <= Decimal("8"), "Qwen stage/budget cap exceeded")
    by_id = {row["id"]: row for row in calls}
    profiles = prepared_profiles()
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
                        "missing Qwen decision")
                case = make_case(assignment, actor, stage, messages, index)
                row = indexed[position]
                position += 1
                require(row["case"] == case, "decision request changed")
                if row["result"]["status"] != "recorded":
                    raise EpisodeFailure("request_not_recorded")
                call = by_id[case["id"]]
                if not (call["result"]["usable"] and
                        call["result"]["valid_action"]):
                    raise EpisodeFailure("unusable_or_invalid_action")
                return t.load(root / "calls" / (case["id"] + ".json"))["final_content"]

            prepared = profiles[assignment["profile_id"]]["prepared"]
            try:
                actual = institution.episode(prepared, assignment["arm"], replay_ask)
                require(saved["status"] == "completed" and
                        actual == {key: value for key, value in saved.items()
                                   if key not in ("id", "status")} and
                        position == len(indexed), "completed episode replay differs")
            except EpisodeFailure as exc:
                require(saved["status"] == "failed" and
                        saved["error"] == str(exc) and position == len(indexed),
                        "failed episode replay differs")
        else:
            require(saved["status"] == "instrument_error" and
                    terminal["global_safety_stop"], "unexplained instrument state")
        records[(assignment["profile_id"], assignment["arm"])] = {
            key: value for key, value in saved.items() if key != "id"}
    readout = analysis.readout(list(profiles.values()), records)
    completed = sum(x["status"] == "completed" for x in terminal["episodes"])
    usable = sum(x["status"] == "recorded" and x["result"]["usable"] and
                 x["result"]["valid_action"] for x in calls)
    feasible = (completed == 21 and usable == MAX_CALLS and
                len(calls) == MAX_CALLS and not terminal["global_safety_stop"])
    return dict(protocol=protocol, assignments=terminal["episodes"],
                calls=calls, completed_episodes=completed,
                usable_actions=usable, feasibility_passed=feasible,
                readout=readout, accounted_usd=str(cost),
                global_safety_stop=terminal["global_safety_stop"],
                caveat=specification()["limitations"])


def export(root, ledger_root, target, destination, secret=None):
    helper = archive_source.archive_helpers()
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
                        contents[prefix + "/" + str(path.relative_to(directory))] = (
                            path.read_bytes())
            contents["expected_report.json"] = (
                json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = (
        "# Paper 3 Qwen constituent-institution discovery\n\n"
        "Seven constructed profiles × three arms; retain every completed and "
        "missing cell. This is mechanism discovery, not population evidence. "
        "From a fresh extracted directory: `python3 -I -S "
        "code/experiments/paper3_constituent_b_qwen_discovery.py . --replay "
        "--expected-protocol " + protocol + "`\n").encode()
    for relative, data in contents.items():
        helper.safe(target, relative)
        helper.credentials(data, secret)
    metadata = dict(format=helper.FORMAT, experiment_family=STAGE,
                    protocol=protocol,
                    files={path: t.sha(data) for path, data in sorted(contents.items())})
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
    require(ROOT == root / "code", "isolated replay needs bundled code")
    sys.addaudithook(helper.offline_guard)
    require(verify(root / "run")[1] == expected_protocol,
            "frozen Qwen protocol changed")
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
    require(args.expected_protocol, "explicit expected protocol required")
    if args.replay:
        print(json.dumps(replay(args.root, args.expected_protocol), indent=2))
        return
    require(verify(args.root)[1] == args.expected_protocol, "unexpected protocol")
    if args.export:
        require(args.target and args.archive, "archive paths required")
        value = export(args.root, BUDGET, args.target, args.archive, t.read_key())
    else:
        value = audit(args.root) if args.audit else execute(args.root, secret=t.read_key())
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
