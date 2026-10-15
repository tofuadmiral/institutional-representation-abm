"""Fresh release-right go/no-go discovery; six games, three coalition topologies.

Independent conditional utility draws, one pivotal and one nonpivotal game per
family. Twelve assigned institutional episodes, at most 432 reasoning actions.
This is a feasibility decision, not confirmatory evidence or a paper result.
"""

# ruff: noqa: E402
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
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

from experiments import paper3_mandate_release_episode_gate_v2 as gate
from experiments import paper3_constituent_b_gptoss_action_gate as archive_source
from paper3 import mandate_release_branching as branching
from paper3 import mandate_release_gonogo_analysis as analysis
from paper3 import mandate_release_gonogo_design as design
from paper3 import mandate_release_institution as institution
from paper3 import mandate_release_gonogo_interface as interface
from paper3 import hosted_reasoning_channel_calls as service
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure


t = gate.t
require = t.require
channel = gate.gate.channel
prior_schema = gate.gate.prior_schema
STAGE = "pivot_b_mandate_release_gonogo_v1"
CAP = Decimal("2.90")
STOP = Decimal("8")
WORKERS = 4
MAX_CALLS = 6 * 2 * 36
SEED_BASE = 2060000
CONFIG = dict(gate.CONFIG, output_bound=14000)
MAX_MESSAGE_JSON_BYTES = interface.MAX_MESSAGE_JSON_BYTES
BUDGET = gate.BUDGET
GATE_ROOT = ROOT / "results/paper3/pivot_b_mandate_release_episode_gate_v2"
GATE_ARCHIVE = ROOT / "paper3/data/pivot_b_mandate_release_episode_gate_v2.zip"
# Exact terminal, audited and independently replayed technical prerequisite.
GATE_PROTOCOL = "f970838a737e9a1e808de65d80015bba5a0cc221027cf01f0aafc1f314aa78b0"
GATE_ARCHIVE_SHA = "0c685bd74b79fc90bfef7d09f64596972a23cfafec6694e66ead986d1e663826"


class EpisodeFailure(ValueError):
    """One episode ended without a complete usable action history."""


@cache
def profiles():
    return {case.case_id: case for case in design.cases()}


@cache
def assignments():
    result = []
    for index, item in enumerate(design.cases()):
        for arm_position, arm in enumerate(
            institution.ARMS if index % 2 == 0 else tuple(reversed(institution.ARMS))
        ):
            assignment_index = 2 * index + arm_position
            result.append(dict(id=f"release-gonogo-{assignment_index:02d}",
                               case_id=item.case_id, arm=arm,
                               seed_base=SEED_BASE + 64 * assignment_index,
                               intended_calls=36))
    seeds = [row["seed_base"] + offset for row in result for offset in range(36)]
    require(len(result) == 12 and len(seeds) == MAX_CALLS and
            len(set(seeds)) == MAX_CALLS, "assignment/seed inventory")
    return result


def request(messages, seed, stage, case):
    result = channel.request_for(messages, seed)
    result["max_tokens"] = CONFIG["output_bound"]
    result["response_format"] = dict(
        type="json_schema",
        json_schema=dict(name=f"paper3_release_{stage}", strict=True,
                         schema=interface.schema(case, stage)),
    )
    return result


def score(row, call_case):
    result = dict(usable=False, valid_action=False, native_reasoning=None,
                  action=None, failure=None)
    if row.get("instrument_error") or "assessment" not in row:
        result["failure"] = "instrument_or_unfinished"
        return result
    assessed = service.assess(row, CONFIG)
    stream = assessed["stream"]
    native = service.native_evidence(stream)
    usable = (assessed["passed"] and stream["finish_reasons"] == ["stop"]
              and native["present"] and row["request"].get("reasoning") ==
              dict(enabled=True, exclude=False))
    result.update(usable=usable, native_reasoning=native)
    if not usable:
        result["failure"] = "transport_reasoning_or_completion"
        return result
    try:
        case = profiles()[call_case["context"]["case_id"]]
        action = interface.decode(case, call_case["context"]["stage"],
                                  row["final_content"])
        if "message" in action and len(json.dumps(
            action["message"], ensure_ascii=True).encode()) > MAX_MESSAGE_JSON_BYTES:
            raise ValueError("message serialization bound")
        result.update(valid_action=True, action=action)
    except (ValueError, TypeError, KeyError) as exc:
        result["failure"] = type(exc).__name__
    return result


