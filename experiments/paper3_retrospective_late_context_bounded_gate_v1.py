"""Fresh16-action late-context feasibility gate; .40cap, at most25 physical.

Only this diagnostic is executable. No old-run reclassification or institution
launch. This gate deliberately enforces the stricter existing17 ledger while
pinning the new19 authority; disposition/new19 pilot implementation is separate.
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
from threading import Event

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import paper3_transport_diagnostic as t
from paper3 import retrospective_billing_calls as service
from paper3 import retrospective_late_context_bounded_gate_v1 as qualification
from paper3 import retrospective_recovery_budget_v2 as budget17
from paper3 import retrospective_recovery_funding_v2 as funding
from paper3 import retrospective_recovery_retirement_v2 as old_retirement
from paper3 import retrospective_failure_scope as failure_scope
from paper3 import retrospective_late_context_bounded_retry_v1 as recovery
from paper3 import retrospective_contract_route_v2 as route
from paper3.pivot_b_budget import atomic
from paper3.retrospective_execution import jsonable, verify_prior
from paper3.retrospective_serial_execution import prior_inventory
from paper3.source_closure import closure

STAGE = "pivot_b_retrospective_late_context_bounded_gate_v1"
CAP = Decimal(".40")
SCOPE_FILE = "pivot_b_retrospective_late_context_bounded_gate_v1_authorization.json"
SCOPE_SHA = "ee69c330a42d7dcc476afda61fec469603c5bd20b30b1b6b0a283a2319198527"
EXTENSION_FILE = "authority_extension_2026_10_16.json"
EXTENSION_SHA = "a7fe6f79cb2f9ef2d98975a917706cbe76714208bbee0f384c7750a280525e11"
OLD_RETIREMENT_SHA = "ac9070f7ac2c0404a8150623a57f48452d05821325f3c5c58ffda1bdd7949028"
OLD_PROTOCOL = "f81bc5019d840e7cb4fe147d084a4ad699523f382541f33dd485927c154d64fc"
BUDGET = ROOT / "results/paper3/pivot_b_budget"
CONFIG = dict(models=[route.MODEL, route.MODEL_ALIAS], provider=route.PROVIDER,
              output_bound=route.OUTPUT_BOUND)
require = t.require


def source_roots():
    return [Path(__file__), ROOT / "analysis/paper3_contracts_archive.py",
            ROOT / "tests/test_paper3_retrospective_late_context_bounded_runner_v1.py",
            ROOT / "tests/test_paper3_retrospective_late_context_bounded_gate_v1.py",
            ROOT / "requirements.txt", ROOT / "results/paper3" / SCOPE_FILE,
            *(BUDGET / n for n in (*budget17.AUTHORITY_FILES, EXTENSION_FILE))]


def _extension(ledger_root):
    path = Path(ledger_root) / EXTENSION_FILE
    require(not path.is_symlink() and t.sha(path.read_bytes()) == EXTENSION_SHA,
            "direct total19 approval changed")
    value = t.load(path)
    require(value["previous_total_cap_usd"] == "17.00" and
            value["new_total_cap_usd"] == "19.00" and
            value["previous_extension_sha256"] == budget17.EXTENSION_SHA and
            value["credit_purchases_authorized"] is False and
            value["old_protocols_modified"] is False, "authority scope")
    scope_path = Path(ledger_root).parent / SCOPE_FILE
    require(not scope_path.is_symlink() and t.sha(scope_path.read_bytes()) == SCOPE_SHA,
            "new bounded gate approval changed/missing")
    scope = t.load(scope_path)
    require(scope["maximum_physical_requests"] == 25 and
        scope["maximum_reissues_per_action"] == 3 and scope["maximum_reissues_total"] == 9
        and scope["all_sixteen_must_pass"] is True
        and scope["authority_extension_sha256"] == EXTENSION_SHA,
        "new bounded scope required")
    return value


def _ledger(ledger_root, root):
    _extension(ledger_root)
    allocation = Path(root) / "allocation.json"
    pins = t.load(allocation)["stage_pins"] if allocation.exists() else {}
    retirement_path = Path(ledger_root) / old_retirement.DIRECTORY / (old_retirement.STAGE + ".json")
    retirements = {old_retirement.STAGE: OLD_RETIREMENT_SHA} if retirement_path.exists() else {}
    return budget17.RecoveryLedger(ledger_root, stage_pins=pins, retirement_pins=retirements)


def _snapshot_locked(ledger):
    rows = ledger._entries()
    used, commitments = ledger._total(rows), ledger._commitments(rows)
    return dict(budget_id=t.load(ledger.root / "authority.json")["budget_id"],
        cap_usd=str(budget17.TOTAL_CAP), original_cap_usd="10.00",
        authority_extension_sha256=budget17.EXTENSION_SHA, accounted_usd=str(used),
        remaining_usd=str(budget17.TOTAL_CAP-used), entries=len(rows),
        unspent_active_stage_caps_usd=str(commitments),
        available_for_new_stages_usd=str(budget17.TOTAL_CAP-used-commitments),
        pending=sum(r["status"] != "settled" for r in rows),
        uncertified=sum(r.get("certified") is False for r in rows))


def _required_funding(ledger):
    unresolved = sum((Decimal(r["accounted_usd"] if r["status"] == "settled" else r["reserved_usd"])
        for r in ledger._entries() if r["status"] != "settled" or r.get("certified") is False),
        Decimal(0))
    return unresolved + CAP


def _actual_root_guard(root, ledger_root):
    if Path(ledger_root).resolve() != BUDGET.resolve():
        return  # Explicit fabricated/private ledgers or network-denied archive replay.
    require(Path(root).resolve() == (ROOT / "results/paper3" / STAGE).resolve(),
            "only approved actual gate root")
    old = ROOT / "results/paper3/pivot_b_retrospective_anticipation_recovery_v2"
    manifest = t.load(old / "manifest.json")
    require(t.sha(t.canonical(manifest).encode()) == OLD_PROTOCOL, "old protocol changed")
    for name, digest in manifest["sources"].items():
        require(t.sha((ROOT / name).read_bytes()) == digest, "old frozen source changed")
    terminal = t.load(ROOT / "results/paper3/pivot_b_retrospective_anticipation_recovery_v2_terminal_summary_2026_10_16.json")
    require(terminal["global_safety_stop"] is True and terminal["block1_never_started"] is True,
            "old terminal prerequisite")
    old_gate = ROOT / "results/paper3/pivot_b_retrospective_late_context_gate_v1"
    gate_manifest = t.load(old_gate / "manifest.json")
    require(t.sha(t.canonical(gate_manifest).encode()) ==
        "81bb972a51fe21f3f844dbcd3a2a890f3048741e52ecea0cac3c11029e89509a",
        "old gate manifest changed")
    for name, digest in gate_manifest["sources"].items():
        require(t.sha((ROOT / name).read_bytes()) == digest, "old gate frozen source changed")
    terminal_path = ROOT / "results/paper3/pivot_b_retrospective_late_context_gate_v1_terminal_summary_2026_10_16.json"
    require(t.sha(terminal_path.read_bytes()) ==
        "9c253fdb0dd4492fe7f832cd427601eb7b12129df4004fc57bb24b31bb6550c1", "old gate terminal evidence changed")


def readiness_check():
    path = ROOT / "results/paper3" / (STAGE + "_preflight.json")
    record = t.load(path)
    actual = {str(p.relative_to(ROOT)): t.sha(p.read_bytes())
              for p in closure(ROOT, source_roots())}
    require(record["sources"] == actual and record["specification_sha256"] ==
            t.sha(t.canonical(specification()).encode()), "readiness source/specification changed")
    check = record["offline_tests"]
    expected = [".venv/bin/python", "-B", "-m", "pytest",
        "tests/test_paper3_retrospective_late_context_bounded_runner_v1.py",
        "tests/test_paper3_retrospective_late_context_bounded_gate_v1.py", "-q", "--tb=short"]
    import re
    require(record["qualification_approved"] is True and record["actual_model_calls"] == 0
        and check["command"] == expected and check["returncode"] == 0 and check["stderr"] == ""
        and re.search(r"(?:^|\n)[1-9][0-9]* passed in [0-9.]+s(?: \([0-9:]+\))?\s*$", check["stdout"])
        and not re.search(r"\b(failed|error|skipped|deselected|xfailed|xpassed)\b", check["stdout"]),
        "genuine whole-file offline checks required")
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
    planned = {qualification.FRAME_SEED, *(qualification.SEED_BASE + i for i in range(16))}
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
    reserve = qualification.bound()
    require(len(cases()) == 16 and Decimal(reserve["full_reservation_usd"]) <= CAP,
            "sixteen fixed calls and full reissue budget")
    return jsonable(dict(name=STAGE, max_calls=16, max_physical_calls=25,
        max_reissues=9, max_reissues_per_action=3, cooldown_seconds=recovery.COOLDOWNS,
        admission_deadline_seconds=86400, workers=1, cap_usd=str(CAP),
        cumulative_stop_usd=str(budget17.TOTAL_CAP), newly_approved_total_usd="19.00",
        enforced_ledger_stop_usd="17.00", authority_extension_sha256=EXTENSION_SHA,
        frame_seed=qualification.FRAME_SEED, seed_base=qualification.SEED_BASE,
        configuration=CONFIG, cases=cases(), expected_cases=qualification.cases(),
        full_reservation_usd=reserve["full_reservation_usd"],
        approval=dict(response="yes approved", date="2026-10-16", scope_sha256=SCOPE_SHA,
            thread_id="01a09ba8-a109-7b62-a8a0-61519cfdea84",
            scope="One fresh16-task late-context check max25physical,3reissues/action9total,cap0.40; no institutional launch."),
        gate="All16 complete native, consistent, legal actions; no preferred vote/policy, no inherited passes.",
        failure="Any global instrument/unknown-billing failure stops. Complete illegal actions are retained failed. Only exact answerless AtlasCloud shared-pool429 permits at most3 identical reissues/action9total after300/600/1200seconds; every full reservation retained. No content or receipt retry or replacement gate.",
        selection="One fresh six-policy diagnostic frame; all4arms x all4phases in term2 with maximal legal public message lengths. 7representatives/63citizens, same native wire/tool grammar. Synthetic scripted histories, not observed bargaining or a sampled population.",
        limitations="Late-context feasibility only. Not long-run reliability, strategic competence, an institutional effect, randomized interface comparison or publication evidence. No old record is reclassified. One separately tested/frozen pilot only after gate pass and full financial/source/route admission."))


def prepare(root, metadata=None, ledger_root=BUDGET):
    root = Path(root)
    require(not root.exists(), "fresh run directory required")
    _actual_root_guard(root, ledger_root)
    _extension(ledger_root)
    ledger = _ledger(ledger_root, root)
    before = ledger.snapshot()
    require(Decimal(before["available_for_new_stages_usd"]) >= CAP, "whole gate cap unavailable")
    funding_evidence = None
    roots = source_roots()
    if Path(ledger_root).resolve() == BUDGET.resolve():
        roots.append(readiness_check())  # BEFORE account or endpoint GETs.
    seeds = seed_audit()
    if Path(ledger_root).resolve() == BUDGET.resolve():
        funding_evidence = funding.observe(t.read_key(), _required_funding(ledger))
    if metadata is None:
        with t.opener().open(route.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    route.check_endpoint(metadata)
    require(ledger.snapshot() == before, "preparation budget changed")
    snapshot = {str(path.relative_to(ROOT)): path.read_text() for path in closure(ROOT, roots)}
    protocol = dict(**specification(), seed_audit=seeds, pre_stage_budget=before,
                    prior_ledger_entries=prior_inventory(ledger_root), endpoint_metadata=metadata,
                    metadata_observed_unix=time.time(), funding_evidence=funding_evidence)
    manifest = dict(protocol=protocol, sources={name: t.sha(value.encode()) for name, value in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    for name in ("calls", "sessions"):
        (root / name).mkdir()
    atomic(root / "sources.json", snapshot)
    atomic(root / "manifest.json", manifest)
    return t.sha(t.canonical(manifest).encode())


def verify(root):
    if Path(root).resolve() == (ROOT / "results/paper3" / STAGE).resolve():
        _actual_root_guard(root, BUDGET)
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
    _actual_root_guard(root, ledger_root)
    require(0 <= clock() - manifest["protocol"]["metadata_observed_unix"] <= 60, "stale metadata")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not list((root / "calls").iterdir()) and not list((root / "sessions").iterdir()),
                "already started; never restart")
        ledger = _ledger(ledger_root, root)
        require(ledger.snapshot() == manifest["protocol"]["pre_stage_budget"], "pre-stage budget changed")
        verify_prior(ledger_root, manifest["protocol"]["prior_ledger_entries"], STAGE)
        require(not (root / "allocation.json").exists(), "existing allocation; never restart")
        if Path(ledger_root).resolve() == BUDGET.resolve():
            require(send is None and lookup is None, "actual gate uses exact default transport")
            funding_evidence = funding.observe(secret, _required_funding(ledger))
            require(0 <= clock() - manifest["protocol"]["metadata_observed_unix"] <= 60,
                    "metadata expired during funding observation")
            atomic(root / "funding-run.json", funding_evidence)
        before = manifest["protocol"]["pre_stage_budget"]
        expected_baseline = dict(prior_entries=manifest["protocol"]["prior_ledger_entries"],
            accounted_usd=before["accounted_usd"],
            unused_commitments_usd=before["unspent_active_stage_caps_usd"])
        allocation = ledger.allocate_group(STAGE, {STAGE: CAP}, expected_baseline=expected_baseline)
        atomic(root / "allocation.json", allocation)
        atomic(root / "sessions/start.json", dict(pid=os.getpid(), protocol=protocol, started_unix=clock()))
        def guarded_score(row, case):
            verify(root)  # Recheck sources AFTER response, before accepting an action.
            return score(row, case)
        # A fresh native service per physical request, as in the tested pilot
        # bridge. Its private two-failure counter is NOT the retry policy.
        # This prospective controller owns a single shared global stop; it is
        # never cleared, and no old service/run is resumed or modified.
        stop = Event()
        deadline = t.load(root / "sessions/start.json")["started_unix"] + 86400
        results, reissues = [], []
        physical_results = {recovery.physical(case, attempt)["id"]:
            dict(id=recovery.physical(case, attempt)["id"], status="not_started")
            for case in cases() for attempt in range(1, 5)}
        for case in cases():
            logical = dict(id=case["id"], status="not_started", attempts=[], final_id=None)
            if stop.is_set():
                results.append(logical)
                continue
            for attempt in range(1, 5):
                physical = recovery.physical(case, attempt)
                require(physical["request_text"] == case["request_text"] and
                    t.sha(physical["request_text"].encode()) == case["request_sha256"],
                    "identical wire and seed required")
                if clock() >= deadline:
                    stop.set()
                    status = dict(id=physical["id"], status="admission_failed")
                else:
                    calls = service.Calls(root, ledger_root, STAGE, 25, lambda: verify(root),
                        guarded_score, CONFIG, secret, send, lookup, clock, sleep)
                    calls.ledger, calls.stop = ledger, stop
                    status = calls.one(physical)
                physical_results[physical["id"]] = status
                # Error diagnostics remain in the full physical terminal row.
                # Logical selection contains only its immutable identity/status,
                # matching the independently recomputed physical audit.
                logical["attempts"].append(dict(id=status["id"], status=status["status"]))
                logical.update(status=status["status"], final_id=physical["id"])
                saved = (t.load(root / "calls" / (physical["id"] + ".json"))
                         if status["status"] == "recorded" else {})
                scope = failure_scope.classify(status["status"], saved.get("result"))
                eligible = recovery.eligibility(saved, logical_attempt=attempt,
                                                recoveries_used=len(reissues))
                if scope == "global_stop" and eligible["eligible"] and not stop.is_set():
                    detected = clock()
                    event = dict(id=physical["id"], protocol=protocol,
                        logical_id=case["id"], ordinal=len(reissues) + 1,
                        eligibility=eligible, request_sha256=physical["request_sha256"],
                        detected_unix=detected,
                        not_before_unix=detected + eligible["delay_seconds"])
                    reissues.append(event)
                    atomic(root / "sessions" / (physical["id"] + "-reissue.json"), event)
                    while clock() < event["not_before_unix"]:
                        sleep(min(1, event["not_before_unix"] - clock()))
                    continue
                if scope == "global_stop" or stop.is_set():
                    stop.set()
                break
            results.append(logical)
        verify_prior(ledger_root, manifest["protocol"]["prior_ledger_entries"], STAGE)
        verify(root)
        terminal = dict(protocol=protocol, results=results,
                        physical_results=list(physical_results.values()), reissues=reissues,
                        global_safety_stop=stop.is_set(),
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
    physical_cases = [recovery.physical(case, attempt) for case in cases() for attempt in range(1, 5)]
    physical_reports, cost = service.audit_records(root, ledger_root, STAGE, protocol,
        physical_cases, dict(results=terminal["physical_results"]), score, CONFIG)
    by_id = {report["id"]: report for report in physical_reports}
    physical = sorted((t.load(p) for p in (root / "calls").glob("*.json")), key=lambda row: row["admitted_unix"])
    require(all(a["ended_unix"] <= b["admitted_unix"] for a, b in zip(physical, physical[1:])), "serial request overlap")
    started = t.load(root / "sessions/start.json")["started_unix"]
    require(all(started <= r["admitted_unix"] < started + 86400 for r in physical),
            "request admitted beyond 24-hour gate horizon")
    require(len(physical) <= 25 and len(terminal["reissues"]) <= 9, "physical/reissue ceilings")
    require([row["id"] for row in terminal["results"]] == [case["id"] for case in cases()],
            "logical assignments changed")
    events = terminal["reissues"]
    saved_events = {p.stem: t.load(p) for p in (root / "sessions").glob("*-reissue.json")}
    require(saved_events == {e["id"] + "-reissue": e for e in events},
            "reissue evidence missing/extra/changed")
    require([e["ordinal"] for e in events] == list(range(1, len(events) + 1)),
            "reissue ordinals")
    expected_physical, reports = [], []
    global_stop, failed, recovered = False, False, 0
    for case, logical in zip(cases(), terminal["results"], strict=True):
        slots = [by_id[recovery.physical(case, attempt)["id"]] for attempt in range(1, 5)]
        attempts = logical["attempts"]
        if global_stop:
            require(logical == dict(id=case["id"], status="not_started", attempts=[], final_id=None)
                and all(r["status"] == "not_started" for r in slots), "admission after global stop")
            reports.append(dict(id=case["id"], status="not_started", result=None,
                                failure_scope="not_started", attempts=[]))
            failed = True
            continue
        require(1 <= len(attempts) <= 4 and slots[0]["status"] != "not_started",
                "unexplained skipped independent case")
        used_reports = slots[:len(attempts)]
        require(all(r["status"] == "not_started" for r in slots[len(attempts):]),
                "extra physical attempt")
        for index, report in enumerate(used_reports, 1):
            require(report["status"] != "not_started", "unattempted logical member")
            row = (t.load(root / "calls" / (report["id"] + ".json"))
                   if report["status"] == "recorded" else {})
            scope = failure_scope.classify(report["status"], report.get("result"))
            eligible = recovery.eligibility(row, logical_attempt=index, recoveries_used=recovered)
            retry = scope == "global_stop" and eligible["eligible"]
            require((index < len(attempts)) == retry, "reissue policy changed")
            if retry:
                event = events[recovered]
                require(event["id"] == report["id"] and event["protocol"] == protocol and
                    event["logical_id"] == case["id"] and event["eligibility"] == eligible and
                    event["request_sha256"] == case["request_sha256"] and
                    event["detected_unix"] >= row["ended_unix"] and
                    event["not_before_unix"] == event["detected_unix"] + eligible["delay_seconds"],
                    "reissue provenance/eligibility/cooldown changed")
                require(all(not event["detected_unix"] < r["admitted_unix"] < event["not_before_unix"]
                            for r in physical), "admission during cooldown")
                next_path = root / "calls" / (slots[index]["id"] + ".json")
                if next_path.exists():
                    next_row = t.load(next_path)
                    require(next_row["admitted_unix"] >= event["not_before_unix"] and
                        next_row["request_text"] == row["request_text"],
                        "premature or changed-wire reissue")
                recovered += 1
            expected_physical.extend([report["id"]] if (root / "calls" / (report["id"] + ".json")).exists() else [])
        final = used_reports[-1]
        require(attempts == [dict(id=r["id"], status=r["status"]) for r in used_reports]
                and logical["status"] == final["status"] and logical["final_id"] == final["id"],
                "logical physical selection changed")
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
    ledger = _ledger(ledger_root, root)
    budget = _snapshot_locked(ledger)
    require(budget == terminal["budget"], "terminal budget changed")
    require(cost <= CAP and Decimal(budget["accounted_usd"]) <= budget17.TOTAL_CAP,
            "budget authority exceeded")
    passed = not failed and not terminal["global_safety_stop"]
    return dict(protocol=protocol, assignments=reports, calls=len(list((root / "calls").glob("*.json"))),
                physical_assignments=physical_reports, reissues=events,
                gate_passed=passed, verdict="qualification_passed" if passed else "qualification_failed",
                accounted_usd=str(cost), cumulative_accounted_usd=budget["accounted_usd"],
                global_safety_stop=terminal["global_safety_stop"], publication_evidence=False,
                limitations=specification()["limitations"])


def audit(root, ledger_root=BUDGET):
    with _ledger(ledger_root, root).locked():
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
        with _ledger(ledger_root, root).locked():
            report = _audit_locked(root, ledger_root)
            contents = {"code/" + name: value.encode() for name, value in t.load(root / "sources.json").items()}
            for prefix, directory in (("run", root), ("ledger", ledger_root)):
                for path in directory.rglob("*"):
                    require(not path.is_symlink(), "symlink in archive")
                    if path.is_file() and path.suffix == ".json":
                        contents[prefix + "/" + str(path.relative_to(directory))] = path.read_bytes()
            contents["expected_report.json"] = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents[SCOPE_FILE] = (ledger_root.parent / SCOPE_FILE).read_bytes()
    contents["README.md"] = ("# DeepSeek bounded late-context qualification\n\n"
        "A gate is not an institutional finding. All failures remain. Fresh replay: "
        "`python3 -I -S code/experiments/paper3_retrospective_late_context_bounded_gate_v1.py . --replay "
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
