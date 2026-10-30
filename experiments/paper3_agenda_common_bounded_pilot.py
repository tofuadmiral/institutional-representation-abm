"""Fresh paired sponsorship discovery with a bounded longer advocacy action.

Twelve new profiles; 7 advocacy actions are shared by sealed and public
arms, followed by 13 binding actions per arm. No repairs, replacements,
inference retries, fallback, restarts, or outcome-selected case changes.
"""
# ruff: noqa: E402
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import fcntl
from functools import cache
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import paper3_agenda_schema_gate as gate
from experiments import paper3_constituent_b_gptoss_action_gate as archive_source
from paper3 import agenda_common_design_v2 as design
from paper3 import agenda_common_interface_v2 as institution
from paper3 import agenda_sponsorship_institution as game
from paper3 import direct_ratification as base
from paper3 import hosted_reasoning_channel_calls as service
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure


t = gate.t
require = t.require
STAGE = "pivot_b_agenda_common_bounded_pilot_v1"
CAP = Decimal("3.10")
STOP = Decimal("8")
MAX_CALLS = 396
WORKERS = 4
CONFIG = gate.CONFIG
BUDGET = gate.BUDGET
GATE_ROOT = ROOT / "results/paper3/pivot_b_agenda_schema_gate_v1"
GATE_ARCHIVE = ROOT / "paper3/data/pivot_b_agenda_schema_gate_v1.zip"
GATE_PROTOCOL = "56c1b1371edbd845dbc8294b53c942dc2acd464199d58a61f4cfda295d0c8aab"
GATE_ARCHIVE_SHA = "1da44eb9a71ea7e83ea8bc182428f88e2652e706f4a3058a36a48b1962de88f3"


class EpisodeFailure(ValueError):
    """A saved action prefix ended without a usable binding decision."""


@cache
def assignments():
    rows = design.assignments()
    require(len(rows) == 12 and
            sum(row["intended_calls"] for row in rows) == MAX_CALLS,
            "common-transcript assignment inventory")
    return rows


@cache
def profiles():
    return {item["profile"]["id"]: item for item in design.profiles()}


def prerequisite(gate_root=GATE_ROOT, gate_archive=GATE_ARCHIVE,
                 ledger_root=BUDGET):
    require(t.sha(Path(gate_archive).read_bytes()) == GATE_ARCHIVE_SHA,
            "strict-interface gate archive changed")
    require(gate.verify(gate_root)[1] == GATE_PROTOCOL,
            "strict-interface gate protocol changed")
    report = gate.audit(gate_root, ledger_root)
    require(report["gate_passed"] and report["calls"] == 16 and
            report["valid"] == 16,
            "strict-interface gate did not pass")
    return dict(protocol=GATE_PROTOCOL,
                archive_sha256=GATE_ARCHIVE_SHA,
                report_sha256=t.sha(t.canonical(report).encode()),
                native_template=request([], 0, "vote", ("X", "Y")))


def prerequisite_paths(gate_root=GATE_ROOT, ledger_root=BUDGET):
    paths = [Path(gate_root) / name for name in
             ("manifest.json", "sources.json", "sessions/terminal.json")]
    paths += list((Path(ledger_root) / "entries").glob(gate.STAGE + "-*.json"))
    paths.append(Path(ledger_root) / "stages" / (gate.STAGE + ".json"))
    return paths


def request(messages, seed, stage, compromises):
    result = gate.request(messages, seed, stage, compromises)
    result["response_format"]["json_schema"]["schema"] = (
        institution.schema(stage, compromises))
    if stage == "advocacy":
        result["response_format"]["json_schema"]["name"] = (
            "paper3_agenda_advocacy_bounded")
    return result


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
        action = institution.parse_action(
            row["final_content"], case["context"]["stage"],
            tuple(case["context"]["compromises"]))
        result.update(valid_action=True, correct=True, action=action)
    except (ValueError, TypeError, KeyError) as exc:
        result["failure"] = type(exc).__name__
    return result


