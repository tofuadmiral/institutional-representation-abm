"""One fresh prospectively frozen validation; no paid qualification or old rerun.

Uses identical tested durable worker/economic/transport code objects, explicitly
injecting only fresh cases, current cumulative authority and prospective readout.
"""
# ruff: noqa: E402
import argparse
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments import paper3_graceful_continuation as previous
from paper3 import retrospective_validation_budget_v1 as budget
from paper3 import retrospective_validation_design_v1 as design
from paper3 import retrospective_receipt_recovery_v1 as billing
from paper3 import retrospective_anticipation_analysis as science
from paper3 import retrospective_graceful_recovery as recovery
from paper3 import retrospective_episode_journal as journal
from paper3.retrospective_source_closure import closure

ROOT_NAME = "results/paper3/pivot_b_independent_validation_v1"
LEDGER = previous.LEDGER
AUTHORITY = "results/paper3/independent_validation_authorization_2026_10_27.json"
AUTHORITY_SHA = "79541295e0c953801c48fd0915e4de1bbaba12f35145801d9ec4a8ba376ea336"
READINESS = "results/paper3/independent_validation_readiness_2026_10_27.json"
DISCOVERY = "results/paper3/pivot_b_graceful_continuation_v1"
DISCOVERY_REPORT_SHA = "cce94f8ed48d86898522f918e16904b2815ce83c966d79b87652be248636df19"
DISCOVERY_ARCHIVE = "paper3/data/pivot_b_graceful_continuation_v1_complete.zip"
DISCOVERY_ARCHIVE_SHA = "c7cca9cfbd8656865723277217d941e16177f2e0ed35a8ac2a2a8c06a5cb04c7"
TEST_COMMAND = [".venv/bin/python", "-B", "-m", "pytest",
    "tests/test_paper3_independent_validation_v1.py",
    "tests/test_paper3_graceful_recovery.py",
    "tests/test_paper3_billing_recovery_v1.py", "-q", "--tb=short", "-x"]
require, load, digest = recovery.require, recovery.load, recovery.digest
atomic, dump = budget.atomic, previous.dump


def items():
    return tuple(a for seed in design.FRAME_SEEDS for a in design.assignments()
                 if a["seed"] == seed)


def specification():
    return dict(frame_seeds=design.FRAME_SEEDS, order_seed=design.ORDER_SEED,
        assignments=journal.encode(items()), bounds=design.full_bound(),
        primary=dict(metric=science.METRIC, horizon="first_term",
            minimum_effect="1/25", aligned_fraction="1/2", two_sided=True,
            all_sixteen_first_terms_required=True, same_sign_both_frames=True),
        replication=dict(prior_direction="increased_distortion",
            per_frame_control_rule="abs(D_aligned) <= abs(D_conflict)/2 in EACH fresh frame",
            original_candidate_screen_retained=True,
            reverse_or_no_lead_reported_without_replacement=True),
        disclosure="Fresh selected settings and seeds; no inherited responses. Two settings/one model "
            "are a bounded replication, not population or motive/publication evidence.")


def authority():
    a = load(REPO / AUTHORITY)
    require(digest(REPO / AUTHORITY) == AUTHORITY_SHA
        and a["total_cumulative_cap_usd"] == "21.31"
        and a["whole_validation_maximum_usd"] == str(design.EXPECTED_FULL_BOUND)
        and a["episodes"] == 16 and a["logical_actions"] == 480
        and a["maximum_physical_requests"] == 560
        and a["frame_seeds"] == list(design.FRAME_SEEDS)
        and a["credit_purchase"] is False, "exact fresh validation authority")
    return a


def source_inventory():
    old = load(REPO / DISCOVERY / "billing_amendment_v1/manifest.json")
    roots = [REPO / n for n in old["sources"]]
    roots += [Path(__file__), REPO / AUTHORITY,
        REPO / LEDGER / budget.EXTENSION_FILE,
        REPO / "paper3/retrospective_validation_budget_v1.py",
        REPO / "paper3/retrospective_validation_design_v1.py",
        REPO / "analysis/paper3_validation_checks_v1.py",
        REPO / "tests/test_paper3_independent_validation_v1.py"]
    return {p.relative_to(REPO).as_posix(): digest(p) for p in closure(REPO, roots)}


def ledger(stage_pins=None):
    return budget.ValidationLedger(REPO / LEDGER, stage_pins=stage_pins)


def prior_entries():
    return {p.name: digest(p) for p in sorted((REPO / LEDGER / "entries").glob("*.json"))}


