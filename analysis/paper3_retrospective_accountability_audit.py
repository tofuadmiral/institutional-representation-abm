"""Independent saved-call replay and portable packaging; never runs a model."""
from decimal import Decimal
import fcntl
import json
from pathlib import Path
import sys

from experiments import paper3_retrospective_accountability as runner
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_readout as readout
from paper3 import retrospective_requests as requests
from paper3.retrospective_execution import jsonable, verify_prior

t = runner.t
require = t.require
archive = runner.offline_module("analysis/paper3_contracts_archive.py")


def _independent_outcome(game, arm, episode):
    """Recompute enacted utilities/tenure directly, not from stored metrics."""
    totals = [[0] * 9 for _ in range(7)]
    for index, term in enumerate(episode.terms):
        enacted = term.final.policy if sum(term.requested) >= 4 else 0
        require(term.executed == term.requested and term.enacted == enacted, "unforced ballot outcome")
        citizens = tuple(tuple(row[enacted] for row in district) for district in game.utilities[index])
        require(term.citizen_utilities == citizens, "direct citizen utility mismatch")
        for actor in range(7):
            for citizen in range(9):
                totals[actor][citizen] += citizens[actor][citizen]
        if index == 0:
            retained = tuple(arm.startswith("advisory") or
                (sum(value >= 0 for value in values) >= 5 if arm.endswith("majority") else
                 sum(values) >= 0) for values in citizens)
            require(term.tenure_retained == retained, "direct tenure mismatch")
        else:
            require(term.tenure_retained is None, "terminal tenure incentive")
    require(episode.cumulative_citizen_utilities == tuple(map(tuple, totals)), "cumulative citizens")
    require(episode.cumulative_district_utilities == tuple(map(sum, totals)), "cumulative districts")
    require(episode.initial_incumbent_scores == tuple(sum(values) + game.office_value * retained[actor]
            for actor, values in enumerate(totals)), "office score erased principal welfare")


def audit(root, ledger_root):
    root, ledger_root = Path(root), Path(ledger_root)
    manifest, protocol = runner.verify(root)
    terminal = t.load(root / "sessions/terminal.json")
    require(t.load(root / "sessions/start.json")["protocol"] == terminal["protocol"] == protocol,
            "terminal protocol")
    verify_prior(ledger_root, manifest["protocol"]["prior_ledger_entries"], runner.STAGE)
    decisions = [t.load(path) for path in sorted((root / "decisions").glob("*.json"))]
    by_decision = {row["case"]["id"]: row for row in decisions}
    require(len(by_decision) == len(decisions), "duplicate decisions")
    gate = runner.gate_calls()
    gate_ids = {call["id"] for call in gate}
    action_records = [row for row in decisions if row["case"]["id"] not in gate_ids]
    cases = [*gate, *(row["case"] for row in action_records)]
    statuses = [by_decision[call["id"]]["result"] if call["id"] in by_decision else
                dict(id=call["id"], status="not_started") for call in cases]
    reports, cost = runner.service.audit_records(root, ledger_root, runner.STAGE, protocol, cases,
                                                 dict(results=statuses), runner.score, runner.CONFIG)
    by_report = {row["id"]: row for row in reports}

    def usable(call):
        report = by_report[call["id"]]
        result = report["result"]
        return (report["status"] == "recorded" and result and result["usable"] and
                result["valid_action"] and result["exact"])

    qualification = []
    failed = False
    for call in gate:
        report = by_report[call["id"]]
        status = "passed" if usable(call) else "not_started" if report["status"] == "not_started" else "failed"
        require(not failed or status == "not_started", "qualification continued after failure")
        if status != "passed":
            failed = True
        qualification.append(dict(id=call["id"], status=status))
    qualified = all(row["status"] == "passed" for row in qualification)
    require(terminal["qualified"] == qualified and terminal["qualification"] == qualification,
            "qualification verdict changed")
    require(t.load(root / "sessions/qualification.json") ==
            dict(protocol=protocol, results=qualification, passed=qualified), "qualification checkpoint")
    scheduled = requests.assignments()
    require([row["id"] for row in terminal["episodes"]] == [row["id"] for row in scheduled],
            "episode inventory")
    observations = {(pair.seed, stratum, arm): None for pair in requests.pairs()
                    for stratum in readout.STRATA for arm in institution.ARMS}
    completed = set()
    episode_reports = []
    matched = set(gate_ids)
    for assignment, status in zip(scheduled, terminal["episodes"], strict=True):
        saved = t.load(root / "episodes" / (assignment["id"] + ".json"))
        require(saved["id"] == status["id"] and saved["status"] == status["status"], "episode status")
        indexed = [row for row in action_records if row["case"]["context"].get("assignment_id") == assignment["id"]]
        indexed.sort(key=lambda row: row["case"]["context"]["index"])
        require([row["case"]["context"]["index"] for row in indexed] == list(range(len(indexed))),
                "episode prefix positions")
        matched.update(row["case"]["id"] for row in indexed)
        position = 0
        replayed_terms = [None, None]
        observed_terms = {}

        def on_term(term):
            observed_terms[term.index] = term
            replayed_terms[term.index] = jsonable(term)

        def ask(actor, identity, term, stage, context, index):
            nonlocal position
            require(position < len(indexed), "missing prepared decision in replay")
            row = indexed[position]
            expected = runner.action_call(assignment, actor, identity, term, stage, context, index)
            require(t.canonical(row["case"]) == t.canonical(expected), "reconstructed request changed")
            position += 1
            if by_report[expected["id"]]["status"] != "recorded":
                raise runner.EpisodeFailure("request_not_recorded")
            if not usable(expected):
                raise runner.EpisodeFailure("unusable_invalid_inexact_or_uncertified")
            return by_report[expected["id"]]["result"]["action"]

        if saved["status"] == "not_started":
            require(not indexed and saved["terms"] == [None, None] and saved["outcome"] is None,
                    "unstarted episode has evidence")
        else:
            require(qualified, "discovery before qualification")
            try:
                episode = institution.episode(assignment["game"], assignment["arm"], ask, on_term)
                require(saved["status"] == "completed" and saved["outcome"] == jsonable(episode),
                        "completed episode changed")
                _independent_outcome(assignment["game"], assignment["arm"], episode)
                completed.add((assignment["seed"], assignment["stratum"], assignment["arm"]))
            except runner.EpisodeFailure as exc:
                require(saved["status"] == "failed" and saved["error"] == str(exc) and
                        saved["outcome"] is None, "failed episode changed")
            require(saved["terms"] == replayed_terms and position == len(indexed), "partial terms/prefix changed")
            if 0 in observed_terms:
                observations[(assignment["seed"], assignment["stratum"], assignment["arm"])] = observed_terms[0]
        episode_reports.append(dict(**status, decisions=len(indexed), terms=saved["terms"], outcome=saved["outcome"]))
    require(matched == {call["id"] for call in cases}, "unassigned decision")
    require({path.stem for path in (root / "episodes").glob("*.json")} == {row["id"] for row in scheduled},
            "extra/missing episode files")
    serial_passed = episode_reports[0]["status"] == "completed"
    require(terminal["serial_episode_passed"] == serial_passed, "serial gate changed")
    if not serial_passed:
        require(all(row["status"] == "not_started" for row in episode_reports[1:]),
                "later episodes started after failed serial gate")
    entries = runner.Ledger(ledger_root)._entries()
    used = runner.Ledger(ledger_root)._total(entries)
    require(Decimal(terminal["budget"]["accounted_usd"]) == used, "terminal accounting changed")
    selected = readout.screen(requests.pairs(), observations, completed_episodes=completed, qualified=qualified)
    return jsonable(dict(protocol=protocol, qualification=qualification, qualified=qualified,
        assignments=episode_reports, calls=len(list((root / "calls").glob("*.json"))),
        completed=len(completed), serial_episode_passed=serial_passed,
        global_safety_stop=terminal["global_safety_stop"], call_reports=reports,
        accounted_usd=str(cost), cumulative_accounted_usd=str(used),
        budget_within_authority=(cost <= requests.CAP and used <= requests.STOP),
        selected_case_screen=selected,
        caveat="Two selected synthetic blocks and one model route. Interface qualification is not scientific success; a lead only proposes independent validation."))


