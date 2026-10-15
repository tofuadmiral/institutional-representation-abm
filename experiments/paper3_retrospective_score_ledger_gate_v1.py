"""Fresh 24-task conditional-score-ledger qualification; $0.35 cap, no pilot.

Native reasoning remains enabled. Safe content failures stop the diagnostic
case, not other independently assigned cases. Instrument failures stop globally.
One answerless rate-limit reissue TOTAL after 300 seconds; never bad answers.
No repair, fallback, inherited pass or institutional launch.
"""
# ruff: noqa: E402
from __future__ import annotations
import argparse
from decimal import Decimal
import fcntl
from functools import cache
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import paper3_transport_diagnostic as t
from paper3 import retrospective_billing_calls as service
from paper3 import retrospective_score_ledger_qualification as qualification
from paper3 import retrospective_failure_scope as failure_scope
from paper3 import retrospective_qualification_retry as recovery
from paper3 import retrospective_contract_route_v2 as route
from paper3.pivot_b_budget import Ledger, atomic
from paper3.retrospective_execution import jsonable, verify_prior
from paper3.retrospective_serial_execution import StopLedger, prior_inventory
from paper3.source_closure import closure

STAGE = "pivot_b_retrospective_score_ledger_gate_v1"
CAP = Decimal(".35")
BUDGET = ROOT / "results/paper3/pivot_b_budget"
CONFIG = dict(models=[route.MODEL, route.MODEL_ALIAS], provider=route.PROVIDER,
              output_bound=route.OUTPUT_BOUND)
require = t.require


def source_roots():
    return [Path(__file__), ROOT / "analysis/paper3_contracts_archive.py", BUDGET / "authority.json",
            BUDGET / "authority_extension_2026_10_03.json",
            ROOT / "tests/test_paper3_retrospective_score_ledger_gate_v1.py",
            ROOT / "tests/test_paper3_retrospective_serialization_contract.py",
            ROOT / "tests/test_paper3_retrospective_score_ledger_qualification.py",
            ROOT / "tests/test_paper3_retrospective_score_ledger.py",
            ROOT / "requirements.txt"]


def readiness_check():
    """Production preparation cannot bypass the independently tested source pins."""
    path = ROOT / "results/paper3" / (STAGE + "_preflight.json")
    record = t.load(path)
    actual = {str(p.relative_to(ROOT)): t.sha(p.read_bytes())
              for p in closure(ROOT, source_roots())}
    require(record["sources"] == actual and record["specification_sha256"] ==
            t.sha(t.canonical(specification()).encode()), "readiness source/specification changed")
    require(record["qualification_approved"] is True and record["actual_model_calls"] == 0
            and record["offline_tests"]["passed"] is True, "readiness authority/test evidence")
    return path


@cache
def cases():
    return tuple(dict(**row, **(bound := route.reservation(row["request"])),
                      request_sha256=t.sha(bound["request_text"].encode()))
                 for row in qualification.requests())


def score(row, case):
    result = dict(usable=False, valid_action=False, exact=False,
                  native_reasoning=None, action=None, failure="instrument_or_unfinished")
    if row.get("instrument_error") or "assessment" not in row:
        return result
    assessed = service.assess(row, CONFIG)
    native = service.native_evidence(assessed["stream"])
    usable = (assessed["passed"] and assessed["stream"]["finish_reasons"] in (["tool_calls"], ["stop"])
              and native["present"] and native["reported_count_consistent"] and row["request"]["reasoning"] == dict(enabled=True, exclude=False))
    result.update(usable=usable, native_reasoning=native)
    if usable:
        context = next(item for item in qualification.cases() if item["id"] == case["context"]["case_id"])
        result.update(qualification.score(context, row["stream"]))
        result["usable"] = result["stream_integrity"]
    else:
        result["failure"] = "transport_reasoning_or_action_completion"
    return result


