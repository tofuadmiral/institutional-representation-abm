"""Prospective election/coalition mechanism pilot; never an automatic launch.

Four selected seven-representative profiles x four institutional arms. Every
synthetic citizen casts a deterministic retrospective ballot. The behavioral
test is the representative's own consent/requested vote *before* controller
enforcement or election tally. A four-call action-channel gate precedes the
16 episodes. No call is retried, repaired, replaced, or attributed to another
model route. Freeze and budget checks apply before any paid request.
"""
# ruff: noqa: E402  # The frozen archive's code directory is set before local imports.
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
from paper3 import electoral_accountability as game
from paper3 import electoral_accountability_design as design
from paper3 import electoral_accountability_analysis as analysis
from paper3 import hosted_reasoning_channel_calls as service
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure

t = gate.t
require = t.require
STAGE = "pivot_b_electoral_accountability_v1"
CAP = Decimal("1.25")
STOP = Decimal("8")
GATE_CALLS = 4
PILOT_CALLS = 224
MAX_CALLS = GATE_CALLS + PILOT_CALLS
GATE_SEED_BASE = 9200000
EPISODE_SEED_BASE = 9201000
WORKERS = 4
BUDGET = gate.BUDGET
CONFIG = gate.CONFIG
GATE_ROOT = ROOT / "results/paper3/pivot_b_direct_ratification_gate_v1"
GATE_ARCHIVE = ROOT / "results/paper3/pivot_b_direct_ratification_gate_v1_export"
GATE_PROTOCOL = "31c206dd1f114e2864da65de89f3d023d082e48a0c50ddf08c1f9ecf9efb1b0f"
PRIOR_ROOT = ROOT / "results/paper3/pivot_b_ratification_disclosure_chamber_v1"
PRIOR_EXPORT = ROOT / "results/paper3/pivot_b_ratification_disclosure_chamber_v1_export"
PRIOR_PROTOCOL = "09a9a83b13b8e47a20e76f55cb0aeb4b7cd93f2f9e63f1376ef5143a36ab4c22"


class EpisodeFailure(ValueError):
    """An incomplete arm, retained without content repair."""


def assignments():
    profile_index = {item["id"]: index
                     for index, item in enumerate(design.inventory())}
    rows = [dict(**row, seed_base=EPISODE_SEED_BASE +
                 profile_index[row["profile_id"]] * 20,
                 intended_calls=14)
            for row in design.candidate_assignments()]
    require(len(rows) == 16 and len({row["id"] for row in rows}) == 16 and
            sum(row["intended_calls"] for row in rows) == PILOT_CALLS,
            "candidate assignment inventory")
    require(all(len({row["seed_base"] for row in rows
                     if row["profile_id"] == profile_id}) == 1
                for profile_id in profile_index), "within-profile seed pairing")
    return rows


def profiles():
    return {row["id"]: row for row in design.inventory()}


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


def make_case(identifier, actor, stage, messages, seed, index, kind,
              profile_id=None, arm=None):
    require(actor in game.ACTORS and stage in game.STAGES and
            kind in ("gate", "episode"), "decision context")
    req = request(messages, seed)
    reserve = reservation(req)
    require(reserve["wire"] == t.canonical(req), "noncanonical request")
    return dict(id=identifier,
                context=dict(kind=kind, stage=stage, actor=actor,
                             index=index, profile_id=profile_id, arm=arm),
                request=req, request_text=reserve["wire"],
                request_sha256=t.sha(reserve["wire"].encode()),
                input_token_bound=reserve["input_token_bound"],
                reserved_usd=reserve["reserved_usd"])


