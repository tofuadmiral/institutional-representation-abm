"""Offline independent trajectory/accounting reconstruction for candidate recovery."""
from decimal import Decimal
import fcntl
import json
from pathlib import Path
import sys

from experiments import paper3_retrospective_overload_discovery as runner
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_readout as readout
from paper3.retrospective_execution import jsonable

t, require = runner.t, runner.require
snapshot = runner.closed.auditor().snapshot
direct_outcome = runner.closed.auditor().direct_outcome


def audit(root, ledger_root):
    root, ledger_root = Path(root), Path(ledger_root)
    manifest, protocol = runner.verify(root)
    proof = manifest["protocol"]["qualification_proof"]
    require(runner.qualification_proof(root / "qualification.zip", proof["protocol"],
            proof["archive_sha256"]) == proof, "qualification replay changed")
    runner.verify_prior_allowed(ledger_root, manifest["protocol"]["prior_ledger_entries"])
    paths = {p.name: p for p in (ledger_root / "entries").glob("*.json")}
    entries = {name: t.load(path) for name, path in paths.items()}
    baseline = manifest["protocol"]["prior_ledger_entries"]
    require(snapshot([entries[n] for n in baseline]) == manifest["protocol"]["pre_stage_budget"],
            "baseline accounting changed")
    observations = {(p.seed, s, a): None for p in runner.requests.pairs()
                    for s in readout.STRATA for a in institution.ARMS}
    completed, batches, assignments, all_calls = set(), [], [], []
    expected_prior = set(baseline)
    for batch in (0, 1):
        local, scheduled = runner.batch_root(root, batch), runner.scheduled(batch)
        terminal_path = local / "sessions/terminal.json"
        if not terminal_path.exists():
            require(all(not list((local / n).glob("*")) for n in runner.DIRECTORIES),
                    "interrupted batch without terminal; preserve, no restart")
            require(not any(e["stage"] == runner.batch_stage(batch) for e in entries.values()),
                    "unstarted stage has reservations")
            rows = [dict(id=a["id"], status="not_started", decisions=0, terms=[None, None], outcome=None)
                    for a in scheduled]
            batches.append(dict(index=batch, status="not_started", complete=False, global_safety_stop=False,
                                accounted_usd="0", calls=0, recoveries=0, assignments=rows))
            assignments.extend(rows)
            continue
        require(batch == 0 or batches[0]["complete"] and not batches[0]["global_safety_stop"],
                "second batch after incomplete/failed first")
        start, terminal = t.load(local / "sessions/start.json"), t.load(terminal_path)
        require(start["protocol"] == terminal["protocol"] == protocol and
                start["batch"] == terminal["batch"] == batch, "batch identity/protocol")
        require(set(start["prior_ledger_entries"]) == expected_prior, "pre-batch inventory")
        for name, digest in start["prior_ledger_entries"].items():
            require(t.sha(paths[name].read_bytes()) == digest, "pre-batch entry changed")
        before = snapshot([entries[n] for n in expected_prior])
        require(before == start["pre_batch_budget"] and Decimal(before["accounted_usd"]) +
                runner.CAP <= runner.route.STOP, "pre-batch authority")
        runner.route.check_endpoint(start["endpoint_metadata"])
        require(0 <= start["started_unix"] - start["metadata_observed_unix"] <= 3600, "stale metadata")
        decisions = [t.load(p) for p in sorted((local / "logicals").glob("*.json"))]
        ids = {a["id"] for a in scheduled}
        require(len({r["case"]["id"] for r in decisions}) == len(decisions) and
                all(r["case"]["context"]["assignment_id"] in ids for r in decisions), "unassigned/duplicate logical")
        require([s["id"] for s in terminal["episodes"]] == [a["id"] for a in scheduled] and
                {p.stem for p in (local / "episodes").glob("*.json")} == ids, "all eight assignments retained")
        controller_stops = tuple(a["id"] for a in terminal["episodes"] if a["status"] == "instrument_error")
        transport = runner.transport.audit(local, ledger_root, runner.batch_stage(batch), protocol,
                                           runner.score, controller_stops=controller_stops)
        by_decision = {d["case"]["id"]: d for d in decisions}
        rows = []
        for assignment, declared in zip(scheduled, terminal["episodes"], strict=True):
            saved = t.load(local / "episodes" / (assignment["id"] + ".json"))
            require(saved["id"] == declared["id"] and saved["status"] == declared["status"], "episode terminal status")
            indexed = sorted((d for d in decisions if d["case"]["context"]["assignment_id"] == assignment["id"]),
                             key=lambda d: d["case"]["context"]["index"])
            require([d["case"]["context"]["index"] for d in indexed] == list(range(len(indexed))), "decision prefix")
            position, terms, observed = 0, [None, None], {}

            def on_term(term):
                terms[term.index] = jsonable(term)
                observed[term.index] = term

            def ask(actor, identity, term, stage, context, index):
                nonlocal position
                expected = runner.action_call(assignment, actor, identity, term, stage, context, index)
                if position == len(indexed) and saved["status"] == "instrument_error":
                    raise runner.EpisodeFailure("saved_controller_interruption")
                require(position < len(indexed), "missing logical decision")
                decision = indexed[position]
                require(t.canonical(decision["case"]) == t.canonical(expected), "reconstructed request mismatch")
                require(decision == by_decision[expected["id"]], "logical identity mismatch")
                position += 1
                if decision["status"] != "recorded":
                    raise runner.EpisodeFailure("logical_action_failed")
                return decision["action"]

            if saved["status"] == "not_started":
                require(not indexed and saved["terms"] == terms and saved["outcome"] is None,
                        "unstarted episode has evidence")
            else:
                try:
                    episode = institution.episode(assignment["game"], assignment["arm"], ask, on_term)
                    require(saved["status"] == "completed" and saved["outcome"] == jsonable(episode), "completed outcome mismatch")
                    direct_outcome(assignment["game"], assignment["arm"], episode)
                    completed.add((assignment["seed"], assignment["stratum"], assignment["arm"]))
                except runner.EpisodeFailure as exc:
                    if str(exc) == "saved_controller_interruption":
                        require(saved["status"] == "instrument_error" and isinstance(saved.get("error"), str) and
                                bool(saved["error"]) and saved["outcome"] is None, "controller interruption mismatch")
                    else:
                        require(saved["status"] == "failed" and saved["error"] == str(exc) and saved["outcome"] is None,
                                "failed trajectory mismatch")
                require(saved["terms"] == terms and position == len(indexed), "observed prefix/partial terms mismatch")
                if 0 in observed:
                    observations[(assignment["seed"], assignment["stratum"], assignment["arm"])] = observed[0]
            rows.append(dict(**declared, decisions=len(indexed), terms=saved["terms"], outcome=saved["outcome"],
                controller_failure_cause_verified=False if saved["status"] == "instrument_error" else None))
        serial_passed = rows[0]["status"] == "completed"
        require(terminal["serial_episode_passed"] == serial_passed, "serial gate changed")
        if not serial_passed:
            require(all(r["status"] == "not_started" for r in rows[1:]), "workers after serial failure")
        failed = any(r["status"] in ("failed", "instrument_error") for r in rows)
        require(terminal["global_safety_stop"] == failed == transport["global_safety_stop"], "global stop mismatch")
        require(terminal["recovery_count"] == transport["recoveries"], "recovery count changed")
        expected_prior |= {name for name, e in entries.items() if e["stage"] == runner.batch_stage(batch)}
        require(snapshot([entries[n] for n in expected_prior]) == terminal["budget"], "terminal budget mismatch")
        require(Decimal(transport["accounted_usd"]) <= runner.CAP and
                Decimal(terminal["budget"]["accounted_usd"]) <= runner.route.STOP, "budget ceiling")
        batches.append(dict(index=batch, status="terminal", complete=all(r["status"] == "completed" for r in rows),
            serial_episode_passed=serial_passed, global_safety_stop=failed, calls=transport["physical_calls"],
            recoveries=transport["recoveries"], logical_actions=transport["logical_actions"],
            accounted_usd=transport["accounted_usd"], assignments=rows))
        assignments.extend(rows)
        all_calls.extend(transport["call_reports"])
    require(set(entries) == expected_prior, "unassigned spending")
    scientific = readout.screen(runner.requests.pairs(), observations, completed_episodes=completed, qualified=True)
    return jsonable(dict(protocol=protocol, integration_only=manifest["protocol"]["integration_only"],
        paid_launch_authorized=manifest["protocol"]["paid_launch_authorized"],
        qualification_proof=proof, new_gate_calls=0, batches=batches, assignments=assignments,
        completed=len(completed), calls=sum(b["calls"] for b in batches), call_reports=all_calls,
        recoveries=sum(b["recoveries"] for b in batches),
        accounted_usd=str(sum(Decimal(b["accounted_usd"]) for b in batches)),
        cumulative_accounted_usd=snapshot(list(entries.values()))["accounted_usd"],
        selected_case_screen=scientific, publication_evidence=False, caveat=runner.specification()["limitation"]))


