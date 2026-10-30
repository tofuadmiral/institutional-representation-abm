"""Final keyed-payoff accountability qualification with bounded transport recovery.

18 logical cases, at most20 requests, $0.25 cap within the shared $8 stop.
No wrong-answer retry, content repair, fallback, inherited pass or automatic pilot.
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
from paper3 import hosted_reasoning_channel_calls as service
from paper3 import retrospective_keyed_qualification as qualification
from paper3 import retrospective_transport_recovery as recovery
from paper3 import retrospective_deepseek_route as route
from paper3.pivot_b_budget import Ledger, atomic
from paper3.retrospective_execution import StopLedger, jsonable, prior_inventory, verify_prior
from paper3.source_closure import closure

STAGE = "pivot_b_retrospective_keyed_gate_v1"
CAP = Decimal(".25")
BUDGET = ROOT / "results/paper3/pivot_b_budget"
CONFIG = dict(models=[route.MODEL, route.MODEL_ALIAS], provider=route.PROVIDER,
              output_bound=route.OUTPUT_BOUND)
require = t.require


@cache
def cases():
    rows = []
    for value in qualification.requests():
        bound = route.reservation(value["request"])
        for attempt in (1, 2):
            rows.append(dict(id=value["id"] + f"-a{attempt}", request=value["request"],
                context=dict(**value["context"], logical_id=value["id"], logical_attempt=attempt),
                **bound, request_sha256=t.sha(bound["request_text"].encode())))
    return tuple(rows)


def accepted(report):
    return bool(report["status"] == "recorded" and report.get("result") and
                all(report["result"][key] for key in ("usable", "valid_action", "exact")))


def recoverable(row, used):
    verdict = recovery.eligibility(row, CONFIG, attempt_number=1, recoveries_used=used)
    if not verdict["eligible"]:
        return verdict
    assessment = row.get("assessment") or {}
    if (Decimal(assessment.get("accounted_usd", "Infinity")) > Decimal(row["reserved_usd"]) or
            any(x.get("secret_redacted") or (x.get("http_status") == 200 and
                not assessment.get("receipt_certified")) for x in row.get("receipts", []))):
        return dict(eligible=False, reason="accounting_or_receipt_safety")
    usage = assessment.get("stream", {}).get("usage")
    if usage is not None:
        if (not isinstance(usage, dict) or
                type(usage.get("prompt_tokens")) is not int or
                not 0 <= usage["prompt_tokens"] <= row["input_token_bound"] or
                type(usage.get("completion_tokens")) is not int or
                not 0 <= usage["completion_tokens"] <= route.OUTPUT_BOUND):
            return dict(eligible=False, reason="accounting_token_bound")
    return verdict

def score(row, case):
    result = dict(usable=False, valid_action=False, exact=False,
                  native_reasoning=None, action=None, failure="instrument_or_unfinished")
    if row.get("instrument_error") or "assessment" not in row:
        return result
    assessed = service.assess(row, CONFIG)
    native = service.native_evidence(assessed["stream"])
    usable = (assessed["passed"] and assessed["stream"]["finish_reasons"] == ["tool_calls"]
              and native["present"] and row["request"]["reasoning"] == dict(enabled=True, exclude=False))
    result.update(usable=usable, native_reasoning=native)
    if usable:
        context = next(item for item in qualification.cases() if item["id"] == case["context"]["case_id"])
        result.update(qualification.score(context, row["stream"]))
    else:
        result["failure"] = "transport_reasoning_or_function_completion"
    return result


def seed_audit(root=ROOT):
    planned = {qualification.FRAME_SEED, *(qualification.SEED_BASE + i for i in range(18))}
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
    primary = [Decimal(row["reserved_usd"]) for row in cases()[::2]]
    reserve = sum(primary) + sum(sorted(primary, reverse=True)[:recovery.MAX_RECOVERIES])
    require(len(cases()) == 36 and reserve <= CAP, "qualification/extra-attempt cap bound")
    return jsonable(dict(name=STAGE, logical_cases=18, max_calls=20, workers=1,
        max_attempts_per_case=recovery.MAX_ATTEMPTS_PER_CASE,
        max_recoveries=recovery.MAX_RECOVERIES, recovery_delay_seconds=recovery.REISSUE_DELAY_SECONDS,
        cap_usd=str(CAP), cumulative_stop_usd=str(route.STOP),
        frame_seed=qualification.FRAME_SEED, seed_base=qualification.SEED_BASE,
        configuration=CONFIG, cases=cases(), expected_cases=qualification.cases(),
        full_reservation_usd=str(reserve), primary_reservation_usd=str(sum(primary)),
        recovery="Only frozen content-blind framing/connection failures. Exact identical wire/seed/route; one recovery per case, two globally; both charges or uncertified reservations retained. No execution of partial tools.",
        failure="Stop on wrong/invalid/completed/length/malformed/safety/billing-only failures or failed second attempt. No repair, fallback, replacement or automatic institutional run.",
        gate="All eighteen fresh tasks require exact factual reports or legal actions, complete native reasoning, pinned route and certified billing for the accepted attempt. Every failed attempt and its conservative cost remains.",
        interface="Policy-keyed payoff cards and common verified district sums; lossless utilities, unchanged history, assessments, factual/legality scoring, sampling and14,000 output ceiling. AUTO server choice, strict one-function acceptance.",
        limitations="Final prospectively specified keyed-interface qualification after retained earlier failures. Deterministic arithmetic assistance changes representation, not underlying preferences or private evidence; no randomized interface/model/transport effect, proof faults independent of task/content, strategic result or publication evidence. Recovery can select for finishable trajectories and remains visible. No prior passes inherited. If this gate fails, stop paid variants of this numerical election instrument pending a human decision."))

def prepare(root, metadata=None, ledger_root=BUDGET):
    root = Path(root)
    require(not root.exists(), "fresh run directory required")
    seeds = seed_audit()
    if metadata is None:
        with t.opener().open(route.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    route.check_endpoint(metadata)
    before = Ledger(ledger_root).snapshot()
    require(Decimal(before["accounted_usd"]) + CAP <= route.STOP, "eight-dollar authority exceeded")
    roots = [Path(__file__), ROOT / "analysis/paper3_contracts_archive.py", BUDGET / "authority.json",
             ROOT / "tests/test_paper3_retrospective_keyed_interface.py",
             ROOT / "tests/test_paper3_retrospective_keyed_gate.py",
             ROOT / "tests/test_paper3_retrospective_transport_recovery.py"]
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
        results = {case["id"]: dict(id=case["id"], status="not_started") for case in cases()}
        decisions, halted = [], False

        def ask(case):
            # Each service instance makes one network request. A second logical
            # attempt has its own immutable file/ledger ID, not a cleared stop.
            client = service.Calls(root, ledger_root, STAGE, 20, lambda: verify(root), score,
                                   CONFIG, secret, send, lookup, clock, sleep)
            client.ledger = ledger
            result = client.one(case)
            results[case["id"]] = result
            return result

        for first, second in zip(cases()[::2], cases()[1::2], strict=True):
            if halted:
                break
            result = ask(first)
            row = t.load(root / "calls" / (first["id"] + ".json")) if result["status"] == "recorded" else None
            if row and accepted(dict(**result, result=row["result"])):
                continue
            permitted = recoverable(row, len(decisions)) if row else dict(eligible=False)
            if not permitted["eligible"]:
                halted = True
                break
            # Persist eligibility before waiting/admission; never use answer
            # validity as an eligibility criterion. Both reservations remain.
            decision = dict(protocol=protocol, logical_id=first["context"]["logical_id"],
                            from_id=first["id"], to_id=second["id"], eligibility=permitted,
                            ordinal=len(decisions) + 1, decided_unix=clock(),
                            not_before_unix=row["ended_unix"] + recovery.REISSUE_DELAY_SECONDS)
            decisions.append(decision)
            atomic(root / "sessions" / f"recovery-{len(decisions):03d}.json", decision)
            require(first["request_text"] == second["request_text"] and
                    first["request_sha256"] == second["request_sha256"], "recovery wire changed")
            sleep(max(0, decision["not_before_unix"] - clock()))
            require(clock() >= decision["not_before_unix"], "recovery delay not observed")
            result = ask(second)
            row = t.load(root / "calls" / (second["id"] + ".json")) if result["status"] == "recorded" else None
            if not row or not accepted(dict(**result, result=row["result"])):
                halted = True
                break
        verify_prior(ledger_root, manifest["protocol"]["prior_ledger_entries"], STAGE)
        terminal = dict(protocol=protocol, results=list(results.values()),
                        recoveries=decisions, global_safety_stop=halted,
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
    reports, cost = service.audit_records(root, ledger_root, STAGE, protocol, cases(), terminal, score, CONFIG)
    require(len(list((root / "calls").glob("*.json"))) <= 20, "request cap")
    logical, decisions, halted = [], [], False
    for first, second, a, b in zip(cases()[::2], cases()[1::2], reports[::2], reports[1::2], strict=True):
        require(first["request_text"] == second["request_text"] and
                first["request_sha256"] == second["request_sha256"], "nonidentical recovery request")
        winner = None
        if halted:
            require(a["status"] == b["status"] == "not_started", "admission after logical failure")
        elif accepted(a):
            require(b["status"] == "not_started", "recovery of a completed accepted answer")
            winner = a["id"]
        else:
            raw = t.load(root / "calls" / (a["id"] + ".json")) if a["status"] == "recorded" else None
            eligible = recoverable(raw, len(decisions)) if raw else dict(eligible=False)
            if eligible["eligible"]:
                require(b["status"] != "not_started", "eligible recovery not attempted")
                path = root / "sessions" / f"recovery-{len(decisions) + 1:03d}.json"
                event = t.load(path)
                require(event["protocol"] == protocol and
                        event["logical_id"] == first["context"]["logical_id"] and
                        event["from_id"] == a["id"] and event["to_id"] == b["id"] and
                        event["eligibility"] == eligible and event["ordinal"] == len(decisions) + 1,
                        "recovery eligibility/event changed")
                require(event["decided_unix"] >= raw["ended_unix"] and
                        event["not_before_unix"] == raw["ended_unix"] + recovery.REISSUE_DELAY_SECONDS,
                        "recovery scheduling changed")
                attempt_path = root / "calls" / (b["id"] + ".json")
                if attempt_path.exists():
                    actual = t.load(attempt_path)
                    require(actual["admitted_unix"] >= event["not_before_unix"], "early reissue")
                decisions.append(event)
                if accepted(b):
                    winner = b["id"]
                else:
                    halted = True
            else:
                require(b["status"] == "not_started", "ineligible response was reissued")
                halted = True
        logical.append(dict(id=first["context"]["logical_id"], accepted_attempt=winner,
                            passed=winner is not None,
                            attempts=[a, b]))
    require(len(decisions) <= recovery.MAX_RECOVERIES and
            terminal["recoveries"] == decisions, "recovery inventory changed")
    require({p.name for p in (root / "sessions").glob("recovery-*.json")} ==
            {f"recovery-{i + 1:03d}.json" for i in range(len(decisions))}, "extra recovery event")
    require(terminal["global_safety_stop"] == halted, "safety verdict changed")

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
    passed = all(row["passed"] for row in logical) and not halted
    return dict(protocol=protocol, assignments=reports, logical_cases=logical,
                recovery_count=len(decisions), passed_logical_cases=sum(row["passed"] for row in logical),
                calls=len(list((root / "calls").glob("*.json"))),
                gate_passed=passed, verdict="qualification_passed" if passed else "qualification_failed",
                accounted_usd=str(cost), cumulative_accounted_usd=budget["accounted_usd"],
                global_safety_stop=terminal["global_safety_stop"], publication_evidence=False,
                limitations=specification()["limitations"])


def audit(root, ledger_root=BUDGET):
    with Ledger(ledger_root).locked():
        return _audit_locked(root, ledger_root)


@cache
def archive_helper():
    spec = importlib.util.spec_from_file_location("_keyed_gate_archive", ROOT / "analysis/paper3_contracts_archive.py")
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
    contents["README.md"] = ("# Keyed-payoff qualification with bounded transport recovery\n\n"
        "A gate is not an institutional finding. All failures remain. Fresh replay: "
        "`python3 -I -S code/experiments/paper3_retrospective_keyed_gate.py . --replay "
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
