"""Continue the unchanged institution from immutable accepted evidence.

prepare is offline. run/resume share a single-writer durable response cache;
audit recomputes every decision without model calls. No old root is restarted.
"""

# ruff: noqa: E402
import argparse
from contextlib import redirect_stdout
from decimal import Decimal
from fractions import Fraction
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments import paper3_retrospective_deepinfra_pilot_v2 as original_runner
from experiments import paper3_transport_diagnostic as diagnostic
from paper3 import retrospective_graceful_recovery as recovery
from paper3 import retrospective_billing_calls as native
from paper3 import retrospective_deepinfra_budget_v2 as budget
from paper3 import retrospective_deepinfra_design_v2 as design
from paper3 import retrospective_deepinfra_execution_v1 as execution
from paper3 import retrospective_deepinfra_failure_v1 as failure
from paper3 import retrospective_deepinfra_freeze_v2 as original_freeze
from paper3 import retrospective_deepinfra_requests_v1 as requests
from paper3 import retrospective_deepinfra_route_v1 as route
from paper3 import retrospective_anticipation_analysis as science
from paper3 import retrospective_episode_journal as journal
from paper3 import hosted_reasoning_transport_v2 as transmitter
from paper3 import retrospective_recovery_funding_v2 as funding
from paper3.retrospective_source_closure import closure

OLD_PROTOCOL = "59e3cf26bac211c9ce6e7958e376fb65e6826edc004818048d04271b245d3866"
OLD_ROOT = "results/paper3/pivot_b_retrospective_deepinfra_pilot_v2"
ROOT_NAME = "results/paper3/pivot_b_graceful_continuation_v1"
AUTHORITY = "results/paper3/graceful_recovery_authorization_2026_10_23.json"
LEDGER = "results/paper3/pivot_b_budget"
OLD_ARCHIVE_SHA = "ef95dcadf92c56c53c11416c1153ffa67de1408921dd42cec012a5b580a7c352"
TEST_COMMAND = [
    ".venv/bin/python",
    "-m",
    "pytest",
    "tests/test_paper3_graceful_recovery.py",
    "tests/test_paper3_graceful_continuation.py",
    "-q",
    "--tb=short",
    "-x",
]
READINESS = "results/paper3/graceful_continuation_readiness_2026_10_23.json"
require, load, digest = recovery.require, recovery.load, recovery.digest


def dump(value):
    return journal.canonical(journal.encode(value))


def items():
    return tuple(
        a
        for seed in design.FRAME_SEEDS
        for a in design.assignments()
        if a["seed"] == seed
    )


def authority():
    a = load(REPO / AUTHORITY)
    require(
        a["total_cumulative_cap_usd"] == "19.30"
        and a["model_provider_parameters_and_scientific_rules_unchanged"] is True
        and a["maximum_physical_requests_across_original_and_continuation"] == 560
        and a["credit_purchase"] is False,
        "exact continuation authority",
    )
    return a


def source_inventory():
    old = load(REPO / OLD_ROOT / "manifest.json")
    roots = [REPO / name for name in old["sources"]]
    roots += [
        Path(__file__),
        REPO / "paper3/retrospective_graceful_recovery.py",
        REPO / AUTHORITY,
        REPO / "tests/test_paper3_graceful_recovery.py",
        REPO / "tests/test_paper3_graceful_continuation.py",
    ]
    return {p.relative_to(REPO).as_posix(): digest(p) for p in closure(REPO, roots)}


