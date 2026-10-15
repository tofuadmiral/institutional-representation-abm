"""Independent request/controller/accounting replay; never calls a model."""
from decimal import Decimal
import fcntl
import json
from pathlib import Path
import sys

from experiments import paper3_retrospective_billing_discovery_v1 as runner
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_readout as readout
from paper3.pivot_b_budget import BUDGET_ID
from paper3.retrospective_execution import jsonable

t, require = runner.t, runner.require


def snapshot(rows):
    used = sum((Decimal(r["accounted_usd"] if r["status"] == "settled" else r["reserved_usd"])
                for r in rows), Decimal(0))
    return dict(budget_id=BUDGET_ID,
        cap_usd="10.00", accounted_usd=str(used), remaining_usd=str(Decimal("10.00") - used),
        entries=len(rows), pending=sum(r["status"] != "settled" for r in rows),
        uncertified=sum(r.get("certified") is False for r in rows))


def direct_outcome(game, arm, episode):
    citizens = [[0] * 9 for _ in range(7)]
    for index, term in enumerate(episode.terms):
        enacted = term.final.policy if sum(term.requested) >= 4 else 0
        values = tuple(tuple(row[enacted] for row in district) for district in game.utilities[index])
        require(term.executed == term.requested and term.enacted == enacted and
                term.citizen_utilities == values, "direct policy/citizen mismatch")
        for d in range(7):
            for c in range(9):
                citizens[d][c] += values[d][c]
        if index == 0:
            retained = tuple(arm.startswith("advisory") or
                (sum(v >= 0 for v in values[d]) >= 5 if arm.endswith("majority") else
                 sum(values[d]) >= 0) for d in range(7))
            require(term.tenure_retained == retained, "direct retention mismatch")
            occupants = tuple(f"{'incumbent' if retained[d] else 'successor'}-r{d}" for d in range(7))
            require(term.next_occupants == occupants and episode.terms[1].occupants == occupants,
                    "direct handover mismatch")
        else:
            require(term.tenure_retained is None, "terminal office incentive")
    require(episode.cumulative_citizen_utilities == tuple(map(tuple, citizens)), "cumulative citizens")
    require(episode.cumulative_district_utilities == tuple(map(sum, citizens)), "cumulative districts")
    require(episode.initial_incumbent_scores == tuple(sum(v) + game.office_value * retained[d]
            for d, v in enumerate(citizens)), "mandate/office score mismatch")
    expected_successors = tuple(None if retained[d] else
        sum(game.utilities[1][d][c][episode.terms[1].enacted] for c in range(9)) for d in range(7))
    require(episode.successor_scores == expected_successors, "successor score mismatch")