def gate_cases():
    inventory = profiles()
    a, b = inventory["credit-conflict-a"], inventory["credit-conflict-b"]
    def sample_events(item):
        focal = item["focal"]
        early = dict(type="early_consents",
                     consents={f"r{i}": True for i in game.ACTORS if i != focal})
        all_signed = dict(type="consent", consents=[True] * 7)
        return early, all_signed

    early_a, full_a = sample_events(a)
    early_b, full_b = sample_events(b)
    contexts = (
        (a, "binding_requested_record", "consent", 0, []),
        (a, "binding_executed_record", "vote", a["focal"],
         [early_a, full_a]),
        (b, "promise_requested_record", "consent", b["focal"], [early_b]),
        (b, "promise_executed_record", "vote", b["focal"],
         [early_b, full_b]),
    )
    rows = []
    for index, (item, arm, stage, actor, events) in enumerate(contexts):
        rows.append(make_case(f"election-gate-{index:02d}", actor, stage,
                              game.messages(item["profile"], arm, actor, stage,
                                            events),
                              GATE_SEED_BASE + index, index, "gate", item["id"], arm))
    require(len(rows) == GATE_CALLS, "four action gate cases")
    return rows


def episode_case(assignment, actor, stage, messages, index):
    require(0 <= index < 14, "episode decision index")
    return make_case(assignment["id"] + f"-{index:02d}", actor, stage,
                     messages, assignment["seed_base"] + index, index,
                     "episode", assignment["profile_id"], assignment["arm"])


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
    reserves = [reservation(case["request"]) for case in gate_cases()]
    mapping = profiles()
    for assignment in assignments():
        profile = mapping[assignment["profile_id"]]["profile"]

        def scripted(actor, stage, messages, index):
            reserves.append(reservation(request(
                messages, assignment["seed_base"] + index)))
            if stage == "consent":
                return json.dumps(dict(consent=True, message="x" * 1500))
            return '{"vote":true,"reason":"nonbinding extra field"}'

        result = game.episode(profile, assignment["arm"], scripted)
        require(result["calls"] == 14, "scripted episode length")
    total = sum(Decimal(row["reserved_usd"]) for row in reserves)
    require(len(reserves) == MAX_CALLS and total <= CAP,
            "full-path reservation exceeds stage cap")
    return dict(intended_calls=MAX_CALLS,
                full_output_scripted_reservations_usd=str(total),
                max_input_bound=max(row["input_token_bound"] for row in reserves),
                cap_usd=str(CAP))


def seed_audit(root=ROOT):
    planned = {GATE_SEED_BASE + index for index in range(GATE_CALLS)}
    planned |= {row["seed_base"] + index for row in assignments()
                for index in range(14)}
    require(len(planned) == GATE_CALLS + 4 * 14,
            "planned paired-seed inventory")
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


def prior_done():
    require((PRIOR_ROOT / "sessions/terminal.json").is_file() and
            (PRIOR_EXPORT / "bundle.json").is_file() and
            (PRIOR_EXPORT / "expected_report.json").is_file(),
            "prior chamber allocation not terminal and archived")
    helper = archive_source.archive_helpers()
    require(helper.verify_bundle(PRIOR_EXPORT, PRIOR_PROTOCOL)["experiment_family"] ==
            "pivot_b_ratification_disclosure_chamber_v1",
            "prior chamber archive changed")
    report = t.load(PRIOR_EXPORT / "expected_report.json")
    require(report["protocol"] == PRIOR_PROTOCOL and
            t.load(PRIOR_ROOT / "sessions/terminal.json")["protocol"] ==
            PRIOR_PROTOCOL, "prior chamber protocol")
    return dict(protocol=PRIOR_PROTOCOL,
                report_sha256=t.sha(t.canonical(report).encode()))


def prerequisite():
    helper = archive_source.archive_helpers()
    require(helper.verify_bundle(GATE_ARCHIVE, GATE_PROTOCOL)["experiment_family"] ==
            gate.STAGE, "inherited gate archive changed")
    require(gate.verify(GATE_ROOT, code_root=Path(GATE_ARCHIVE) / "code")[1] ==
            GATE_PROTOCOL, "inherited gate protocol changed")
    report = t.load(GATE_ARCHIVE / "expected_report.json")
    require(report["gate_passed"] and report["calls"] == 10,
            "inherited Qwen gate did not pass")
    for case in gate.cases():
        require(request(case["request"]["messages"],
                        case["request"]["seed"]) == case["request"],
                "native request configuration differs")
    return dict(protocol=GATE_PROTOCOL,
                report_sha256=t.sha(t.canonical(report).encode()),
                native_template=request([], 0))