def baseline():
    """Use the genuine original closeout; don't rerun a qualification ladder."""
    original_freeze.verify(REPO / OLD_ROOT, REPO, OLD_PROTOCOL)
    closeout = load(
        REPO
        / "results/paper3/pivot_b_retrospective_deepinfra_pilot_v2_closeout_2026_10_22.json"
    )
    require(
        closeout["archive"]["sha256"] == OLD_ARCHIVE_SHA
        and closeout["production_export"]["certificate"]["isolated_report_matched"]
        is True
        and digest(REPO / closeout["archive"]["path"]) == OLD_ARCHIVE_SHA,
        "original genuinely replayed archive changed",
    )
    prefix, failures, references = {}, {}, {}
    old = REPO / OLD_ROOT
    for p in sorted((old / "block-0/calls").glob("*.json")):
        row = load(p)
        ref = dict(path=p.relative_to(REPO).as_posix(), sha256=digest(p))
        references[ref["path"]] = ref["sha256"]
        key = row["context"]["logical_id"]
        if row["result"]["status"] == "recorded_valid":
            require(key not in prefix, "duplicate accepted prefix")
            prefix[key] = ref
        else:
            require(
                recovery.overload(row)["eligible"], "prior failure cannot be retried"
            )
            failures.setdefault(key, []).append(ref)
    require(
        len(prefix) == 111 and sum(map(len, failures.values())) == 1,
        "exact original accepted prefix",
    )
    bounds = []
    for frame in design.FRAME_SEEDS:
        group = tuple(a for a in items() if a["seed"] == frame)
        envelopes = {
            a["id"]: requests.legal_history_bounds(a["game"], a["arm"], a["seed_base"])
            for a in group
        }
        unstarted = [
            Decimal(envelopes[a["id"]]["per_call_reservations_usd"][i])
            for a in group
            for i in range(30)
            if a["id"] + f"-{i:02d}" not in prefix
            and a["id"] + f"-{i:02d}" not in failures
        ]
        largest = max(Decimal(e["largest_attempt_usd"]) for e in envelopes.values())
        bounds.append(
            dict(
                frame=frame,
                cap_usd=str(sum(unstarted, Decimal(0)) + 40 * largest),
                maximum_new_physical=len(unstarted) + 40,
            )
        )
    allocation = load(old / "sessions/allocation.json")
    old_stage = allocation["group"] + "-1"
    for name in ("block-1", "sessions/block-1-start.json"):
        require(not (old / name).exists(), "original second block already started")
    return dict(
        prefix=prefix,
        failures=failures,
        references=references,
        bounds=bounds,
        reused_stage=old_stage,
        reused_stage_sha=allocation["stage_pins"][old_stage],
        original_archive_sha256=OLD_ARCHIVE_SHA,
    )


def ledger(stage_pins=None):
    return budget.RecoveryLedger(
        REPO / LEDGER,
        stage_pins=stage_pins,
        retirement_pins=original_freeze.RETIREMENT_PINS,
    )


def prepare():
    root = REPO / ROOT_NAME
    require(not root.exists(), "prepare once only; resume an existing new root")
    authority()
    ready = load(REPO / READINESS)
    sources = source_inventory()
    require(
        ready["argv"] == TEST_COMMAND
        and ready["returncode"] == 0
        and not ready["stderr"].strip()
        and "passed" in ready["stdout"]
        and ready["sources_before"] == ready["sources_after"] == sources,
        "genuine current-source offline checks required",
    )
    b = baseline()
    book = ledger()
    snapshot = book.snapshot()
    require(
        Decimal(b["bounds"][0]["cap_usd"])
        <= Decimal(snapshot["available_for_new_stages_usd"]),
        "continuation funding exceeds authority",
    )
    require(
        Decimal(b["bounds"][1]["cap_usd"])
        <= Decimal(
            load(REPO / LEDGER / budget.STAGES / (b["reused_stage"] + ".json"))[
                "cap_usd"
            ]
        ),
        "existing unstarted block cannot fund its unchanged assignments",
    )
    with book.locked():
        prior = {p.name: digest(p) for p in (REPO / LEDGER / "entries").glob("*.json")}
    manifest = dict(
        format=recovery.VERSION,
        sources=sources,
        baseline=b,
        readiness_sha256=digest(REPO / READINESS),
        authority_sha256=digest(REPO / AUTHORITY),
        original_protocol=OLD_PROTOCOL,
        assignments=journal.encode(items()),
        prior_entries=prior,
        baseline_budget=snapshot,
        disclosure="Technical recovery amendment after failure; original verdict remains incomplete. "
        "Not pristine confirmatory evidence or independent validation.",
    )
    protocol = hashlib.sha256(journal.canonical(manifest).encode()).hexdigest()
    root.mkdir(exist_ok=False)
    atomic(root / "manifest.json", manifest)
    return dict(
        protocol=protocol,
        reused_accepted_actions=111,
        new_logical_actions=369,
        bounds=b["bounds"],
        new_model_calls=0,
    )