def reservation(req):
    wire = t.canonical(req)
    bound = len(wire.encode()) + 1024
    require(bound + CONFIG["output_bound"] <= gate.channel.CONTEXT,
            "conservative context bound")
    cost = ((Decimal(bound) * gate.channel.PRICE_IN +
             Decimal(CONFIG["output_bound"]) * gate.channel.PRICE_OUT) /
            Decimal(1000000))
    return dict(wire=wire, input_token_bound=bound, reserved_usd=str(cost))


def make_case(assignment, actor, stage, arm, messages, index):
    require(0 <= index < 33 and actor in base.ACTORS and
            stage in game.STAGES and
            ((stage == "advocacy" and arm is None and index < 7) or
             (stage in ("sponsor", "vote") and arm in game.ARMS and
              index >= 7)), "decision position")
    item = profiles()[assignment["profile_id"]]
    req = request(messages, assignment["seed_base"] + index,
                  stage, item["compromises"])
    reserve = reservation(req)
    return dict(id=assignment["id"] + f"-{index:02d}",
                context=dict(kind="action", stage=stage, actor=actor,
                             arm=arm, index=index,
                             profile_id=assignment["profile_id"],
                             compromises=list(item["compromises"])),
                request=req, request_text=reserve["wire"],
                request_sha256=t.sha(reserve["wire"].encode()),
                input_token_bound=reserve["input_token_bound"],
                reserved_usd=reserve["reserved_usd"])


def run_profile(assignment, item, ask, progress):
    """Mutable progress remains available when a decision fails mid-profile."""
    progress["advocacy"] = institution.advocacy(
        item, lambda actor, stage, messages, index:
        ask(actor, stage, None, messages, index))
    for position, arm in enumerate(assignment["arm_order"]):
        progress["arms"][arm] = institution.arm_episode(
            item, arm, progress["advocacy"],
            lambda actor, stage, messages, index:
            ask(actor, stage, arm, messages, 7 + 13 * position + index))
    return progress


@cache
def scripted_preflight():
    reserves = []
    bounds = []
    profile_map = profiles()
    for assignment in assignments():
        def scripted(actor, stage, arm, messages, index):
            case = make_case(assignment, actor, stage, arm, messages, index)
            reserves.append(Decimal(case["reserved_usd"]))
            bounds.append(case["input_token_bound"])
            if stage == "advocacy":
                return json.dumps(dict(message="é" * 266))
            if stage == "sponsor":
                return '{"policy":"none"}'
            return '{"vote":true}'

        progress = dict(advocacy=None, arms={})
        run_profile(assignment, profile_map[assignment["profile_id"]],
                    scripted, progress)
        require(len(progress["arms"]) == 2, "scripted paired episode")
    total = sum(reserves, Decimal(0))
    require(len(reserves) == MAX_CALLS and total <= CAP,
            "full-path reservation exceeds cap")
    return dict(intended_calls=MAX_CALLS,
                full_output_scripted_reservations_usd=str(total),
                max_input_bound=max(bounds),
                cap_usd=str(CAP))


def seed_audit(root=ROOT):
    planned = {row["seed_base"] + index for row in assignments()
               for index in range(33)}
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

    for directory, dirs, files in os.walk(Path(root) / "results/paper3"):
        dirs[:] = [name for name in dirs if not any(fragment in name for fragment in
                   ("portable", "bundle", "export", "replay", "__pycache__", "code"))]
        for name in files:
            path = Path(directory) / name
            if name != "manifest.json" and not (path.parent.name == "calls" and
                                                 name.endswith(".json")):
                continue
            value = t.load(path)
            walk(value.get("request", value) if path.parent.name == "calls" else value)
            inventory.append((str(path.relative_to(root)), t.sha(path.read_bytes())))
    require(not planned & observed, "historical request seed overlap")
    return dict(planned=sorted(planned), overlap=[],
                historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()))