def make_call(assignment, actor, stage, messages, index, shocked):
    require(0 <= index < 36 and actor in institution.ACTORS and
            stage in interface.STAGE_TASKS, "decision position")
    require((stage == "y_vote") == (type(shocked) is bool),
            "shock state only at Y ballot")
    case = profiles()[assignment["case_id"]]
    req = request(messages, assignment["seed_base"] + index, stage, case)
    wire = t.canonical(req)
    bound = len(wire.encode()) + 1024
    require(bound + CONFIG["output_bound"] <= channel.CONTEXT,
            "conservative context bound")
    reserve = ((Decimal(bound) * channel.PRICE_IN
                + Decimal(CONFIG["output_bound"]) * channel.PRICE_OUT)
               / Decimal(1000000))
    return dict(id=assignment["id"] + f"-{index:02d}",
                context=dict(case_id=assignment["case_id"],
                             arm=assignment["arm"], shock_branch=shocked,
                             actor=actor, stage=stage, index=index),
                request=req, request_text=wire,
                request_sha256=t.sha(wire.encode()),
                input_token_bound=bound, reserved_usd=str(reserve))


def run_assignment(assignment, ask, on_branch=None):
    case = profiles()[assignment["case_id"]]
    index = 0

    def decision(actor, stage, context, shocked):
        nonlocal index
        messages = interface.messages(case, actor, stage, context)
        result = ask(actor, stage, messages, index, shocked)
        index += 1
        return result

    pair = branching.episode_pair(case.game, assignment["arm"], 0, decision,
                                  on_complete=on_branch)
    require(index == 36, "completed branching episode has 36 decisions")
    return pair


@cache
def scripted_preflight():
    reserves = []
    bounds = []
    for assignment in assignments():
        def scripted(actor, stage, messages, index, shocked):
            call = make_call(assignment, actor, stage, messages, index, shocked)
            reserves.append(Decimal(call["reserved_usd"]))
            bounds.append(call["input_token_bound"])
            if stage in ("draft", "final"):
                return dict(second_project="Y1", coalition=[0, 1, 2, 3],
                            message="😀" * interface.MAX_MESSAGE_CHARS)
            if stage == "response":
                return dict(support=True, counter_project="Y1",
                            message="😀" * interface.MAX_MESSAGE_CHARS)
            if stage == "consent":
                return dict(consent=True)
            return dict(vote=False)

        run_assignment(assignment, scripted)
    total = sum(reserves, Decimal(0))
    require(len(reserves) == MAX_CALLS and total <= CAP,
            "full scripted path exceeds pilot cap")
    return dict(intended_calls=MAX_CALLS,
                max_message_json_bytes=MAX_MESSAGE_JSON_BYTES,
                full_output_scripted_reservations_usd=str(total),
                max_input_bound=max(bounds), cap_usd=str(CAP))


def seed_audit(root=ROOT):
    planned = {row["seed_base"] + offset for row in assignments()
               for offset in range(36)}
    observed = set()
    inventory = []

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
            if name != "manifest.json" and not (path.parent.name == "calls"
                                                  and name.endswith(".json")):
                continue
            value = t.load(path)
            walk(value.get("request", value) if path.parent.name == "calls" else value)
            inventory.append((str(path.relative_to(root)), t.sha(path.read_bytes())))
    require(not planned & observed, "pilot request seed overlap")
    return dict(planned=sorted(planned), overlap=[],
                historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()))


def prerequisite(gate_root=GATE_ROOT, gate_archive=GATE_ARCHIVE,
                 ledger_root=BUDGET):
    require(GATE_PROTOCOL is not None and GATE_ARCHIVE_SHA is not None,
            "technical gate has not been pinned")
    require(t.sha(Path(gate_archive).read_bytes()) == GATE_ARCHIVE_SHA,
            "technical gate archive changed")
    require(gate.verify(gate_root)[1] == GATE_PROTOCOL,
            "technical gate protocol changed")
    report = gate.audit(gate_root, ledger_root)
    require(report["technical_gate_passed"] and report["calls"] == 58 and
            report["completed"] == 2, "full-episode technical gate did not pass")
    return dict(protocol=GATE_PROTOCOL, archive_sha256=GATE_ARCHIVE_SHA,
                report_sha256=t.sha(t.canonical(report).encode()))