def audit(root, ledger_root):
    root, ledger_root = Path(root), Path(ledger_root)
    manifest, protocol = runner.verify(root)
    proof = manifest["protocol"]["qualification_proof"]
    require(runner.qualification_proof(root / "qualification.zip", proof["protocol"],
            proof["archive_sha256"]) == proof, "qualification replay/equality changed")
    runner.verify_prior_allowed(ledger_root, manifest["protocol"]["prior_ledger_entries"])
    paths = {p.name: p for p in (ledger_root / "entries").glob("*.json")}
    entries = {n: t.load(p) for n, p in paths.items()}
    baseline = manifest["protocol"]["prior_ledger_entries"]
    require(snapshot([entries[n] for n in baseline]) == manifest["protocol"]["pre_stage_budget"],
            "baseline budget mismatch")
    observations = {(p.seed, s, a): None for p in runner.requests.pairs()
                    for s in readout.STRATA for a in institution.ARMS}
    completed, batch_reports, all_reports, all_calls = set(), [], [], []
    message_executions = []
    expected_prior = set(baseline)
    for batch in (0, 1):
        local, scheduled = runner.batch_root(root, batch), runner.scheduled(batch)
        terminal_path = local / "sessions/terminal.json"
        if not terminal_path.exists():
            require(not list((local / "sessions").glob("*")) and
                    all(not list((local / n).glob("*")) for n in ("calls", "decisions", "episodes")),
                    "started/interrupted batch has no terminal; preserve without restart")
            require(not any(r["stage"] == runner.batch_stage(batch) for r in entries.values()),
                    "unstarted batch has reservations")
            rows = [dict(id=a["id"], status="not_started", decisions=0, terms=[None, None], outcome=None)
                    for a in scheduled]
            batch_reports.append(dict(index=batch, status="not_started", complete=False,
                                      global_safety_stop=False, accounted_usd="0", calls=0, assignments=rows))
            all_reports.extend(rows)
            continue
        require(batch == 0 or batch_reports[0]["complete"] is True and
                not batch_reports[0]["global_safety_stop"], "second batch after failed/incomplete first")
        start, terminal = t.load(local / "sessions/start.json"), t.load(terminal_path)
        require(start["protocol"] == terminal["protocol"] == protocol and
                start["batch"] == terminal["batch"] == batch, "batch protocol/identity")
        require(set(start["prior_ledger_entries"]) == expected_prior, "pre-batch entry inventory")
        for n, digest in start["prior_ledger_entries"].items():
            require(t.sha(paths[n].read_bytes()) == digest, "pre-batch entry changed")
        before = snapshot([entries[n] for n in expected_prior])
        require(before == start["pre_batch_budget"] and Decimal(before["accounted_usd"]) +
                runner.CAP <= runner.TOTAL_STOP, "pre-batch authority")
        runner.route.check_endpoint(start["endpoint_metadata"])
        require(0 <= start["started_unix"] - start["metadata_observed_unix"] <= 3600,
                "stale batch metadata")
        decisions = [t.load(p) for p in sorted((local / "decisions").glob("*.json"))]
        ids = {a["id"] for a in scheduled}
        require(len({r["case"]["id"] for r in decisions}) == len(decisions) and
                all(r["case"]["context"]["assignment_id"] in ids for r in decisions),
                "duplicate/unassigned decision")
        controller_stops = tuple(a["id"] for a in terminal["episodes"]
                                 if a["status"] == "instrument_error")
        component = runner.coordinator.audit(local, ledger_root, runner.batch_stage(batch),
                                             protocol, runner.score, controller_stops=controller_stops)
        call_reports, cost = component["call_reports"], Decimal(component["accounted_usd"])
        by_logical = {p.stem: t.load(p) for p in (local / "logicals").glob("*.json")}
        require(set(by_logical) == {d["case"]["id"] for d in decisions}, "logical/decision inventory")
        for d in decisions:
            logical = by_logical[d["case"]["id"]]
            require(t.canonical(d["case"]) == t.canonical(logical["case"]) and
                    t.canonical(d["result"]) == t.canonical(logical), "logical decision evidence changed")
        require(terminal["physical_calls"] == component["physical_calls"] and
                terminal["logical_actions"] == component["logical_actions"] and
                terminal["recoveries"] == component["recoveries"], "terminal transport inventory")
        require([s["id"] for s in terminal["episodes"]] == [a["id"] for a in scheduled],
                "all eight batch assignments retained")
        require({p.stem for p in (local / "episodes").glob("*.json")} == ids,
                "episode file inventory")
        rows = []
        for assignment, declared in zip(scheduled, terminal["episodes"], strict=True):
            saved = t.load(local / "episodes" / (assignment["id"] + ".json"))
            require(saved["id"] == declared["id"] and saved["status"] == declared["status"],
                    "episode terminal status")
            indexed = sorted((r for r in decisions if r["case"]["context"]["assignment_id"] ==
                              assignment["id"]), key=lambda r: r["case"]["context"]["index"])
            require([r["case"]["context"]["index"] for r in indexed] == list(range(len(indexed))),
                    "episode decision prefix")
            position, terms, observed = 0, [None, None], {}

            def on_term(term):
                terms[term.index] = jsonable(term)
                observed[term.index] = term

            def ask(actor, identity, term, stage, context, index):
                nonlocal position
                expected = runner.action_call(assignment, actor, identity, term, stage, context, index)
                if position == len(indexed) and saved["status"] == "instrument_error":
                    # Replay the observed prefix, not an invented post-fault action.
                    # This preserves a declared runtime interruption; it does not
                    # independently establish the cause of the controller fault.
                    raise runner.EpisodeFailure("saved_controller_interruption")
                require(position < len(indexed), "missing prepared decision")
                decision = indexed[position]
                require(t.canonical(decision["case"]) == t.canonical(expected), "reconstructed request mismatch")
                position += 1
                logical = by_logical[expected["id"]]
                if logical["status"] != "recorded":
                    raise runner.EpisodeFailure("request_not_recorded")
                selected = t.load(local / "calls" / (logical["selected_id"] + ".json"))
                raw = runner.interface.decision(selected["stream"])["arguments"]
                executed = dict(raw)
                requested_len = executed_len = None
                if stage != "vote":
                    text = raw["message"]
                    require(type(text) is str and all(
                        (ord(c) >= 32 and not 127 <= ord(c) <= 159) or c in "\t\n\r"
                        for c in text), "independent raw public text legality")
                    executed["message"] = text[:128]
                    requested_len, executed_len = len(text), len(executed["message"])
                expected_mapping = dict(version=runner.message_budget.VERSION, stage=stage,
                    requested_action=raw, executed_action=executed,
                    requested_characters=requested_len, executed_characters=executed_len,
                    clipped=requested_len is not None and requested_len > executed_len)
                require(selected["result"]["message_execution"] == expected_mapping and
                        logical["action"] == executed, "independent raw/executed mapping")
                message_executions.append(dict(id=expected["id"], selected_id=logical["selected_id"],
                    assignment_id=assignment["id"], arm=assignment["arm"], term=term,
                    stage=stage, index=index, mapping=expected_mapping))
                return logical["action"]

            if saved["status"] == "not_started":
                require(not indexed and saved["terms"] == terms and saved["outcome"] is None,
                        "unstarted assignment has evidence")
            else:
                try:
                    episode = institution.episode(assignment["game"], assignment["arm"], ask, on_term)
                    require(saved["status"] == "completed" and saved["outcome"] == jsonable(episode),
                            "completed episode mismatch")
                    direct_outcome(assignment["game"], assignment["arm"], episode)
                    completed.add((assignment["seed"], assignment["stratum"], assignment["arm"]))
                except runner.EpisodeFailure as exc:
                    if str(exc) == "saved_controller_interruption":
                        require(saved["status"] == "instrument_error" and
                                type(saved.get("error")) is str and bool(saved["error"]) and
                                saved["outcome"] is None, "controller interruption mismatch")
                    else:
                        require(saved["status"] == "failed" and saved["error"] == str(exc) and
                                saved["outcome"] is None, "failed episode mismatch")
                require(saved["terms"] == terms and position == len(indexed), "partial terms/prefix mismatch")
                if 0 in observed:
                    observations[(assignment["seed"], assignment["stratum"], assignment["arm"])] = observed[0]
            rows.append(dict(**declared, decisions=len(indexed), terms=saved["terms"], outcome=saved["outcome"],
                controller_failure_cause_verified=False if saved["status"] == "instrument_error" else None))
        serial_passed = rows[0]["status"] == "completed"
        require(terminal["serial_episode_passed"] == serial_passed, "serial technical verdict")
        if not serial_passed:
            require(all(r["status"] == "not_started" for r in rows[1:]), "worker launch after serial failure")
        stop_path = local / "sessions/safety_stop.json"
        failed = any(r["status"] in ("failed", "instrument_error") for r in rows)
        require(terminal["global_safety_stop"] == failed, "global safety verdict")
        if stop_path.exists():
            event = t.load(stop_path)
            require(event["protocol"] == protocol and event["batch"] == batch and
                    failed, "safety event provenance")
            if event["kind"] == "controller_instrument_error":
                require(any(r["id"] == event["call_id"] and r["status"] == "instrument_error"
                            for r in rows), "controller safety event provenance")
            else:
                require(event["call_id"] in by_logical, "logical safety event provenance")
                require(by_logical[event["call_id"]]["status"] != "recorded", "stop on recorded logical action")
            require(all(t.load(p)["admitted_unix"] <= event["detected_unix"]
                        for p in (local / "calls").glob("*.json")), "admission after safety event")
        else:
            require(not failed, "missing safety event")
        stage_names = {n for n, e in entries.items() if e["stage"] == runner.batch_stage(batch)}
        expected_prior |= stage_names
        require(snapshot([entries[n] for n in expected_prior]) == terminal["budget"], "terminal budget mismatch")
        require(cost <= runner.CAP and Decimal(terminal["budget"]["accounted_usd"]) <= runner.TOTAL_STOP,
                "stage/total authority exceeded")
        batch_reports.append(dict(index=batch, status="terminal", complete=all(r["status"] == "completed" for r in rows),
            serial_episode_passed=serial_passed, global_safety_stop=failed, calls=len(list((local / "calls").glob("*.json"))),
            accounted_usd=str(cost), logical_actions=component["logical_actions"],
            recoveries=component["recoveries"], assignments=rows))
        all_reports.extend(rows)
        all_calls.extend(call_reports)
    require(set(entries) == expected_prior, "unassigned ledger entries")
    scientific = readout.screen(runner.requests.pairs(), observations, completed_episodes=completed, qualified=True)
    return jsonable(dict(protocol=protocol, qualification_proof=proof, new_gate_calls=0,
        batches=batch_reports, assignments=all_reports, completed=len(completed),
        calls=sum(r["calls"] for r in batch_reports), call_reports=all_calls,
        accounted_usd=str(sum(Decimal(r["accounted_usd"]) for r in batch_reports)),
        cumulative_accounted_usd=snapshot(list(entries.values()))["accounted_usd"],
        billing_evidence=dict(version=runner.billing.VERSION,
            records=[dict(id=c["id"], **c["result"]["billing"])
                for c in all_calls if c.get("result") and "billing" in c["result"]],
            certified_physical_calls=sum(c.get("result", {}).get("billing", {}).get("receipt_certified", False)
                for c in all_calls if c.get("result")),
            uncertified_selected_actions=sum(runner.coordinator.valid(c["result"]) and
                not c["result"]["billing"]["receipt_certified"] for c in all_calls if c.get("result")),
            full_reservation_without_receipt=True),
        selected_case_screen=scientific, publication_evidence=False,
        message_execution=dict(version=runner.message_budget.VERSION,
            records=message_executions, selected_actions=len(message_executions),
            clipped_messages=sum(x["mapping"]["clipped"] for x in message_executions),
            by_arm_phase=[dict(arm=arm, phase=stage,
                actions=sum(x["arm"] == arm and x["stage"] == stage for x in message_executions),
                clipped=sum(x["arm"] == arm and x["stage"] == stage and x["mapping"]["clipped"]
                            for x in message_executions))
                for arm in institution.ARMS for stage in ("draft", "response", "final", "vote")]),
        caveat=runner.specification()["limitation"]))