@cache
def specification():
    return dict(name=STAGE, assignments=assignments(), workers=WORKERS,
                max_calls=MAX_CALLS, cap_usd=str(CAP),
                budget_stop_usd=str(STOP), model_configuration=CONFIG,
                strict_interface_gate=GATE_PROTOCOL,
                scripted_preflight=scripted_preflight(),
                new_gate_calls=0, inference_retries=0,
                failure_rule="First full 33-action profile is a content-blind engineering check. Thereafter four workers. Invalid or uncertified action fails only its profile; transport/accounting/source/identity/credential/budget/instrument safety stop prevents new admissions. No retry, repair, replacement, fallback or restart.",
                screen="Twelve new opportunity-conditioned profiles, eight split and four aligned. Public benefit or harm requires a sponsorship-selected floor change and at least 18 aggregate citizen utility difference in at least six split pairs, at most one opposing welfare pair or missing split pair, and at least three stable qualified aligned controls. Selected-case discovery only, not significance or confirmation.",
                limitations="One common arm-blind agent-authored transcript per profile; two institution arms differ only in prior formal-filing visibility. One Qwen model/provider and one trajectory per profile-arm; profile is the independent unit. Synthetic complete-information opportunity-conditioned templates are not population evidence. A lead requires untouched-profile, stochastic and second-model validation.")


