"""Seven-profile gpt-oss constituent B institutional discovery runner.

This distinct, at-most-630-call/$3 stage is within the $8 cumulative stop
point authorized by Fuad. Capability records remain separately immutable.
"""
from __future__ import annotations

import argparse
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

from experiments import paper3_constituent_b_gptoss_action_gate as gate_runner
from experiments import paper3_constituent_b_gptoss_tool_gate as factual_gate
from experiments import paper3_transport_diagnostic as t
from paper3 import coalition_contracts as game
from paper3 import constituent_b_gptoss_discovery_analysis as analysis
from paper3 import constituent_b_gptoss_discovery_design as design
from paper3 import constituent_b_institution as institution
from paper3 import constituent_b_gptoss_discovery_requests as requests
from paper3 import constituent_b_tool_interface as tool
from paper3 import hosted_reasoning_channel_calls as service
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure


require = t.require
STAGE = "pivot_b_gptoss_constituent_discovery_v1"
CAP = requests.CAP
MAX_CALLS = requests.MAX_CALLS
WORKERS = 1
BUDGET = gate_runner.BUDGET
GATE_ROOT = ROOT / "results/paper3/pivot_b_gptoss_action_gate_v1"
FACT_ROOT = ROOT / "results/paper3/pivot_b_gptoss_tool_gate_v1"
CONFIG = gate_runner.CONFIG


class EpisodeFailure(ValueError):
    """A prespecified model/transport failure, not a repaired action."""


def assignments():
    rows = design.assignments()
    require(len(rows) == 21 and sum(row["intended_calls"] for row in rows) == MAX_CALLS
            and [row["phase"] for row in rows] == [1] * 3 + [2] * 18,
            "discovery assignment schedule changed")
    return rows


def prerequisite(gate_root=GATE_ROOT, fact_root=FACT_ROOT, ledger_root=BUDGET):
    """Keep both capability records separate; never convert a failed gate to a pass."""
    action_manifest, action_protocol = gate_runner.verify(gate_root)
    action_report = gate_runner.audit(gate_root, ledger_root)
    fact_manifest, fact_protocol = factual_gate.verify(fact_root)
    fact_report = factual_gate.audit(fact_root, ledger_root)
    require(action_report["protocol"] == action_protocol and
            action_report["gate_passed"] and action_report["calls"] == 3,
            "fresh action diagnostic did not pass")
    fact_rows = fact_report["assignments"]
    require(fact_report["protocol"] == fact_protocol and
            not fact_report["gate_passed"] and fact_report["calls"] == 10 and
            len(fact_rows) == 12 and
            all(row["status"] == "recorded" and row["result"]["usable"] and
                row["result"]["valid_action"] and row["result"]["exact"]
                for row in fact_rows[:9]) and
            fact_rows[9]["id"] == "fresh-action-draft" and
            fact_rows[9]["status"] == "recorded" and
            not fact_rows[9]["result"]["usable"] and
            all(row["status"] == "not_started" for row in fact_rows[10:]),
            "historical factual gate evidence changed")
    require(action_manifest["protocol"]["model_configuration"] ==
            fact_manifest["protocol"]["model_configuration"] == CONFIG,
            "capability records use different model/provider")
    return dict(action=dict(protocol=action_protocol, report=action_report,
                            report_sha256=t.sha(t.canonical(action_report).encode())),
                factual=dict(protocol=fact_protocol, report=fact_report,
                             report_sha256=t.sha(t.canonical(fact_report).encode())),
                limitation="Action-only diagnostic passed; the 12-case factual/tool gate remains failed after nine exact fixed reports and a provider 502. Neither record is institutional evidence.")


def prerequisite_paths(gate_root=GATE_ROOT, fact_root=FACT_ROOT, ledger_root=BUDGET):
    ledger_root = Path(ledger_root)
    paths = []
    for directory, stage in ((Path(gate_root), gate_runner.STAGE),
                             (Path(fact_root), factual_gate.STAGE)):
        paths += [ROOT / p for p in t.load(directory / "manifest.json")["sources"]]
        paths += [path for path in directory.rglob("*.json") if path.is_file()]
        paths += list((ledger_root / "entries").glob(stage + "-*.json"))
        paths.append(ledger_root / "stages" / (stage + ".json"))
    return paths


def prepared_profiles():
    return {item["prepared"]["contract_profile"]["id"]: item
            for item in design.profiles()}