def export(root, ledger_root, target, destination, secret=None):
    root, ledger_root, target = [Path(p).resolve() for p in (root, ledger_root, target)]
    require(not target.exists() and not Path(destination).exists(), "archive destination exists")
    helper = runner.gate.archive_helper()
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with runner.Ledger(ledger_root).locked():
            report = audit(root, ledger_root)
            contents = {"code/" + n: s.encode() for n, s in t.load(root / "sources.json").items()}
            for prefix, folder in (("run", root), ("ledger", ledger_root)):
                for p in folder.rglob("*"):
                    require(not p.is_symlink(), "archive symlink")
                    if p.is_file() and p.suffix == ".json":
                        contents[prefix + "/" + str(p.relative_to(folder))] = p.read_bytes()
            contents["run/qualification.zip"] = (root / "qualification.zip").read_bytes()
            contents["expected_report.json"] = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = ("# Staged accountability discovery\n\nAll sixteen assignments remain. "
        "An incomplete run is inconclusive; a selected-case lead is not publication evidence. "
        "Fresh replay: `python3 -I -S code/experiments/paper3_retrospective_billing_discovery_v1.py . --replay "
        "--expected-protocol " + report["protocol"] + "`.\n").encode()
    for n, value in contents.items():
        helper.safe(target, n)
        helper.credentials(value, secret)
    metadata = dict(format=helper.FORMAT, experiment_family=runner.NAME, protocol=report["protocol"],
                    files={n: t.sha(v) for n, v in sorted(contents.items())})
    target.mkdir(parents=True, exist_ok=False)
    for n, value in contents.items():
        path = helper.safe(target, n)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(value)
    with (target / "bundle.json").open("x") as stream:
        json.dump(metadata, stream, sort_keys=True, indent=2)
    return dict(protocol=report["protocol"], files=len(contents), sha256=helper.archive(target, destination))


def replay(root, expected_protocol):
    root = Path(root).resolve()
    helper = runner.gate.archive_helper()
    metadata = helper.verify_bundle(root, expected_protocol)
    require(metadata["experiment_family"] == runner.NAME and runner.ROOT == root / "code",
            "isolated staged code required")
    sys.addaudithook(helper.offline_guard)
    report = audit(root / "run", root / "ledger")
    require(t.canonical(report) == t.canonical(t.load(root / "expected_report.json")), "replay report mismatch")
    return dict(**report, portable_replay=dict(exact_report_match=True, protocol=expected_protocol))