def prepare(root, *, metadata=None, ledger_root=BUDGET,
            gate_root=GATE_ROOT, gate_archive=GATE_ARCHIVE):
    root = Path(root)
    require(not root.exists(), "fresh common-transcript directory required")
    inherited = prerequisite(gate_root, gate_archive, ledger_root)
    seeds = seed_audit()
    pending = gate.pending_inventory(ledger_root)
    if metadata is None:
        with t.opener().open(gate.channel.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    gate.check_endpoint(metadata)
    budget = Ledger(ledger_root).snapshot()
    require(budget["pending"] == len(pending) and
            Decimal(budget["accounted_usd"]) + CAP < STOP,
            "conservative $8 spending stop")
    paths = closure(ROOT, [Path(__file__),
                           ROOT / "analysis/paper3_contracts_archive.py",
                           ROOT / "tests/test_paper3_agenda_common_bounded_pilot.py",
                           BUDGET / "authority.json",
                           *prerequisite_paths(gate_root, ledger_root)])
    snapshot = {str(path.relative_to(ROOT)): path.read_text() for path in paths}
    protocol = dict(**specification(), inherited_prerequisite=inherited,
                    seed_audit=seeds, pre_stage_budget=budget,
                    prior_pending=pending, endpoint_metadata=metadata,
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
                "frozen common-transcript source changed: " + relative)
    require(all(manifest["protocol"].get(key) == value
                for key, value in specification().items()),
            "common-transcript specification changed")
    require(manifest["protocol"]["inherited_prerequisite"]["protocol"] ==
            GATE_PROTOCOL and
            manifest["protocol"]["seed_audit"]["planned"] ==
            sorted({row["seed_base"] + index for row in assignments()
                    for index in range(33)}) and
            not manifest["protocol"]["seed_audit"]["overlap"],
            "prerequisite or seed inventory changed")
    gate.check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, ledger_root=BUDGET, gate_root=GATE_ROOT,
            gate_archive=GATE_ARCHIVE, secret=None, send=None, lookup=None,
            clock=time.time, sleep=time.sleep):
    root = Path(root)
    manifest, protocol = verify(root)
    require(prerequisite(gate_root, gate_archive, ledger_root) ==
            manifest["protocol"]["inherited_prerequisite"],
            "live strict-interface prerequisite changed")
    require(0 <= clock() - manifest["protocol"]["metadata_observed_unix"] <= 3600,
            "stale endpoint metadata")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(all(not list((root / name).iterdir()) for name in
                    ("calls", "decisions", "episodes", "sessions")),
                "already started; no restart")
        ledger = Ledger(ledger_root)
        require(ledger.snapshot() == manifest["protocol"]["pre_stage_budget"] and
                gate.pending_inventory(ledger_root) ==
                manifest["protocol"]["prior_pending"],
                "pre-stage accounting changed")
        ledger.allocate(STAGE, CAP)
        atomic(root / "sessions/start.json", dict(protocol=protocol,
                                                  pid=os.getpid(),
                                                  started_unix=clock()))
        calls = service.Calls(root, ledger_root, STAGE, MAX_CALLS,
                              lambda: verify(root), score, CONFIG,
                              secret, send, lookup, clock, sleep)
        profile_map = profiles()

        def one(assignment):
            progress = dict(advocacy=None, arms={})
            if calls.stop.is_set():
                saved = dict(id=assignment["id"], status="not_started",
                             **progress)
            else:
                def ask(actor, stage, arm, messages, index):
                    case = make_case(assignment, actor, stage, arm,
                                     messages, index)
                    path = root / "decisions" / (case["id"] + ".json")
                    atomic(path, dict(case=case,
                                      result=dict(id=case["id"],
                                                  status="prepared")))
                    result = calls.one(case)
                    atomic(path, dict(case=case, result=result))
                    if result["status"] != "recorded":
                        raise EpisodeFailure("request_not_recorded")
                    row = t.load(root / "calls" / (case["id"] + ".json"))
                    if not (row["result"]["usable"] and
                            row["result"]["valid_action"] and
                            row["assessment"]["receipt_certified"]):
                        raise EpisodeFailure("unusable_invalid_or_uncertified_action")
                    return row["final_content"]

                try:
                    run_profile(assignment,
                                profile_map[assignment["profile_id"]],
                                ask, progress)
                    saved = dict(id=assignment["id"], status="completed",
                                 **progress)
                except EpisodeFailure as exc:
                    saved = dict(id=assignment["id"], status="failed",
                                 error=str(exc), **progress)
                except Exception as exc:
                    calls.stop.set()
                    saved = dict(id=assignment["id"], status="instrument_error",
                                 error=type(exc).__name__, **progress)
            atomic(root / "episodes" / (assignment["id"] + ".json"), saved)
            print(json.dumps(dict(event="common_transcript_profile_terminal",
                                  id=assignment["id"], status=saved["status"],
                                  budget=ledger.snapshot())), flush=True)
            return dict(id=assignment["id"], status=saved["status"])

        scheduled = manifest["protocol"]["assignments"]
        first = one(scheduled[0])
        first_calls = [t.load(path) for path in
                       (root / "calls").glob(scheduled[0]["id"] + "-*.json")]
        interface_passed = (first["status"] == "completed" and
                            len(first_calls) == 33 and
                            all(row["result"]["usable"] and
                                row["result"]["valid_action"] and
                                row["assessment"]["receipt_certified"]
                                for row in first_calls))
        if interface_passed and not calls.stop.is_set():
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                rest = list(pool.map(one, scheduled[1:]))
        else:
            rest = []
            for assignment in scheduled[1:]:
                saved = dict(id=assignment["id"], status="not_started",
                             advocacy=None, arms={})
                atomic(root / "episodes" / (assignment["id"] + ".json"), saved)
                rest.append(dict(id=assignment["id"], status="not_started"))
        terminal = dict(protocol=protocol, episodes=[first, *rest],
                        interface_gate_passed=interface_passed,
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
    require([row["id"] for row in terminal["episodes"]] ==
            [row["id"] for row in scheduled], "profile inventory")
    decisions = [t.load(path) for path in
                 sorted((root / "decisions").glob("*.json"))]
    cases = [row["case"] for row in decisions]
    require(len(cases) <= MAX_CALLS and
            len({case["id"] for case in cases}) == len(cases),
            "decision inventory")
    calls, cost = service.audit_records(
        root, ledger_root, STAGE, protocol, cases,
        dict(results=[row["result"] for row in decisions]), score, CONFIG)
    require(cost <= CAP and
            Decimal(manifest["protocol"]["pre_stage_budget"]["accounted_usd"]) +
            cost < STOP, "stage or cumulative budget exceeded")
    by_id = {row["id"]: row for row in calls}
    profile_map = profiles()
    outcomes, records = {}, {}
    for assignment, summary in zip(scheduled, terminal["episodes"], strict=True):
        saved = t.load(root / "episodes" / (assignment["id"] + ".json"))
        require(saved["id"] == summary["id"] and
                saved["status"] == summary["status"],
                "profile terminal changed")
        indexed = [row for row in decisions
                   if row["case"]["id"].startswith(assignment["id"] + "-")]
        indexed.sort(key=lambda row: row["case"]["context"]["index"])
        if saved["status"] == "not_started":
            require(not indexed and saved["advocacy"] is None and
                    not saved["arms"], "not-started profile has actions")
        elif saved["status"] in ("completed", "failed"):
            position = 0
            progress = dict(advocacy=None, arms={})

            def replay_ask(actor, stage, arm, messages, index):
                nonlocal position
                require(position < len(indexed), "missing decision")
                case = make_case(assignment, actor, stage, arm,
                                 messages, index)
                row = indexed[position]
                position += 1
                require(row["case"] == case, "common-transcript request changed")
                if row["result"]["status"] != "recorded":
                    raise EpisodeFailure("request_not_recorded")
                call = by_id[case["id"]]
                raw = t.load(root / "calls" / (case["id"] + ".json"))
                if not (call["result"]["usable"] and
                        call["result"]["valid_action"] and
                        raw["assessment"]["receipt_certified"]):
                    raise EpisodeFailure("unusable_invalid_or_uncertified_action")
                return raw["final_content"]

            try:
                run_profile(assignment, profile_map[assignment["profile_id"]],
                            replay_ask, progress)
                require(saved["status"] == "completed" and
                        saved["advocacy"] == progress["advocacy"] and
                        saved["arms"] == progress["arms"] and
                        position == len(indexed),
                        "completed profile replay differs")
            except EpisodeFailure as exc:
                require(saved["status"] == "failed" and
                        saved["error"] == str(exc) and
                        saved["advocacy"] == progress["advocacy"] and
                        saved["arms"] == progress["arms"] and
                        position == len(indexed),
                        "failed profile replay differs")
        else:
            require(saved["status"] == "instrument_error" and
                    terminal["global_safety_stop"],
                    "unexplained instrument state")
        for arm in game.ARMS:
            outcomes[assignment["profile_id"], arm] = (
                saved["arms"][arm]["outcome"]
                if saved["status"] == "completed" else None)
        records[assignment["id"]] = dict(
            status=saved["status"], advocacy=saved["advocacy"],
            arms=saved["arms"], failure=saved.get("error"),
            decision_count=len(indexed))
    first_id = scheduled[0]["id"]
    first_saved = t.load(root / "episodes" / (first_id + ".json"))
    actual_interface = (first_saved["status"] == "completed" and
                        sum(case["id"].startswith(first_id + "-")
                            for case in cases) == 33 and
                        all(row["result"]["usable"] and
                            row["result"]["valid_action"] and
                            t.load(root / "calls" / (row["id"] + ".json"))[
                                "assessment"]["receipt_certified"]
                            for row in calls
                            if row["id"].startswith(first_id + "-")))
    require(terminal["interface_gate_passed"] == actual_interface,
            "interface classification changed")
    if not actual_interface:
        require(all(row["status"] == "not_started" for row in
                    terminal["episodes"][1:]),
                "calls after failed interface check")
    completed = sum(row["status"] == "completed" for row in
                    terminal["episodes"])
    usable = sum(row["status"] == "recorded" and
                 row["result"]["usable"] and row["result"]["valid_action"]
                 for row in calls)
    return dict(protocol=protocol, assignments=terminal["episodes"],
                calls=calls, records=records,
                completed_profiles=completed, usable_actions=usable,
                all_profiles_complete=(completed == 12 and usable == MAX_CALLS and
                                       len(calls) == MAX_CALLS and
                                       not terminal["global_safety_stop"]),
                interface_gate_passed=actual_interface,
                selected_case_readout=design.screen(outcomes),
                accounted_usd=str(cost),
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
                        contents[prefix + "/" +
                                 str(path.relative_to(directory))] = path.read_bytes()
            contents["expected_report.json"] = (
                json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = (
        "# Common-transcript coalition-sponsorship discovery\n\n"
        "Retains all twelve paired profiles, seven shared advocacy actions "
        "per profile, six sponsorships and seven ballots per arm, failures, "
        "and person-level outcomes. Selected-case pilot only. From a fresh "
        "extraction run `python3 -I -S code/experiments/"
        "paper3_agenda_common_bounded_pilot.py . --replay "
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
    helper = archive_source.archive_helpers()
    root = Path(root).resolve()
    metadata = helper.verify_bundle(root, expected_protocol)
    require(metadata["experiment_family"] == STAGE, "wrong archive family")
    require(ROOT == root / "code", "isolated replay requires bundled code")
    sys.addaudithook(helper.offline_guard)
    require(verify(root / "run")[1] == expected_protocol,
            "frozen common-transcript protocol changed")
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