def prepare():
    root = REPO / ROOT_NAME
    require(not root.exists(), "prepare exactly once; existing root is not replaceable")
    authority()
    sources = source_inventory()
    ready = load(REPO / READINESS)
    require(ready["argv"] == TEST_COMMAND and ready["returncode"] == 0
        and not ready["stderr"].strip() and "passed" in ready["stdout"]
        and ready["sources_before"] == ready["sources_after"] == sources
        and ready["specification"] == journal.encode(specification()),
        "genuine exact current-source whole-file readiness required")
    require(digest(REPO / DISCOVERY / "report.json") == DISCOVERY_REPORT_SHA
        and digest(REPO / DISCOVERY_ARCHIVE) == DISCOVERY_ARCHIVE_SHA,
        "completed discovery remains immutable")
    old = load(REPO / DISCOVERY / "billing_amendment_v1/manifest.json")
    for name, sha in old["sources"].items():
        require(digest(REPO / name) == sha, "old frozen source changed")
    seeds = design.seed_audit(REPO)
    book = ledger()
    with book.locked():
        entries = prior_entries()
        rows = book._entries()
        used, held = book._total(rows), book._commitments(rows)
    snapshot = book.snapshot()
    require(Decimal(snapshot["available_for_new_stages_usd"])
        >= design.EXPECTED_FULL_BOUND, "whole fresh comparison must fit before any call")
    bounds = [dict(frame=b["frame_seed"], cap_usd=b["full_reservation_usd"],
                   maximum_new_physical=b["maximum_physical_calls"])
              for b in design.full_bound()["blocks"]]
    manifest = dict(format=design.FORMAT, sources=sources,
        readiness_sha256=digest(REPO / READINESS), authority_sha256=AUTHORITY_SHA,
        specification=journal.encode(specification()), seed_audit=seeds,
        prior_entries=entries, baseline_budget=snapshot,
        allocation_baseline=dict(prior_entries=entries, accounted_usd=str(used),
            unused_commitments_usd=str(held)),
        baseline=dict(prefix={}, failures={}, references={}, bounds=bounds),
        discovery_report_sha256=DISCOVERY_REPORT_SHA,
        discovery_archive_sha256=DISCOVERY_ARCHIVE_SHA,
        zero_inherited_responses=True, publication_evidence=False)
    protocol = hashlib.sha256(journal.canonical(manifest).encode()).hexdigest()
    root.mkdir(exist_ok=False)
    atomic(root / "manifest.json", manifest)
    return dict(protocol=protocol, sources=len(sources), logical_actions=480,
                full_reservation_usd=str(design.EXPECTED_FULL_BOUND), model_calls=0)


def verify(root, protocol):
    m = load(Path(root) / "manifest.json")
    require(hashlib.sha256(journal.canonical(m).encode()).hexdigest() == protocol
        and m["format"] == design.FORMAT, "external fresh protocol changed")
    require(m["authority_sha256"] == AUTHORITY_SHA == digest(REPO / AUTHORITY)
        and m["readiness_sha256"] == digest(REPO / READINESS), "authority/readiness changed")
    require(m["sources"] == source_inventory(), "complete frozen source closure changed")
    require(m["baseline"]["prefix"] == m["baseline"]["failures"]
        == m["baseline"]["references"] == {} and m["zero_inherited_responses"] is True,
        "fresh validation may inherit no actions")
    return m, protocol


def validate_pins(pins, m, protocol):
    expected = ["validation-" + protocol[:16] + f"-{i}" for i in range(2)]
    require(pins["protocol"] == protocol and pins["stages"] == expected
            and set(pins["stage_pins"]) == set(expected), "exact whole validation allocation")
    book = ledger(pins["stage_pins"])
    with book.locked():
        for stage, bound in zip(expected, m["baseline"]["bounds"], strict=True):
            record = book._stage(stage)
            require(record["prior_entries"] == m["prior_entries"]
                and Decimal(record["cap_usd"]) == Decimal(bound["cap_usd"]),
                "preassigned full block cap/prior-entry inventory changed")


def allocate(root, protocol, m):
    path = root / "allocation.json"
    if path.exists():
        pins = load(path)
        validate_pins(pins, m, protocol)
        return pins
    group = "validation-" + protocol[:16]
    stages = [group + f"-{i}" for i in range(2)]
    gp = REPO / LEDGER / budget.GROUPS / (group + ".json")
    book = ledger()
    if gp.exists():
        saved = book._group(group)
        require(set(saved["stages"]) == set(stages), "ambiguous existing stage group")
        pins = {s: digest(REPO / LEDGER / budget.STAGES / (s + ".json")) for s in stages}
    else:
        pins = book.allocate_group(group,
            {s: b["cap_usd"] for s, b in zip(stages, m["baseline"]["bounds"], strict=True)},
            expected_baseline=m["allocation_baseline"])["stage_pins"]
    result = dict(protocol=protocol, stages=stages, stage_pins=pins)
    validate_pins(result, m, protocol)
    atomic(path, result)
    return result


def classify(row, request, key):
    assignment = next(a for a in items() if key.startswith(a["id"] + "-"))
    stage = json.loads(request["messages"][1]["content"])["stage"]
    return billing.classify(row, request, assignment["game"], stage)