def seed_audit(root=ROOT):
    planned = {qualification.FRAME_SEED, *(qualification.SEED_BASE + i for i in range(24))}
    observed, inventory = set(), []

    def walk(value, key=""):
        if type(value) is dict:
            for name, child in value.items():
                walk(child, name)
        elif type(value) is list:
            for child in value:
                walk(child, key)
        elif type(value) is int and "seed" in key.lower():
            observed.add(value)

    for base, dirs, files in os.walk(Path(root) / "results/paper3"):
        dirs[:] = [name for name in dirs if not any(fragment in name for fragment in
                   ("portable", "bundle", "export", "replay", "__pycache__", "code"))]
        for name in files:
            path = Path(base) / name
            if name == "manifest.json" or (path.parent.name == "calls" and name.endswith(".json")):
                value = t.load(path)
                walk(value.get("request", value) if path.parent.name == "calls" else value)
                inventory.append((str(path.relative_to(root)), t.sha(path.read_bytes())))
    require(not planned & observed, "historical frame/request seed collision")
    return dict(planned=sorted(planned), overlap=[], historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()))


@cache
def specification():
    reserve = recovery.bound(cases())
    require(len(cases()) == 24 and reserve <= CAP, "qualification call/cap bound")
    return jsonable(dict(name=STAGE, max_calls=24, max_physical_calls=25,
        max_reissues=1, cooldown_seconds=300, workers=1, cap_usd=str(CAP),
        cumulative_stop_usd=str(route.STOP), frame_seed=qualification.FRAME_SEED,
        newly_approved_total_usd="12", enforced_ledger_stop_usd="10",
        seed_base=qualification.SEED_BASE, configuration=CONFIG, cases=cases(),
        approval=dict(source="direct human user message", response="approved",
            date="2026-10-04", thread_id="01a09ba8-a109-7b62-a8a0-61519cfdea84",
            scope="Approved fresh SCORE-LEDGER qualification: up to24 tasks and one identical-wire/seed retry TOTAL only for confirmed answerless shared-pool429 after300 seconds;0.35 stage cap. Human raised total allowance from10 to12; this stage intentionally retains stricter original10 ledger stop and freezes old authority unchanged. NO institutional launch."),
        expected_cases=qualification.cases(), full_reservation_usd=str(reserve),
        gate="All24 fresh exact factual reports or legal actions; complete consistent native reasoning, pinned route, certified receipt or exactly four404s retaining the entire reservation.",
        failure="Independent safe wrong facts/illegal actions remain failed and other assigned tasks continue. ONE exact answerless AtlasCloud shared-pool429 may be reissued once after shared300 seconds with BOTH full reservations retained. Second/ineligible transport/native/route/usage/unknown billing/source/budget failures stop globally. No content/receipt retries, repair, fallback, replacements or old-run reinterpretation.",
        interface="Common conditional score ledger plus original keyed substantive facts, action schemas and presence reporting. Every possible enacted-policy score is displayed without an action recommendation or forecast. Counterfactuals require combining own/peer ballots and role/horizon bookkeeping; terminal totals are disclosed and can be copied, not proof of strategic competence. One actual AUTO tool OR an entire plain JSON / exact json fence, optionally exact submit_decision newline label. No prose extraction, dual channels, coercion or inferred actions. Full raw actions and approved128-character public-text execution retained.",
        selection="Fresh constructive diagnostic frame:4 terminal role reports,8 counterfactual own-ballot/enactment/horizon reports,12 legal actions; both terms/all phases/four arms. Common deterministic conditional score ledger added, without changing payoffs, roles, history, action schemas or native configuration. Fixed coverage, not research-population sampling. Earlier substantive and instrument failures remain failed.",
        limitations="A small diagnostic pass is not long-run reliability, a randomized interface/provider effect, accountability evidence or publication evidence. Every failure remains. Institutional work requires its own reviewed freeze and full budget admission."))