def check_endpoint(metadata):
    row = gate.channel.check_metadata(metadata)
    require(row.get("uptime_last_30m") is not None and
            row["uptime_last_30m"] >= 99 and
            row.get("uptime_last_5m") is not None and
            row["uptime_last_5m"] >= 95,
            "Qwen endpoint uptime below pilot threshold")
    return row


def specification():
    return dict(name=STAGE, assignments=assignments(), gate_cases=gate_cases(),
                workers=WORKERS, max_calls=MAX_CALLS, cap_usd=str(CAP),
                budget_stop_usd=str(STOP), model_configuration=CONFIG,
                inherited_gate_protocol=GATE_PROTOCOL,
                preflight=scripted_preflight(),
                seed_pairing="The same requested seed is used for a given profile and decision index across all four arms; gate seeds are disjoint. This is an attempted common-random-numbers control, not proof of identical provider randomness or matched potential outcomes.",
                gate_rule="Four serial task-action cases must be native-reasoning, valid, and billing-certified. Stop at first failure; no episode begins unless all four pass. This is interface qualification, not strategic evidence.",
                failure_rule="Four episode workers. Invalid/unusable action ends only its episode; retain all assignments and prefixes. Stop new admissions after two transport/accounting failures or source/identity/credential/budget/instrument breach. No retry, repair, replacement, fallback or restart.",
                discovery_rule="All 16 selected cells retained. Six nonfocal representatives sign first; the focal last signer observes only their Boolean signature record. A selected-case attribution lead requires the identical three-signature early coalition in both binding visibility arms of each conflict profile, then focal consent/requested-vote divergence before enforcement; aligned and zero-office controls must both enact P in their binding arms, and the focal must make identical pre-enforcement choices in the two nonbinding record-label arms. No unique consent or requested ballot is presumed in the zero-office control because multiple actions can implement P with equal payoff. Missing or unmatched coalition cells are not scientific nulls. Forced ballots/elections alone never pass.",
                limitations="Four selected synthetic profiles, only two distinct conflict cases, one model/provider, sequential last-signer advantage, zero inter-agent messages, deterministic nine-citizen elections with hidden contract membership and fixed status-quo challenger. A positive screen is not population or human-voter evidence and requires untouched games and another model.")