def export(root, ledger_root, target, destination, secret=None):
    root, ledger_root, target = [Path(p).resolve() for p in (root, ledger_root, target)]
    require(not target.exists() and not Path(destination).exists(), "archive destination exists")
    helper = runner.closed.gate.archive_helper()
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with runner.Ledger(ledger_root).locked():
            report = audit(root, ledger_root)
            contents = {"code/" + n: s.encode() for n, s in t.load(root / "sources.json").items()}
            for prefix, folder in (("run", root), ("ledger", ledger_root)):
                for path in folder.rglob("*"):
                    require(not path.is_symlink(), "archive symlink")
                    if path.is_file() and path.suffix == ".json":
                        contents[prefix + "/" + str(path.relative_to(folder))] = path.read_bytes()
            contents["run/qualification.zip"] = (root / "qualification.zip").read_bytes()
            contents["expected_report.json"] = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    description = ("Fabricated transport tests are not agent results. " if report["integration_only"] else
                   "Selected-case model pilot, not population or publication evidence. ")
    contents["README.md"] = ("# Accountability discovery\n\n" + description +
        "Retains all16 assignments/physical attempts. An incomplete run is inconclusive. Replay: "
        "`python3 -I -S code/experiments/paper3_retrospective_overload_discovery.py . --replay "
        "--expected-protocol " + report["protocol"] + "`.\n").encode()
    for name, value in contents.items():
        helper.safe(target, name)
        helper.credentials(value, secret)
    metadata = dict(format=helper.FORMAT, experiment_family=runner.NAME, protocol=report["protocol"],
                    files={n: t.sha(v) for n, v in sorted(contents.items())})
    target.mkdir(parents=True, exist_ok=False)
    for name, value in contents.items():
        path = helper.safe(target, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(value)
    with (target / "bundle.json").open("x") as stream:
        json.dump(metadata, stream, sort_keys=True, indent=2)
    return dict(protocol=report["protocol"], files=len(contents), sha256=helper.archive(target, destination))


def replay(root, expected_protocol):
    root = Path(root).resolve()
    helper = runner.closed.gate.archive_helper()
    metadata = helper.verify_bundle(root, expected_protocol)
    require(metadata["experiment_family"] == runner.NAME and runner.ROOT == root / "code", "isolated code required")
    sys.addaudithook(helper.offline_guard)
    report = audit(root / "run", root / "ledger")
    require(t.canonical(report) == t.canonical(t.load(root / "expected_report.json")), "replay report mismatch")
    return dict(**report, portable_replay=dict(exact_report_match=True, protocol=expected_protocol))