atomic = budget.atomic


def verify(root, protocol):
    root = Path(root)
    m = load(root / "manifest.json")
    require(
        hashlib.sha256(journal.canonical(m).encode()).hexdigest() == protocol,
        "external protocol differs",
    )
    require(
        m["authority_sha256"] == digest(REPO / AUTHORITY)
        and m["readiness_sha256"] == digest(REPO / READINESS),
        "authority/readiness changed",
    )
    for name, sha in m["sources"].items():
        require(digest(REPO / name) == sha, "frozen source changed: " + name)
    return m, protocol


def classify(row, request, key):
    assignment = next(a for a in items() if key.startswith(a["id"] + "-"))
    stage = json.loads(request["messages"][1]["content"])["stage"]
    return failure.classify(row, request, assignment["game"], stage)


def check_record(path, row, manifest, pins, *, reconcile=False):
    """Validate request, native evidence AND exact full financial settlement."""
    require(row["status"] == "recorded", "in-flight request requires reconciliation")
    relative = Path(path).relative_to(REPO).as_posix()
    if relative in manifest["baseline"]["references"]:
        require(
            digest(path) == manifest["baseline"]["references"][relative]
            and row["protocol"] == OLD_PROTOCOL,
            "original response changed",
        )
        stage = load(REPO / OLD_ROOT / "sessions/block-0-start.json")["stage"]
    else:
        frame_index = next(
            i
            for i, frame in enumerate(design.FRAME_SEEDS)
            if any(
                row["context"]["logical_id"].startswith(a["id"] + "-")
                for a in items()
                if a["seed"] == frame
            )
        )
        stage = pins["stages"][frame_index]
        require(row["protocol"] == pins["protocol"], "new physical protocol changed")
    e = load(REPO / LEDGER / "entries" / (stage + "-" + row["id"] + ".json"))
    a = native.assess(row, failure.previous.CONFIG)
    if (
        relative not in manifest["baseline"]["references"]
        and e["status"] == "reserved"
        and reconcile
    ):
        # A process can die after saving the full response but before settling
        # its already-reserved charge. Finish ONLY that deterministic transaction;
        # no new inference, receipt lookup, repair or new charge is generated.
        require(
            row["assessment"] == a
            and row["result"]
            == classify(row, row["request"], row["context"]["logical_id"])
            and e["request_sha256"] == row["request_sha256"]
            and e["reserved_usd"] == row["reserved_usd"],
            "cannot reconcile altered evidence",
        )
        ledger(pins["stage_pins"]).settle(
            e["request_id"], a["accounted_usd"], a["receipt_certified"], digest(path)
        )
        e = load(REPO / LEDGER / "entries" / (stage + "-" + row["id"] + ".json"))
    require(
        row["assessment"] == a
        and e["status"] == "settled"
        and e["evidence_sha256"] == digest(path)
        and e["request_sha256"] == row["request_sha256"]
        and e["reserved_usd"] == row["reserved_usd"]
        and e["accounted_usd"] == a["accounted_usd"]
        and e["certified"] == a["receipt_certified"],
        "physical/ledger settlement mismatch",
    )
    if not e["certified"]:
        require(
            Decimal(e["accounted_usd"]) >= Decimal(e["reserved_usd"]),
            "uncertain costs released",
        )


def allocate(root, protocol, manifest):
    path = root / "allocation.json"
    if path.exists():
        pins = load(path)
        validate_pins(pins, manifest, protocol)
        return pins
    stage0 = "graceful-" + protocol[:16] + "-0"
    book = ledger()
    # A deterministic group can be recovered after an allocation/index crash,
    # but an existing stage is never allocated or mutated again.
    group_path = REPO / LEDGER / budget.GROUPS / (stage0 + ".json")
    if group_path.exists():
        group = load(group_path)
        require(
            set(group["stages"]) == {stage0}
            and group["stages"][stage0]["prior_entries"] == manifest["prior_entries"]
            and Decimal(group["cap_usd"])
            == Decimal(manifest["baseline"]["bounds"][0]["cap_usd"]),
            "ambiguous existing allocation",
        )
        stage_pins = {
            stage0: digest(REPO / LEDGER / budget.STAGES / (stage0 + ".json"))
        }
    else:
        require(
            {p.name: digest(p) for p in (REPO / LEDGER / "entries").glob("*.json")}
            == manifest["prior_entries"],
            "baseline changed before allocation",
        )
        stage_pins = book.allocate(
            stage0, manifest["baseline"]["bounds"][0]["cap_usd"]
        )["stage_pins"]
    old = manifest["baseline"]["reused_stage"]
    stage_pins[old] = manifest["baseline"]["reused_stage_sha"]
    pins = dict(protocol=protocol, stages=[stage0, old], stage_pins=stage_pins)
    atomic(path, pins)
    validate_pins(pins, manifest, protocol)
    return pins