def prepare(root, *, metadata=None, ledger_root=BUDGET):
    root = Path(root)
    require(not root.exists(), "fresh election pilot directory required")
    prior = prior_done()
    inherited = prerequisite()
    seeds = seed_audit()
    if metadata is None:
        with t.opener().open(gate.channel.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    check_endpoint(metadata)
    budget = Ledger(ledger_root).snapshot()
    require(budget["pending"] == 0 and
            Decimal(budget["accounted_usd"]) + CAP < STOP,
            "pre-stage conservative $8 stop")
    paths = closure(ROOT, [Path(__file__),
                           ROOT / "analysis/paper3_contracts_archive.py",
                           ROOT / "tests/test_paper3_electoral_accountability_pilot.py",
                           BUDGET / "authority.json"])
    snapshot = {str(path.relative_to(ROOT)): path.read_text() for path in paths}
    protocol = dict(**specification(), inherited_prerequisite=inherited,
                    prior_terminal_archive=prior, seed_audit=seeds,
                    pre_stage_budget=budget, endpoint_metadata=metadata,
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
                "frozen election source changed: " + relative)
    require(all(manifest["protocol"].get(key) == value
                for key, value in specification().items()),
            "election specification changed")
    require(manifest["protocol"]["inherited_prerequisite"]["protocol"] ==
            GATE_PROTOCOL and
            manifest["protocol"]["inherited_prerequisite"]["native_template"] ==
            request([], 0), "native request config changed")
    require(manifest["protocol"]["prior_terminal_archive"]["protocol"] ==
            PRIOR_PROTOCOL, "prior allocation identity")
    planned = sorted({GATE_SEED_BASE + index for index in range(GATE_CALLS)} |
                     {row["seed_base"] + index for row in assignments()
                      for index in range(14)})
    require(manifest["protocol"]["seed_audit"]["planned_unique"] == planned and
            not manifest["protocol"]["seed_audit"]["overlap"],
            "seed inventory changed")
    check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, ledger_root=BUDGET, secret=None, send=None, lookup=None,
            clock=time.time, sleep=time.sleep):
    root = Path(root)
    manifest, protocol = verify(root)
    require(prior_done() == manifest["protocol"]["prior_terminal_archive"],
            "prior terminal archive changed")
    require(prerequisite() == manifest["protocol"]["inherited_prerequisite"],
            "inherited native gate changed")
    require(0 <= clock() - manifest["protocol"]["metadata_observed_unix"] <= 3600,
            "stale endpoint metadata")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(all(not list((root / name).iterdir()) for name in
                    ("calls", "decisions", "episodes", "sessions")),
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
        gate_results = []
        gate_failed = False
        for case in manifest["protocol"]["gate_cases"]:
            if calls.stop.is_set() or gate_failed:
                gate_results.append(dict(id=case["id"], status="not_started"))
                continue
            result = calls.one(case)
            gate_results.append(result)
            if result["status"] != "recorded":
                gate_failed = True
                continue
            saved = t.load(root / "calls" / (case["id"] + ".json"))
            if not (saved["result"]["usable"] and
                    saved["result"]["valid_action"] and
                    saved["result"]["correct"] is True):
                gate_failed = True
        gate_passed = (not gate_failed and not calls.stop.is_set() and
                       len(gate_results) == GATE_CALLS)
        profile_map = profiles()

        def one(assignment):
            if not gate_passed or calls.stop.is_set():
                saved = dict(id=assignment["id"], status="not_started")
            else:
                profile = profile_map[assignment["profile_id"]]["profile"]

                def ask(actor, stage, messages, index):
                    case = episode_case(assignment, actor, stage, messages, index)
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
            print(json.dumps(dict(event="election_episode_terminal",
                                  id=assignment["id"], status=saved["status"],
                                  budget=ledger.snapshot())), flush=True)
            return dict(id=assignment["id"], status=saved["status"])

        if gate_passed:
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                summaries = list(pool.map(one, manifest["protocol"]["assignments"]))
        else:
            summaries = [one(assignment) for assignment in
                         manifest["protocol"]["assignments"]]
        terminal = dict(protocol=protocol, gate_results=gate_results,
                        gate_passed=gate_passed, episodes=summaries,
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
    require({path.stem for path in (root / "episodes").glob("*.json")} ==
            {row["id"] for row in scheduled}, "episode file inventory")
    require([row["id"] for row in terminal["gate_results"]] ==
            [row["id"] for row in manifest["protocol"]["gate_cases"]],
            "gate inventory")
    decision_paths = sorted((root / "decisions").glob("*.json"))
    decisions = [t.load(path) for path in decision_paths]
    require(all(row["case"]["id"] == path.stem
                for row, path in zip(decisions, decision_paths, strict=True)),
            "decision file identity")
    cases = manifest["protocol"]["gate_cases"] + [row["case"] for row in decisions]
    require(len(cases) <= MAX_CALLS and
            len({row["id"] for row in cases}) == len(cases),
            "decision inventory")
    statuses = terminal["gate_results"] + [row["result"] for row in decisions]
    calls, cost = service.audit_records(
        root, ledger_root, STAGE, protocol, cases,
        dict(results=statuses), score, CONFIG)
    require(cost <= CAP and
            Decimal(manifest["protocol"]["pre_stage_budget"]["accounted_usd"]) +
            cost < STOP, "stage/budget cap exceeded")
    by_id = {row["id"]: row for row in calls}
    gate_report = calls[:GATE_CALLS]
    first_failure = next((index for index, row in enumerate(gate_report)
                          if not (row["status"] == "recorded" and
                                  row["result"]["usable"] and
                                  row["result"]["valid_action"] and
                                  row["result"]["correct"] is True)), None)
    if first_failure is not None:
        require(all(row["status"] == "not_started"
                    for row in gate_report[first_failure + 1:]),
                "gate continued after failure")
    gate_passed = first_failure is None and not terminal["global_safety_stop"]
    # A later episode safety stop does not negate a gate that passed at launch.
    if first_failure is None:
        gate_passed = True
    require(terminal["gate_passed"] == gate_passed, "gate state changed")
    profile_map = profiles()
    records = {}
    for assignment, summary in zip(scheduled, terminal["episodes"], strict=True):
        saved = t.load(root / "episodes" / (assignment["id"] + ".json"))
        require(saved["id"] == summary["id"] and
                saved["status"] == summary["status"], "episode terminal changed")
        indexed = [row for row in decisions if row["case"]["id"].startswith(
            assignment["id"] + "-")]
        indexed.sort(key=lambda row: row["case"]["context"]["index"])
        if saved["status"] == "not_started":
            require(not indexed, "not-started episode has decisions")
        elif saved["status"] in ("completed", "failed"):
            position = 0

            def replay_ask(actor, stage, messages, index):
                nonlocal position
                require(index == position and position < len(indexed),
                        "missing decision")
                case = episode_case(assignment, actor, stage, messages, index)
                row = indexed[position]
                position += 1
                require(row["case"] == case, "election request changed")
                if row["result"]["status"] != "recorded":
                    raise EpisodeFailure("request_not_recorded")
                call = by_id[case["id"]]
                if not (call["result"]["usable"] and
                        call["result"]["valid_action"]):
                    raise EpisodeFailure("unusable_or_invalid_action")
                return t.load(root / "calls" / (case["id"] + ".json"))["final_content"]

            profile = profile_map[assignment["profile_id"]]["profile"]
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
        record = {key: value for key, value in saved.items() if key != "id"}
        if saved["status"] != "completed":
            record["prefix"] = [dict(id=row["case"]["id"],
                                     stage=row["case"]["context"]["stage"],
                                     actor=row["case"]["context"]["actor"],
                                     status=row["result"]["status"],
                                     result=by_id.get(row["case"]["id"], {}).get(
                                         "result")) for row in indexed]
        records[(assignment["profile_id"], assignment["arm"])] = record
    if not gate_passed:
        require(all(row["status"] == "not_started" for row in
                    terminal["episodes"]), "episodes started after failed gate")
    require(all(any(row["case"]["id"].startswith(assignment["id"] + "-")
                    for assignment in scheduled) for row in decisions),
            "unassigned episode decision")
    readout = analysis.readout(records)
    completed = sum(row["status"] == "completed" for row in terminal["episodes"])
    usable = sum(row["status"] == "recorded" and
                 row["result"]["usable"] and row["result"]["valid_action"]
                 for row in calls)
    feasible = (gate_passed and completed == 16 and usable == MAX_CALLS and
                len(calls) == MAX_CALLS and not terminal["global_safety_stop"])
    return dict(protocol=protocol, gate_assignments=gate_report,
                gate_passed=gate_passed, assignments=terminal["episodes"],
                calls=calls, completed_episodes=completed,
                usable_actions=usable, feasibility_passed=feasible,
                readout=readout, discovery_screen=analysis.discovery_screen(readout),
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
                        contents[prefix + "/" + str(path.relative_to(directory))] = (
                            path.read_bytes())
            contents["expected_report.json"] = (
                json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = (
        "# Electoral-accountability mechanism pilot\n\n"
        "Four selected profiles, 16 episodes and four prior action checks. "
        "Retain all failures, pre-enforcement choices, 63 citizen ballots per "
        "complete episode and finite missingness bounds. "
        "From fresh extraction run `python3 -I -S "
        "code/experiments/paper3_electoral_accountability_pilot.py . "
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
            "frozen election protocol changed")
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