def make_case(assignment, actor, stage, messages, index):
    require(0 <= index < 30 and actor in game.ACTORS and
            stage in ("draft", "response", "final", "consent", "first_vote", "second_vote"),
            "invalid decision position")
    key = assignment["id"] + f"-{index:02d}"
    req = requests.request(messages, assignment["seed_base"] + index, stage)
    reservation = requests.reservation(req)
    require(reservation["wire"] == t.canonical(req), "noncanonical request")
    return dict(id=key, context=dict(assignment=assignment["id"],
                                     profile_id=assignment["profile_id"],
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
    usable = (assessed["passed"] and summary["finish_reasons"] == ["tool_calls"]
              and native["present"] and
              row["request"].get("reasoning") == dict(effort="medium", exclude=False))
    report.update(usable=usable, native_reasoning=native)
    if not usable:
        report["failure"] = "transport_reasoning_or_completion"
        return report
    try:
        action = game.parse_action(json.dumps(tool.arguments(row["stream"])),
                                   case["context"]["stage"])
        report.update(valid_action=True, action=action)
    except (ValueError, TypeError, KeyError) as exc:
        report["failure"] = type(exc).__name__
    return report


def seed_audit(root=ROOT):
    planned = {a["seed_base"] + i for a in assignments() for i in range(30)}
    observed, inventory = set(), []

    def walk(value, key=""):
        if isinstance(value, dict):
            for field, child in value.items():
                walk(child, field)
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
            if path.parent.name == "calls":
                walk(value.get("request", value))
            else:
                walk(value)
            inventory.append((str(path.relative_to(root)), t.sha(path.read_bytes())))
    require(not planned & observed, "historical discovery seed overlap")
    return dict(planned_unique=sorted(planned), intended_calls=MAX_CALLS,
                paired_across_arms=True, overlap=[], historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()))


@lru_cache(maxsize=1)
def specification():
    return dict(name=STAGE, assignments=assignments(), max_calls=MAX_CALLS,
                workers=WORKERS, cap_usd=str(CAP), budget_cap_usd="8.00",
                model_configuration=CONFIG,
                discovery_preflight=requests.scripted_preflight(),
                new_gate_calls=0, inference_retries=0,
                receipt_offsets_seconds=[0, 20, 40, 60],
                failure_rule="One worker; invalid/unusable output or billing/identity/source error stops new admissions. No retry, replacement, repair, fallback or restart. Retain all twenty-one assigned episode statuses and prefixes.",
                phase_rule="All three first-profile arms (90 decisions) must complete technically before the other eighteen assignments; no favorable-effect filter.",
                feasibility_gate="All twenty-one episodes complete, all 630 calls usable, locally legal and billing-certified, no global safety stop. Technical feasibility is not scientific success.",
                readout="All seven profiles, three arms, pre-vote terms, requested and executed ballots, seven district utilities/regrets, all 63 citizen outcomes per profile and pairwise finite missingness bounds.",
                limitations="Seven distinct utility structures from two seeded realizations of constructed archetypes, one model/provider; no population or paper-worthy causal prevalence inference. Mechanically changed votes are not agent adaptation.")


def prepare(root, *, metadata=None, ledger_root=BUDGET, gate_root=GATE_ROOT,
            fact_root=FACT_ROOT):
    root = Path(root)
    require(not root.exists(), "fresh pilot directory required")
    inherited = prerequisite(gate_root, fact_root, ledger_root)
    seeds = seed_audit()
    if metadata is None:
        with t.opener().open(gate_runner.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    gate_runner.check_endpoint(metadata)
    budget = Ledger(ledger_root).snapshot()
    require(budget["pending"] == 0 and
            Decimal(budget["accounted_usd"]) + CAP <= Decimal("8"),
            "pilot budget baseline")
    roots = [Path(__file__), ROOT / "analysis/paper3_contracts_archive.py",
             ROOT / "tests/test_paper3_constituent_b_gptoss_discovery_runner.py",
             ROOT / "tests/test_paper3_constituent_b_gptoss_discovery_analysis.py",
             Path(ledger_root) / "authority.json",
             *prerequisite_paths(gate_root, fact_root, ledger_root)]
    paths = closure(ROOT, roots)
    snapshot = {str(path.relative_to(ROOT)): path.read_text() for path in paths}
    protocol = dict(**specification(), inherited_prerequisite=inherited,
                    seed_audit=seeds, pre_stage_budget=budget,
                    endpoint_metadata=metadata, metadata_observed_unix=time.time())
    manifest = dict(protocol=protocol,
                    sources={path: t.sha(value.encode()) for path, value in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    for name in ("calls", "decisions", "episodes", "sessions"):
        (root / name).mkdir()
    atomic(root / "sources.json", snapshot)
    atomic(root / "manifest.json", manifest)
    return t.sha(t.canonical(manifest).encode())


def verify(root, code_root=ROOT):
    root = Path(root)
    manifest, snapshot = t.load(root / "manifest.json"), t.load(root / "sources.json")
    require(set(snapshot) == set(manifest["sources"]), "pilot source inventory")
    for relative, expected in manifest["sources"].items():
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts, "unsafe pilot source")
        require(t.sha((Path(code_root) / path).read_bytes()) ==
                t.sha(snapshot[relative].encode()) == expected,
                "frozen pilot source changed: " + relative)
    require(all(manifest["protocol"].get(key) == value
                for key, value in specification().items()), "pilot specification changed")
    inherited = manifest["protocol"]["inherited_prerequisite"]
    require(inherited["action"]["report"]["gate_passed"] and
            inherited["action"]["report"]["calls"] == 3 and
            not inherited["factual"]["report"]["gate_passed"] and
            inherited["factual"]["report"]["calls"] == 10 and
            all(item["report_sha256"] == t.sha(t.canonical(item["report"]).encode())
                for item in (inherited["action"], inherited["factual"])),
            "capability evidence changed")
    require(manifest["protocol"]["seed_audit"]["planned_unique"] ==
            sorted({a["seed_base"] + i for a in assignments() for i in range(30)}) and
            not manifest["protocol"]["seed_audit"]["overlap"], "pilot seed audit")
    gate_runner.check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, ledger_root=BUDGET, gate_root=GATE_ROOT, fact_root=FACT_ROOT,
            secret=None,
            send=None, lookup=None, clock=time.time, sleep=time.sleep):
    root = Path(root)
    manifest, protocol = verify(root)
    require(prerequisite(gate_root, fact_root, ledger_root) ==
            manifest["protocol"]["inherited_prerequisite"], "gate replay changed")
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
        profiles = prepared_profiles()
        summaries = []
        for assignment in manifest["protocol"]["assignments"]:
            if calls.stop.is_set():
                episode = dict(id=assignment["id"], status="not_started")
            else:
                prepared = profiles[assignment["profile_id"]]["prepared"]

                def ask(actor, stage, messages, index):
                    case = make_case(assignment, actor, stage, messages, index)
                    path = root / "decisions" / (case["id"] + ".json")
                    atomic(path, dict(case=case, result=dict(id=case["id"],
                                                              status="prepared")))
                    status = calls.one(case)
                    atomic(path, dict(case=case, result=status))
                    if status["status"] != "recorded":
                        raise EpisodeFailure("request_not_recorded")
                    row = t.load(root / "calls" / (case["id"] + ".json"))
                    if not (row["result"]["usable"] and row["result"]["valid_action"]):
                        raise EpisodeFailure("unusable_or_invalid_action")
                    return json.dumps(row["result"]["action"], sort_keys=True)

                try:
                    episode = dict(id=assignment["id"], status="completed",
                                   **institution.episode(prepared, assignment["arm"], ask))
                except EpisodeFailure as exc:
                    calls.stop.set()
                    episode = dict(id=assignment["id"], status="failed", error=str(exc))
                except Exception as exc:
                    calls.stop.set()
                    episode = dict(id=assignment["id"], status="instrument_error",
                                   error=type(exc).__name__)
            atomic(root / "episodes" / (assignment["id"] + ".json"), episode)
            summaries.append(dict(id=assignment["id"], status=episode["status"]))
            print(json.dumps(dict(event="constituent_b_episode_terminal",
                                  id=assignment["id"], status=episode["status"],
                                  budget=ledger.snapshot())), flush=True)
            if len(summaries) == 3 and any(row["status"] != "completed" for row in summaries):
                calls.stop.set()
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
            terminal["protocol"] == protocol, "pilot terminal protocol mismatch")
    scheduled = manifest["protocol"]["assignments"]
    require([episode["id"] for episode in terminal["episodes"]] ==
            [assignment["id"] for assignment in scheduled], "episode inventory changed")
    decisions = [t.load(path) for path in sorted((root / "decisions").glob("*.json"))]
    cases = [item["case"] for item in decisions]
    require(len(cases) <= MAX_CALLS and len({case["id"] for case in cases}) == len(cases) and
            {case["context"]["assignment"] for case in cases} <=
            {assignment["id"] for assignment in scheduled}, "unexpected decisions")
    call_reports, cost = service.audit_records(
        root, ledger_root, STAGE, protocol, cases,
        dict(results=[item["result"] for item in decisions]), score, CONFIG)
    require(cost <= CAP and
            Decimal(manifest["protocol"]["pre_stage_budget"]["accounted_usd"]) + cost <=
            Decimal("8"), "stage or shared cap exceeded")
    reports_by_id = {row["id"]: row for row in call_reports}
    profiles = prepared_profiles()
    records = {}
    for assignment, summary in zip(scheduled, terminal["episodes"], strict=True):
        saved = t.load(root / "episodes" / (assignment["id"] + ".json"))
        require(saved["id"] == summary["id"] and saved["status"] == summary["status"],
                "episode terminal changed")
        indexed = [item for item in decisions
                   if item["case"]["context"]["assignment"] == assignment["id"]]
        indexed.sort(key=lambda item: item["case"]["context"]["index"])
        if saved["status"] == "not_started":
            require(not indexed, "not-started episode has decisions")
        elif saved["status"] in ("completed", "failed"):
            index = 0

            def replay_ask(actor, stage, messages, position):
                nonlocal index
                require(position == index and index < len(indexed), "missing decision")
                case = make_case(assignment, actor, stage, messages, position)
                item = indexed[index]
                index += 1
                require(item["case"] == case, "decision request changed")
                status = item["result"]
                if status["status"] != "recorded":
                    raise EpisodeFailure("request_not_recorded")
                call = reports_by_id[case["id"]]
                if not (call["result"]["usable"] and call["result"]["valid_action"]):
                    raise EpisodeFailure("unusable_or_invalid_action")
                return json.dumps(call["result"]["action"], sort_keys=True)

            prepared = profiles[assignment["profile_id"]]["prepared"]
            try:
                actual = institution.episode(prepared, assignment["arm"], replay_ask)
                require(saved["status"] == "completed" and
                        actual == {key: value for key, value in saved.items()
                                   if key not in ("id", "status")} and index == len(indexed),
                        "completed episode replay differs")
            except EpisodeFailure as exc:
                require(saved["status"] == "failed" and saved["error"] == str(exc) and
                        index == len(indexed) and terminal["global_safety_stop"],
                        "failed episode replay differs")
        else:
            require(saved["status"] == "instrument_error" and
                    terminal["global_safety_stop"], "unexplained instrument state")
        records[(assignment["profile_id"], assignment["arm"])] = {
            key: value for key, value in saved.items() if key != "id"}
    readout = analysis.readout(list(profiles.values()), records)
    completed = sum(row["status"] == "completed" for row in terminal["episodes"])
    usable = sum(row["status"] == "recorded" and row["result"]["usable"] and
                 row["result"]["valid_action"] for row in call_reports)
    feasible = (completed == 21 and usable == MAX_CALLS and
                len(call_reports) == MAX_CALLS and not terminal["global_safety_stop"])
    return dict(protocol=protocol, assignments=terminal["episodes"], calls=call_reports,
                completed_episodes=completed, usable_actions=usable,
                feasibility_passed=feasible, readout=readout,
                accounted_usd=str(cost), global_safety_stop=terminal["global_safety_stop"],
                caveat=specification()["limitations"])


def export(root, ledger_root, target, destination, secret=None):
    helper = gate_runner.archive_helpers()
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
                        contents[prefix + "/" + str(path.relative_to(directory))] = path.read_bytes()
            contents["expected_report.json"] = (
                json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = (
        "# Paper 3 gpt-oss constituent B discovery\n\n"
        "Seven constructed utility structures, three arms, at most 630 calls. Retains all twenty-one "
        "assignments, failures, 63 citizens per profile and finite missingness bounds. "
        "Completion is mechanism discovery, not population or paper evidence.\n\n"
        "From a fresh extracted directory: `python3 -I -S "
        "code/experiments/paper3_constituent_b_gptoss_discovery.py . --replay --expected-protocol "
        + protocol + "`\n").encode()
    for relative, data in contents.items():
        helper.safe(target, relative)
        helper.credentials(data, secret)
    metadata = dict(format=helper.FORMAT, experiment_family=STAGE, protocol=protocol,
                    files={path: t.sha(data) for path, data in sorted(contents.items())})
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
    helper = gate_runner.archive_helpers()
    root = Path(root).resolve()
    metadata = helper.verify_bundle(root, expected_protocol)
    require(metadata["experiment_family"] == STAGE, "wrong archive family")
    require(ROOT == root / "code", "replay needs bundled source under isolated Python")
    sys.addaudithook(helper.offline_guard)
    require(verify(root / "run")[1] == expected_protocol, "frozen protocol changed")
    report = audit(root / "run", root / "ledger")
    require(report == t.load(root / "expected_report.json"), "archived report differs")
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