def validate_pins(pins, manifest, protocol):
    require(
        pins["protocol"] == protocol
        and pins["stages"]
        == ["graceful-" + protocol[:16] + "-0", manifest["baseline"]["reused_stage"]]
        and pins["stage_pins"][pins["stages"][1]]
        == manifest["baseline"]["reused_stage_sha"],
        "exact assigned financial stages required",
    )
    book = ledger(pins["stage_pins"])
    with book.locked():
        for i, stage in enumerate(pins["stages"]):
            record = book._stage(stage)
            require(
                Decimal(record["cap_usd"])
                >= Decimal(manifest["baseline"]["bounds"][i]["cap_usd"]),
                "full remaining block reservation",
            )
            if i == 0:
                require(
                    record["prior_entries"] == manifest["prior_entries"]
                    and Decimal(record["cap_usd"])
                    == Decimal(manifest["baseline"]["bounds"][0]["cap_usd"]),
                    "new allocation baseline/cap changed",
                )


def run(root, protocol, *, send=None, lookup=None, secret=None, admission=None):
    root = Path(root)
    with (root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        m, _ = verify(root, protocol)
        require(not (root / "report.json").exists(), "already terminal; audit instead")
        # All original incurred entries are immutable even on resumed admission.
        for name, sha in m["prior_entries"].items():
            require(
                digest(REPO / LEDGER / "entries" / name) == sha, "old entry changed"
            )
        if admission:
            admission(m)
        pins = allocate(root, protocol, m)
        book = ledger(pins["stage_pins"])
        send = send or transmitter.transmit
        lookup = lookup or diagnostic.receipt_lookup
        starts = root / "invocations"
        starts.mkdir(exist_ok=True)
        n = len(list(starts.glob("*-start.json")))
        atomic(
            starts / f"{n:04d}-start.json",
            dict(pid=os.getpid(), started_unix=time.time(), protocol=protocol),
        )
        reports = []
        try:
            for index, frame in enumerate(design.FRAME_SEEDS):
                state = root / f"block-{index}"
                state.mkdir(exist_ok=True)
                for name in ("calls",):
                    (state / name).mkdir(exist_ok=True)
                stage = pins["stages"][index]
                bound = m["baseline"]["bounds"][index]
                start = state / "admission.json"
                if not start.exists():
                    atomic(
                        start,
                        dict(
                            started_unix=time.time(), deadline_unix=time.time() + 86400
                        ),
                    )
                deadline = load(start)["deadline_unix"]

                def guard():
                    return verify(root, protocol)

                def perform(request, key, physical_id):
                    require(time.time() < deadline, "block admission deadline")
                    case = dict(
                        id=physical_id,
                        request=request,
                        **route.reservation(request),
                        context=dict(
                            stage=json.loads(request["messages"][1]["content"])[
                                "stage"
                            ],
                            logical_id=key,
                        ),
                    )
                    case["request_sha256"] = hashlib.sha256(
                        case["request_text"].encode()
                    ).hexdigest()

                    def score(row, unused):
                        return classify(row, request, key)

                    calls = native.Calls(
                        state,
                        REPO / LEDGER,
                        stage,
                        bound["maximum_new_physical"],
                        guard,
                        score,
                        failure.previous.CONFIG,
                        secret,
                        send,
                        lookup,
                        time.time,
                        time.sleep,
                    )
                    calls.ledger = book
                    with redirect_stdout(io.StringIO()):
                        result = calls.one(case)
                    require(
                        result["status"] == "recorded",
                        "physical request did not settle",
                    )
                    return state / "calls" / (physical_id + ".json")

                def recover_claim(record, request):
                    entry = (
                        REPO
                        / LEDGER
                        / "entries"
                        / (stage + "-" + record["physical_id"] + ".json")
                    )
                    require(not entry.exists(), "possibly sent request: no blind retry")
                    return perform(request, record["logical_id"], record["physical_id"])

                cache = recovery.DurableResponses(
                    state,
                    REPO,
                    protocol=protocol,
                    classify=classify,
                    perform=perform,
                    check_record=lambda p, r: check_record(
                        p, r, m, pins, reconcile=True
                    ),
                    verify=guard,
                    prefix=m["baseline"]["prefix"],
                    initial_failures=m["baseline"]["failures"],
                    maximum_physical=bound["maximum_new_physical"],
                    recover_claim=recover_claim,
                    clock=time.time,
                    sleep=time.sleep,
                )
                try:
                    report = execution.execute(
                        tuple(a for a in items() if a["seed"] == frame),
                        respond=cache.respond,
                        verify=guard,
                        persist=lambda event: None,
                    )
                    require(
                        not report["global_safety_stop"],
                        "unexpected economic/controller stop",
                    )
                    reports.append(report)
                    print(
                        json.dumps(
                            dict(
                                event="frame_complete",
                                frame=frame,
                                complete_episodes=report["completed"],
                            )
                        ),
                        flush=True,
                    )
                finally:
                    cache.close()
            result = readout(reports)
            atomic(root / "report.json", journal.encode(result))
            atomic(
                starts / f"{n:04d}-terminal.json",
                dict(status="complete", completed_unix=time.time()),
            )
            return dict(
                status="complete", analysis=result["analysis"]["candidate_screen"]
            )
        except recovery.Paused as exc:
            atomic(
                starts / f"{n:04d}-terminal.json",
                dict(
                    status="paused",
                    reason=exc.reason,
                    automatic=exc.automatic,
                    completed_unix=time.time(),
                ),
            )
            return dict(status="paused", reason=exc.reason, automatic=exc.automatic)


def readout(reports):
    rows = tuple(row for r in reports for row in r["assignments"])
    observations = {r["id"]: tuple(r["terms"]) for r in rows}
    require(len(rows) == 16, "retain all assigned episodes")
    analysis = science.analyze(
        items(),
        observations,
        minimum_effect=Fraction(1, 25),
        aligned_fraction=Fraction(1, 2),
    )
    return dict(
        assignments=rows,
        analysis=analysis,
        publication_evidence=False,
        disclosure="Technical continuation of previously incomplete discovery; not independent validation.",
    )


def audit(root, protocol):
    root = Path(root)
    with (root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        m, _ = verify(root, protocol)
        pins = load(root / "allocation.json")
        # The production financial adapter independently verifies all stage and
        # historical entry bindings. Private unit fixtures exercise raw replay.
        if "reused_stage" in m["baseline"]:
            validate_pins(pins, m, protocol)
        reports, referenced, expected_requests = [], set(), {}
        for index, frame in enumerate(design.FRAME_SEEDS):
            state = root / f"block-{index}"

            def respond(request, key):
                expected_requests[key] = route.reservation(request)["request_text"]
                ref = m["baseline"]["prefix"].get(key)
                if ref is None:
                    ref = load(state / "accepted" / (key + ".json"))
                path = REPO / ref["path"]
                require(digest(path) == ref["sha256"], "accepted reference changed")
                row = load(path)
                check_record(path, row, m, pins)
                require(
                    row["request_text"] == route.reservation(request)["request_text"],
                    "exact economic replay request",
                )
                referenced.add(path.resolve())
                return dict(row, id=key)

            report = execution.execute(
                tuple(a for a in items() if a["seed"] == frame),
                respond=respond,
                verify=lambda: verify(root, protocol),
                persist=lambda e: None,
            )
            reports.append(report)
            for p in (state / "calls").glob("*.json"):
                row = load(p)
                check_record(p, row, m, pins)
                if p.resolve() not in referenced:
                    require(
                        recovery.overload(row)["eligible"], "unused non-overload answer"
                    )
            # Replaying DurableResponses in audit would send nothing only when
            # terminal, but its attempt chains must still be independently bound.
            for p in (state / "attempts").glob("*.json"):
                a = load(p)
                ref = a["evidence"]
                row = load(REPO / ref["path"])
                require(
                    digest(REPO / ref["path"]) == ref["sha256"]
                    and row["id"] == a["physical_id"]
                    and row["request_sha256"] == a["request_sha256"]
                    and a["protocol"] == protocol,
                    "physical attempt evidence mismatch",
                )
            chains = {}
            for p in (state / "attempts").glob("*.json"):
                record = load(p)
                require(p.name == record["physical_id"] + ".json", "attempt filename")
                chains.setdefault(record["logical_id"], []).append(record)
            reissues = 0
            for key, chain in chains.items():
                require(key in expected_requests, "unassigned or unexecuted request")
                chain.sort(key=lambda a: a["attempt"])
                prior = m["baseline"]["failures"].get(key, [])
                require(
                    [a["attempt"] for a in chain]
                    == list(range(len(prior) + 1, len(prior) + len(chain) + 1))
                    and len(prior) + len(chain) <= 4,
                    "attempt limit/gap",
                )
                previous = load(REPO / prior[-1]["path"]) if prior else None
                for record in chain:
                    row = load(REPO / record["evidence"]["path"])
                    require(
                        row["request_text"] == expected_requests[key],
                        "retry changed wire or seed",
                    )
                    if previous is not None:
                        eligible = recovery.overload(previous)
                        require(eligible["eligible"], "retried content/answer failure")
                        wait = max(
                            recovery.COOLDOWNS[record["attempt"] - 2],
                            eligible["delay"] or 0,
                        )
                        require(
                            row["admitted_unix"] >= previous["ended_unix"] + wait,
                            "retry violated cooldown/Retry-After",
                        )
                    reissues += record["attempt"] > 1
                    previous = row
            require(
                reissues <= 40
                and sum(map(len, chains.values()))
                <= m["baseline"]["bounds"][index]["maximum_new_physical"],
                "block request/retry cap",
            )
            require(
                {load(p)["physical_id"] for p in (state / "attempts").glob("*.json")}
                == {p.stem for p in (state / "calls").glob("*.json")},
                "unmatched raw physical call",
            )
        result = readout(reports)
        require(
            dump(result) == journal.canonical(load(root / "report.json")),
            "entire recomputed report mismatch",
        )
        return dict(
            protocol=protocol,
            entire_report_matched=True,
            analysis=result["analysis"]["candidate_screen"],
            budget=ledger(pins["stage_pins"]).snapshot(),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("prepare", "run", "audit"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--expected-protocol")
    args = parser.parse_args()
    if args.prepare:
        require(args.expected_protocol is None, "new preparation has no prior protocol")
        result = prepare()
    else:
        require(args.expected_protocol is not None, "external protocol pin required")
        root = REPO / ROOT_NAME
        if args.audit:
            result = audit(root, args.expected_protocol)
        else:
            secret = original_runner.read_secret(REPO)

            def admission(m):
                book = ledger()
                with book.locked():
                    rows = book._entries()
                    unresolved = sum(
                        (
                            Decimal(r.get("accounted_usd", r["reserved_usd"]))
                            for r in rows
                            if r["status"] != "settled" or r.get("certified") is False
                        ),
                        Decimal(0),
                    )
                full = sum(Decimal(b["cap_usd"]) for b in m["baseline"]["bounds"])
                account = funding.observe(secret, full + unresolved)
                with diagnostic.opener().open(
                    route.METADATA_URL, timeout=20
                ) as response:
                    metadata = json.load(response)
                route.check_endpoint(metadata)
                log = root / "admissions"
                log.mkdir(exist_ok=True)
                atomic(
                    log / f"{time.time_ns()}.json",
                    dict(account=account, metadata=metadata),
                )

            result = run(
                root, args.expected_protocol, secret=secret, admission=admission
            )
    print(json.dumps(result, default=str), flush=True)


if __name__ == "__main__":
    main()