def prerequisite_paths(gate_root=GATE_ROOT, ledger_root=BUDGET):
    paths = [Path(gate_root) / name for name in
             ("manifest.json", "sources.json", "sessions/terminal.json")]
    paths += list((Path(ledger_root) / "entries").glob(gate.STAGE + "-*.json"))
    paths.append(Path(ledger_root) / "stages" / (gate.STAGE + ".json"))
    return paths


@cache
def specification():
    return dict(name=STAGE, assignments=assignments(), workers=WORKERS,
                max_calls=MAX_CALLS, cap_usd=str(CAP), budget_stop_usd=str(STOP),
                model_configuration=CONFIG,
                strict_interface_gate=GATE_PROTOCOL,
                scripted_preflight=scripted_preflight(),
                inference_retries=0,
                first_episode_gate="The first 36-action branch pair is a serial content-blind engineering stop gate; all actions must be usable, schema-valid, native-reasoning and billing-certified. No policy content criterion.",
                failure_rule="Content failure ends only its episode; transport, billing, identity, source, credential or budget fault stops new admissions. No retries, repairs, replacements, provider fallback or restart.",
                discovery_screen="Three independently drawn pivotal games and three nonpivotal comparators. Require all three pivotal pairs and at least two controls complete, four pairs with an active agreement, two identical active control agreements, same-direction Y1-exposed activation changes in at least two pivotal games and none opposite, plus nonzero expected district outcomes in at least two cases with changed agreements. Every missing pair contributes worst-case bounds; failures remain. A go proposes independent validation only.",
                opportunity_inventory=[dict(case_id=case.case_id, family=case.family, stratum=case.stratum, seed=case.seed, draw_index=case.draw_index, certificate=design.certificate(case.game, case.family, case.stratum)) for case in design.cases()],
                offline_diversity_audit=design.diversity_audit(),
                limitations="Independent draws conditional on three related coalition topologies, one model/provider and one trajectory per arm. Common sign templates, bounded synthetic utilities, known shock risk and no renegotiation. This is not a population sample. Citizens are outcomes, not independent experimental units.")