def export(root, ledger_root, target, destination, secret=None):
    root, ledger_root, target = (Path(path).resolve() for path in (root, ledger_root, target))
    require(not target.exists() and not Path(destination).exists(), "archive destination exists")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with runner.Ledger(ledger_root).locked():
            report = audit(root, ledger_root)
            _, protocol = runner.verify(root)
            contents = {"code/" + relative: value.encode() for relative, value in
                        t.load(root / "sources.json").items()}
            for prefix, directory in (("run", root), ("ledger", ledger_root)):
                for path in directory.rglob("*"):
                    require(not path.is_symlink(), "symlink in archive source")
                    if path.is_file() and path.suffix == ".json":
                        contents[prefix + "/" + str(path.relative_to(directory))] = path.read_bytes()
            contents["expected_report.json"] = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = ("# Retrospective-accountability discovery\n\n"
        "Qualification and selected-case discovery, not publication evidence. Retain failures and all citizen outcomes. "
        "From a fresh extraction run `python3 -I -S code/experiments/paper3_retrospective_accountability.py "
        ". --replay --expected-protocol " + protocol + "`.\n").encode()
    for relative, value in contents.items():
        archive.safe(target, relative)
        archive.credentials(value, secret)
    metadata = dict(format=archive.FORMAT, experiment_family=runner.STAGE, protocol=protocol,
                    files={key: t.sha(value) for key, value in sorted(contents.items())})
    target.mkdir(parents=True, exist_ok=False)
    for relative, value in contents.items():
        path = archive.safe(target, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(value)
    with (target / "bundle.json").open("x") as stream:
        json.dump(metadata, stream, sort_keys=True, indent=2)
    return dict(protocol=protocol, files=len(contents), sha256=archive.archive(target, destination))


def replay(root, expected_protocol):
    root = Path(root).resolve()
    metadata = archive.verify_bundle(root, expected_protocol)
    require(metadata["experiment_family"] == runner.STAGE and runner.ROOT == root / "code",
            "isolated bundled code required")
    sys.addaudithook(archive.offline_guard)
    report = audit(root / "run", root / "ledger")
    require(t.canonical(report) == t.canonical(t.load(root / "expected_report.json")), "replay report changed")
    return dict(**report, portable_replay=dict(exact_report_match=True, protocol=expected_protocol))