def readout(reports):
    rows = tuple(row for report in reports for row in report["assignments"])
    require(len(rows) == 16, "all fresh assignments retained")
    analysis = science.analyze(items(), {r["id"]: tuple(r["terms"]) for r in rows},
        minimum_effect=Fraction(1, 25), aligned_fraction=Fraction(1, 2))
    controls = []
    # Controls are evaluated separately in each setting; opposite signs cannot
    # cancel into a validation pass. The original two-sided screen is unchanged.
    for frame in analysis["per_frame"]:
        aligned = frame["aligned"]["support_bounds"]
        conflict = frame["conflict"]["support_bounds"]
        complete = aligned[0] == aligned[1] and conflict[0] == conflict[1]
        controls.append(dict(seed=frame["seed"], aligned_bounds=aligned,
            conflict_bounds=conflict,
            passed=complete and abs(aligned[0]) <= abs(conflict[0])/2))
    screen = analysis["candidate_screen"]
    replication = (screen["selected_case_lead"] and screen["direction"] == "increased_distortion"
                   and all(c["passed"] for c in controls))
    return dict(assignments=rows, analysis=analysis,
        validation=dict(positive_discovery_replicated=replication,
            per_frame_controls=tuple(controls),
            original_two_sided_screen=screen,
            independent_fresh_assignments=True,
            prior_response_or_setting_reuse=False),
        publication_evidence=False, disclosure=specification()["disclosure"])


def drivers(admission=None):
    class FreshCalls(billing.Calls):
        def one(self, case):
            if admission is not None and not getattr(admission, "first_checked", False):
                require(0 <= time.time() - admission.observed_unix <= 60,
                        "launch route no longer fresh; no request sent")
                admission.first_checked = True
            return super().one(case)

    deps = dict(REPO=REPO, LEDGER=LEDGER, design=design, items=items, verify=verify,
        ledger=ledger, allocate=allocate, validate_pins=validate_pins,
        native=SimpleNamespace(assess=billing.assess, Calls=FreshCalls),
        execution=SimpleNamespace(execute=billing.execute),
        classify=classify, readout=readout)
    check = billing.bind(previous.check_record, **deps)
    deps["check_record"] = check
    return billing.bind(previous.run, **deps), billing.bind(previous.audit, **deps)


def run(root, protocol, **kwargs):
    return drivers(kwargs.get("admission"))[0](root, protocol, **kwargs)


def audit(root, protocol):
    root = Path(root)
    m, _ = verify(root, protocol)
    for name, sha in m["prior_entries"].items():
        require(digest(REPO / LEDGER / "entries" / name) == sha, "historical entry changed")
    pins = load(root / "allocation.json")
    validate_pins(pins, m, protocol)
    result = drivers()[1](root, protocol)
    rows = ledger(pins["stage_pins"])._entries()
    for i, stage in enumerate(pins["stages"]):
        require({r["request_id"] for r in rows if r["stage"] == stage}
            == {stage + "-" + p.stem for p in (root / f"block-{i}/calls").glob("*.json")},
            "orphan stage charge/raw evidence")
    result["validation"] = load(root / "report.json")["validation"]
    return result


def live_admission(root, protocol, secret):
    """One late exact route observation; no metadata polling/fallback."""
    def admit(m):
        # Do all expensive old-entry/allocation verification BEFORE the observer.
        allocate(root, protocol, m)
        book = ledger(load(root / "allocation.json")["stage_pins"])
        with book.locked():
            rows = book._entries()
            unresolved = sum((Decimal(r.get("accounted_usd", r["reserved_usd"]))
                for r in rows if r["status"] != "settled" or r.get("certified") is False), Decimal(0))
            remaining = sum((max(Decimal(0), Decimal(book._stage(stage)["cap_usd"])
                - book._total(rows, stage)) for stage in book._stage_pins), Decimal(0))
        account = previous.funding.observe(secret, remaining + unresolved)
        with previous.diagnostic.opener().open(previous.route.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
        observed = time.time()
        previous.route.check_endpoint(metadata)
        (root / "admissions").mkdir(exist_ok=True)
        atomic(root / "admissions" / f"{time.time_ns()}.json",
            dict(account=account, metadata=metadata, metadata_observed_unix=observed,
                protocol=protocol))
        require(0 <= time.time() - observed <= 60, "strict route freshness")
        admit.observed_unix = observed
    return admit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("prepare", "run", "audit"):
        modes.add_argument("--" + mode, action="store_true")
    parser.add_argument("--expected-protocol")
    args = parser.parse_args()
    root = REPO / ROOT_NAME
    if args.prepare:
        require(args.expected_protocol is None, "no invented prepare protocol")
        result = prepare()
    else:
        require(args.expected_protocol is not None, "external protocol required")
        if args.audit:
            result = audit(root, args.expected_protocol)
        else:
            secret = previous.original_runner.read_secret(REPO)
            result = run(root, args.expected_protocol, secret=secret,
                admission=live_admission(root, args.expected_protocol, secret))
    print(json.dumps(journal.encode(result)), flush=True)


if __name__ == "__main__":
    main()