def prepare(root, *, metadata=None, ledger_root=BUDGET,
            gate_root=GATE_ROOT, gate_archive=GATE_ARCHIVE):
    root = Path(root)
    require(not root.exists(), "fresh pilot directory required")
    inherited = prerequisite(gate_root, gate_archive, ledger_root)
    seeds = seed_audit()
    pending = prior_schema.pending_inventory(ledger_root)
    if metadata is None:
        with t.opener().open(channel.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    prior_schema.check_endpoint(metadata)
    budget = Ledger(ledger_root).snapshot()
    require(budget["pending"] == len(pending) and
            Decimal(budget["accounted_usd"]) + CAP < STOP,
            "conservative $8 cumulative stop")
    paths = closure(ROOT, [Path(__file__),
                           ROOT / "analysis/paper3_contracts_archive.py",
                           ROOT / "tests/test_paper3_mandate_release_gonogo.py",
                           ROOT / "tests/test_paper3_mandate_release_branching.py",
                           ROOT / "tests/test_paper3_mandate_release_gonogo_design.py",
                           ROOT / "tests/test_paper3_mandate_release_gonogo_analysis.py",
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
                "unsafe source path")
        require(t.sha((Path(code_root) / path).read_bytes()) ==
                t.sha(snapshot[relative].encode()) == expected,
                "frozen pilot source changed: " + relative)
    require(all(t.canonical(manifest["protocol"].get(key)) == t.canonical(value)
                for key, value in specification().items()),
            "pilot specification changed")
    require(manifest["protocol"]["inherited_prerequisite"]["protocol"] ==
            GATE_PROTOCOL and manifest["protocol"]["seed_audit"]["planned"] ==
            sorted({row["seed_base"] + offset for row in assignments()
                    for offset in range(36)}) and
            not manifest["protocol"]["seed_audit"]["overlap"],
            "prerequisite or seed audit")
    prior_schema.check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, ledger_root=BUDGET, gate_root=GATE_ROOT,
            gate_archive=GATE_ARCHIVE, secret=None, send=None, lookup=None,
            clock=time.time, sleep=time.sleep):
    root = Path(root)
    manifest, protocol = verify(root)
    require(prerequisite(gate_root, gate_archive, ledger_root) ==
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
        require(ledger.snapshot() == manifest["protocol"]["pre_stage_budget"] and
                prior_schema.pending_inventory(ledger_root) ==
                manifest["protocol"]["prior_pending"],
                "pre-stage accounting changed")
        ledger.allocate(STAGE, CAP)
        atomic(root / "sessions/start.json", dict(protocol=protocol,
                                                  pid=os.getpid(),
                                                  started_unix=clock()))
        calls = service.Calls(root, ledger_root, STAGE, MAX_CALLS,
                              lambda: verify(root), score, CONFIG,
                              secret, send, lookup, clock, sleep)

        def one(assignment):
            if calls.stop.is_set():
                saved = dict(id=assignment["id"], status="not_started",
                             outcome=None)
            else:
                partial = [None, None]

                def on_branch(shocked, outcome):
                    partial[int(shocked)] = asdict(outcome)
                    atomic(root / "episodes" / (assignment["id"] + ".json"),
                           dict(id=assignment["id"], status="in_progress",
                                outcome=partial))

                def ask(actor, stage, messages, index, shocked):
                    call = make_call(assignment, actor, stage, messages, index, shocked)
                    path = root / "decisions" / (call["id"] + ".json")
                    atomic(path, dict(case=call, result=dict(
                        id=call["id"], status="prepared")))
                    result = calls.one(call)
                    atomic(path, dict(case=call, result=result))
                    if result["status"] != "recorded":
                        raise EpisodeFailure("request_not_recorded")
                    row = t.load(root / "calls" / (call["id"] + ".json"))
                    if not (row["result"]["usable"] and
                            row["result"]["valid_action"] and
                            row["assessment"]["receipt_certified"]):
                        raise EpisodeFailure("unusable_invalid_or_uncertified_action")
                    return row["result"]["action"]

                try:
                    run_assignment(assignment, ask, on_branch)
                    saved = dict(id=assignment["id"], status="completed",
                                 outcome=partial)
                except EpisodeFailure as exc:
                    saved = dict(id=assignment["id"], status="failed",
                                 error=str(exc), outcome=partial)
                except Exception as exc:
                    calls.stop.set()
                    saved = dict(id=assignment["id"], status="instrument_error",
                                 error=type(exc).__name__, outcome=partial)
            atomic(root / "episodes" / (assignment["id"] + ".json"), saved)
            print(json.dumps(dict(event="release_gonogo_terminal",
                                  id=assignment["id"], status=saved["status"],
                                  budget=ledger.snapshot())), flush=True)
            return dict(id=assignment["id"], status=saved["status"])

        scheduled = manifest["protocol"]["assignments"]
        first = one(scheduled[0])
        first_calls = [t.load(path) for path in
                       (root / "calls").glob(scheduled[0]["id"] + "-*.json")]
        interface_passed = (first["status"] == "completed" and
                            len(first_calls) == 36 and
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
                             outcome=None)
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
            [row["id"] for row in scheduled], "episode inventory")
    decisions = [t.load(path) for path in
                 sorted((root / "decisions").glob("*.json"))]
    calls = [row["case"] for row in decisions]
    require(len(calls) <= MAX_CALLS and
            len({row["id"] for row in calls}) == len(calls),
            "decision inventory")
    call_reports, cost = service.audit_records(
        root, ledger_root, STAGE, protocol, calls,
        dict(results=[row["result"] for row in decisions]), score, CONFIG)
    require(cost <= CAP and
            Decimal(manifest["protocol"]["pre_stage_budget"]["accounted_usd"]) +
            cost < STOP, "stage or cumulative budget exceeded")
    by_id = {row["id"]: row for row in call_reports}
    outcomes = {}
    episode_reports = []
    for assignment, summary in zip(scheduled, terminal["episodes"], strict=True):
        saved = t.load(root / "episodes" / (assignment["id"] + ".json"))
        require(saved["id"] == summary["id"] and
                saved["status"] == summary["status"],
                "episode terminal changed")
        indexed = [row for row in decisions
                   if row["case"]["id"].startswith(assignment["id"] + "-")]
        indexed.sort(key=lambda row: row["case"]["context"]["index"])
        require([row["case"]["context"]["index"] for row in indexed] ==
                list(range(len(indexed))), "episode decision prefix")
        if saved["status"] == "not_started":
            require(not indexed and saved["outcome"] is None,
                    "not-started episode has decisions")
        elif saved["status"] in ("completed", "failed"):
            position = 0
            replayed_parts = [None, None]
            branch_outcomes = {}

            def replay_branch(shocked, outcome):
                replayed_parts[int(shocked)] = asdict(outcome)
                branch_outcomes[shocked] = outcome

            def replay_ask(actor, stage, messages, index, shocked):
                nonlocal position
                require(position < len(indexed), "missing decision")
                call = make_call(assignment, actor, stage, messages, index, shocked)
                record = indexed[position]
                position += 1
                require(record["case"] == call, "agent request changed")
                if record["result"]["status"] != "recorded":
                    raise EpisodeFailure("request_not_recorded")
                audited = by_id[call["id"]]
                raw = t.load(root / "calls" / (call["id"] + ".json"))
                if not (audited["result"]["usable"] and
                        audited["result"]["valid_action"] and
                        raw["assessment"]["receipt_certified"]):
                    raise EpisodeFailure("unusable_invalid_or_uncertified_action")
                return audited["result"]["action"]

            try:
                run_assignment(assignment, replay_ask, replay_branch)
                require(saved["status"] == "completed" and
                        all(part is not None for part in replayed_parts),
                        "completed episode changed")
            except EpisodeFailure as exc:
                require(saved["status"] == "failed" and
                        saved["error"] == str(exc),
                        "failure changed")
            require(t.canonical(saved["outcome"]) ==
                    t.canonical(replayed_parts),
                    "saved partial branch outcomes changed")
            for shocked, outcome in branch_outcomes.items():
                outcomes[(assignment["case_id"], assignment["arm"], shocked)] = outcome
            require(position == len(indexed), "extra decisions after episode end")
        elif saved["status"] == "instrument_error":
            require(type(saved["outcome"]) is list and
                    len(saved["outcome"]) == 2 and terminal["global_safety_stop"],
                    "unexplained instrument error")
        else:
            raise ValueError("unknown episode status")
        episode_reports.append(dict(id=assignment["id"], case_id=assignment["case_id"],
                                    arm=assignment["arm"], status=saved["status"],
                                    decisions=len(indexed),
                                    outcome=saved["outcome"]))
    require(len(list((root / "episodes").glob("*.json"))) == len(scheduled),
            "unexpected episode files")
    first = episode_reports[0]
    first_calls = [row for row in calls
                   if row["id"].startswith(scheduled[0]["id"] + "-")]
    interface_passed = (first["status"] == "completed" and
                        len(first_calls) == 36 and
                        all(by_id[row["id"]]["result"]["usable"] and
                            by_id[row["id"]]["result"]["valid_action"] and
                            t.load(root / "calls" / (row["id"] + ".json"))
                            ["assessment"]["receipt_certified"]
                            for row in first_calls))
    require(terminal["interface_gate_passed"] == interface_passed,
            "first-episode stop gate changed")
    if not interface_passed:
        require(all(row["status"] == "not_started"
                    for row in episode_reports[1:]),
                "later episode started after failed interface gate")
    selected = analysis.screen(outcomes)
    return dict(protocol=protocol, assignments=episode_reports,
                calls=len(list((root / "calls").glob("*.json"))),
                completed=sum(row["status"] == "completed" for row in episode_reports),
                failed=sum(row["status"] == "failed" for row in episode_reports),
                not_started=sum(row["status"] == "not_started" for row in episode_reports),
                instrument_error=sum(row["status"] == "instrument_error"
                                     for row in episode_reports),
                interface_gate_passed=interface_passed,
                global_safety_stop=terminal["global_safety_stop"],
                accounted_usd=str(cost), selected_case_screen=selected,
                caveat="Three selected synthetic opportunity topologies on one model route. A behavioral lead is mechanism discovery, not publication evidence; failed prefixes and every citizen outcome are retained.")


def export(root, ledger_root, target, destination, secret=None):
    helper = archive_source.archive_helpers()
    root, ledger_root, target = map(lambda path: Path(path).resolve(),
                                    (root, ledger_root, target))
    require((root / "sessions/terminal.json").is_file(), "pilot not terminal")
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
        "# Constituent-release branching discovery pilot\n\n"
        "Selected-case mechanism discovery only, not publication evidence. "
        "Preserve every failed prefix and citizen outcome. "
        "From a fresh extraction run `python3 -I -S "
        "code/experiments/paper3_mandate_release_gonogo.py "
        ". --replay --expected-protocol " + protocol + "`.\n").encode()
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
            "frozen pilot protocol changed")
    report = audit(root / "run", root / "ledger")
    require(t.canonical(report) ==
            t.canonical(t.load(root / "expected_report.json")),
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