def prepare(root, metadata=None, ledger_root=BUDGET):
    root = Path(root)
    require(not root.exists(), "fresh run directory required")
    seeds = seed_audit()
    if metadata is None:
        with t.opener().open(route.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    route.check_endpoint(metadata)
    before = Ledger(ledger_root).snapshot()
    require(Decimal(before["accounted_usd"]) + CAP <= route.STOP, "ten-dollar authority exceeded")
    roots = source_roots()
    if Path(ledger_root).resolve() == BUDGET.resolve():
        roots.append(readiness_check())
    snapshot = {str(path.relative_to(ROOT)): path.read_text() for path in closure(ROOT, roots)}
    protocol = dict(**specification(), seed_audit=seeds, pre_stage_budget=before,
                    prior_ledger_entries=prior_inventory(ledger_root), endpoint_metadata=metadata,
                    metadata_observed_unix=time.time())
    manifest = dict(protocol=protocol, sources={name: t.sha(value.encode()) for name, value in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    for name in ("calls", "sessions"):
        (root / name).mkdir()
    atomic(root / "sources.json", snapshot)
    atomic(root / "manifest.json", manifest)
    return t.sha(t.canonical(manifest).encode())


def verify(root):
    manifest, sources = t.load(Path(root) / "manifest.json"), t.load(Path(root) / "sources.json")
    require(set(manifest["sources"]) == set(sources), "source inventory")
    for name, digest in manifest["sources"].items():
        path = Path(name)
        require(not path.is_absolute() and ".." not in path.parts, "unsafe source path")
        require(t.sha((ROOT / path).read_bytes()) == digest == t.sha(sources[name].encode()),
                "frozen source changed: " + name)
    require(all(t.canonical(manifest["protocol"].get(key)) == t.canonical(value)
                for key, value in specification().items()), "protocol changed")
    require(not manifest["protocol"]["seed_audit"]["overlap"], "seed overlap")
    route.check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, ledger_root=BUDGET, secret=None, send=None, lookup=None, clock=time.time, sleep=time.sleep):
    root = Path(root)
    manifest, protocol = verify(root)
    require(0 <= clock() - manifest["protocol"]["metadata_observed_unix"] <= 3600, "stale metadata")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not list((root / "calls").iterdir()) and not list((root / "sessions").iterdir()),
                "already started; never restart")
        ledger = StopLedger(ledger_root)
        require(ledger.snapshot() == manifest["protocol"]["pre_stage_budget"], "pre-stage budget changed")
        verify_prior(ledger_root, manifest["protocol"]["prior_ledger_entries"], STAGE)
        ledger.allocate(STAGE, CAP)
        atomic(root / "sessions/start.json", dict(pid=os.getpid(), protocol=protocol, started_unix=clock()))
        calls = service.Calls(root, ledger_root, STAGE, 25, lambda: verify(root), score,
                              CONFIG, secret, send, lookup, clock, sleep)
        calls.ledger = ledger
        results, reissues = [], []
        physical_results = {recovery.physical(case, attempt)["id"]:
            dict(id=recovery.physical(case, attempt)["id"], status="not_started")
            for case in cases() for attempt in (1, 2)}
        for case in cases():
            logical = dict(id=case["id"], status="not_started", attempts=[], final_id=None)
            if calls.stop.is_set():
                results.append(logical)
                continue
            for attempt in (1, 2):
                physical = recovery.physical(case, attempt)
                status = calls.one(physical)
                physical_results[physical["id"]] = status
                logical["attempts"].append(status)
                logical.update(status=status["status"], final_id=physical["id"])
                saved = (t.load(root / "calls" / (physical["id"] + ".json"))
                         if status["status"] == "recorded" else {})
                scope = failure_scope.classify(status["status"], saved.get("result"))
                eligible = recovery.eligibility(saved, logical_attempt=attempt,
                                                recoveries_used=len(reissues))
                if scope == "global_stop" and eligible["eligible"] and not calls.stop.is_set():
                    detected = clock()
                    event = dict(id=physical["id"], protocol=protocol,
                        logical_id=case["id"], eligibility=eligible,
                        request_sha256=physical["request_sha256"], detected_unix=detected,
                        not_before_unix=detected + recovery.DELAY_SECONDS)
                    reissues.append(event)
                    atomic(root / "sessions/reissue.json", event)
                    while clock() < event["not_before_unix"]:
                        sleep(min(1, event["not_before_unix"] - clock()))
                    continue
                if scope == "global_stop" or calls.stop.is_set():
                    calls.stop.set()
                break
            results.append(logical)
        verify_prior(ledger_root, manifest["protocol"]["prior_ledger_entries"], STAGE)
        terminal = dict(protocol=protocol, results=results,
                        physical_results=list(physical_results.values()), reissues=reissues,
                        global_safety_stop=calls.stop.is_set(),
                        budget=ledger.snapshot(), ended_unix=clock())
        atomic(root / "sessions/terminal.json", terminal)
        return terminal


def _audit_locked(root, ledger_root):
    root, ledger_root = Path(root), Path(ledger_root)
    manifest, protocol = verify(root)
    terminal = t.load(root / "sessions/terminal.json")
    require(t.load(root / "sessions/start.json")["protocol"] == terminal["protocol"] == protocol,
            "terminal protocol")
    verify_prior(ledger_root, manifest["protocol"]["prior_ledger_entries"], STAGE)
    physical_cases = [recovery.physical(case, attempt) for case in cases() for attempt in (1, 2)]
    physical_reports, cost = service.audit_records(root, ledger_root, STAGE, protocol,
        physical_cases, dict(results=terminal["physical_results"]), score, CONFIG)
    by_id = {report["id"]: report for report in physical_reports}
    physical = sorted((t.load(p) for p in (root / "calls").glob("*.json")), key=lambda row: row["admitted_unix"])
    require(all(a["ended_unix"] <= b["admitted_unix"] for a, b in zip(physical, physical[1:])), "serial request overlap")
    require(len(physical) <= 25 and len(terminal["reissues"]) <= 1, "physical/reissue ceilings")
    require([row["id"] for row in terminal["results"]] == [case["id"] for case in cases()],
            "logical assignments changed")
    events = terminal["reissues"]
    event_path = root / "sessions/reissue.json"
    require(event_path.exists() == bool(events), "reissue evidence missing/extra")
    if events:
        require(t.load(event_path) == events[0], "reissue event changed")
    expected_physical, reports = [], []
    global_stop, failed, recovered = False, False, 0
    for case, logical in zip(cases(), terminal["results"], strict=True):
        first, second = (by_id[recovery.physical(case, attempt)["id"]] for attempt in (1, 2))
        attempts = logical["attempts"]
        if global_stop:
            require(logical == dict(id=case["id"], status="not_started", attempts=[], final_id=None)
                and first["status"] == second["status"] == "not_started", "admission after global stop")
            reports.append(dict(id=case["id"], status="not_started", result=None,
                                failure_scope="not_started", attempts=[]))
            failed = True
            continue
        require(first["status"] != "not_started" and len(attempts) in (1, 2),
                "unexplained skipped independent case")
        first_scope = failure_scope.classify(first["status"], first.get("result"))
        row = t.load(root / "calls" / (first["id"] + ".json")) if first["status"] == "recorded" else {}
        eligible = recovery.eligibility(row, logical_attempt=1, recoveries_used=recovered)
        retry = first_scope == "global_stop" and eligible["eligible"]
        require(len(attempts) == (2 if retry else 1), "reissue policy changed")
        final = first
        if retry:
            require(recovered == 0 and len(events) == 1 and second["status"] != "not_started",
                    "unassigned/exhausted reissue")
            event = events[0]
            require(event["id"] == first["id"] and event["protocol"] == protocol and
                event["logical_id"] == case["id"] and event["eligibility"] == eligible and
                event["request_sha256"] == case["request_sha256"] and
                event["detected_unix"] >= row["ended_unix"] and
                event["not_before_unix"] == event["detected_unix"] + 300,
                "reissue provenance/eligibility/cooldown changed")
            require(all(not event["detected_unix"] < r["admitted_unix"] < event["not_before_unix"]
                        for r in physical), "admission during cooldown")
            second_path = root / "calls" / (second["id"] + ".json")
            if second_path.exists():
                require(t.load(second_path)["admitted_unix"] >= event["not_before_unix"], "premature reissue")
            recovered += 1
            final = second
        else:
            require(second["status"] == "not_started", "extra physical attempt")
        used_reports = [first, second] if retry else [first]
        require(attempts == [dict(id=r["id"], status=r["status"]) for r in used_reports]
                and logical["status"] == final["status"] and logical["final_id"] == final["id"],
                "logical physical selection changed")
        expected_physical.extend(r["id"] for r in used_reports if (root / "calls" / (r["id"] + ".json")).exists())
        report = dict(id=case["id"], status=final["status"], result=final.get("result"),
                      attempts=used_reports)
        scope = failure_scope.classify(report["status"], report.get("result"))
        global_stop |= scope == "global_stop"
        failed |= scope != "passed"
        report["failure_scope"] = scope
        reports.append(report)
    require(recovered == len(events) and [row["id"] for row in physical] == expected_physical,
            "physical ordering/reissue inventory changed")
    require(global_stop == terminal["global_safety_stop"], "failure-scope stop mismatch")
    ledger = Ledger(ledger_root)
    entries = ledger._entries()
    used = ledger._total(entries)
    authority = t.load(ledger_root / "authority.json")
    budget = dict(budget_id=authority["budget_id"], cap_usd=authority["cap_usd"],
                  accounted_usd=str(used), remaining_usd=str(Decimal(authority["cap_usd"]) - used),
                  entries=len(entries), pending=sum(row["status"] != "settled" for row in entries),
                  uncertified=sum(row.get("certified") is False for row in entries))
    require(budget == terminal["budget"], "terminal budget changed")
    require(cost <= CAP and Decimal(budget["accounted_usd"]) <= route.STOP, "budget authority exceeded")
    passed = not failed and not terminal["global_safety_stop"]
    return dict(protocol=protocol, assignments=reports, calls=len(list((root / "calls").glob("*.json"))),
                physical_assignments=physical_reports, reissues=events,
                gate_passed=passed, verdict="qualification_passed" if passed else "qualification_failed",
                accounted_usd=str(cost), cumulative_accounted_usd=budget["accounted_usd"],
                global_safety_stop=terminal["global_safety_stop"], publication_evidence=False,
                limitations=specification()["limitations"])


def audit(root, ledger_root=BUDGET):
    with Ledger(ledger_root).locked():
        return _audit_locked(root, ledger_root)


@cache
def archive_helper():
    spec = importlib.util.spec_from_file_location("_deepseek_gate_archive", ROOT / "analysis/paper3_contracts_archive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def export(root, ledger_root, target, destination, secret=None):
    root, ledger_root, target = (Path(path).resolve() for path in (root, ledger_root, target))
    helper = archive_helper()
    require(not target.exists() and not Path(destination).exists(), "archive destination exists")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with Ledger(ledger_root).locked():
            report = _audit_locked(root, ledger_root)
            contents = {"code/" + name: value.encode() for name, value in t.load(root / "sources.json").items()}
            for prefix, directory in (("run", root), ("ledger", ledger_root)):
                for path in directory.rglob("*"):
                    require(not path.is_symlink(), "symlink in archive")
                    if path.is_file() and path.suffix == ".json":
                        contents[prefix + "/" + str(path.relative_to(directory))] = path.read_bytes()
            contents["expected_report.json"] = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = ("# DeepSeek conditional-score-ledger qualification\n\n"
        "A gate is not an institutional finding. All failures remain. Fresh replay: "
        "`python3 -I -S code/experiments/paper3_retrospective_score_ledger_gate_v1.py . --replay "
        "--expected-protocol " + report["protocol"] + "`.\n").encode()
    for name, value in contents.items():
        helper.safe(target, name)
        helper.credentials(value, secret)
    metadata = dict(format=helper.FORMAT, experiment_family=STAGE, protocol=report["protocol"],
                    files={name: t.sha(value) for name, value in sorted(contents.items())})
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
    root, helper = Path(root).resolve(), archive_helper()
    metadata = helper.verify_bundle(root, expected_protocol)
    require(metadata["experiment_family"] == STAGE and ROOT == root / "code", "isolated gate code required")
    sys.addaudithook(helper.offline_guard)
    report = audit(root / "run", root / "ledger")
    require(t.canonical(report) == t.canonical(t.load(root / "expected_report.json")), "replay report changed")
    return dict(**report, portable_replay=dict(exact_report_match=True, protocol=expected_protocol))


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
        result = dict(protocol=prepare(args.root))
    else:
        require(args.expected_protocol, "expected protocol required")
        if args.replay:
            result = replay(args.root, args.expected_protocol)
        else:
            require(verify(args.root)[1] == args.expected_protocol, "unexpected protocol")
            if args.run:
                result = execute(args.root, secret=t.read_key())
            elif args.audit:
                result = audit(args.root)
            else:
                require(args.target and args.archive, "archive paths required")
                result = export(args.root, BUDGET, args.target, args.archive, t.read_key())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
