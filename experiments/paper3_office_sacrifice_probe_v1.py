"""One fresh fixed diagnostic cohort. Prepare offline; run once/resume safely; audit offline."""
# ruff: noqa: E402
import argparse
from contextlib import redirect_stdout
from decimal import Decimal
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from paper3 import office_sacrifice_probe_v1 as design
from paper3 import office_sacrifice_budget_v1 as budget
from paper3 import retrospective_reasoning_timeout_recovery_v1 as retry
from paper3 import retrospective_receipt_recovery_v1 as billing
from paper3 import retrospective_deepinfra_classifier_v1 as classifier
from paper3 import retrospective_deepinfra_failure_v1 as failure
from paper3 import retrospective_deepinfra_route_v1 as route
from paper3 import retrospective_graceful_recovery as durable
from paper3 import hosted_reasoning_transport_v2 as transport
from paper3 import retrospective_recovery_funding_v2 as funding
from paper3.retrospective_source_closure import closure
from paper3.pivot_b_budget import atomic
from experiments import paper3_transport_diagnostic as diagnostic
from experiments.paper3_retrospective_deepinfra_pilot_v2 import read_secret

ROOT_NAME = "results/paper3/office_sacrifice_probe_v1"
LEDGER = "results/paper3/pivot_b_budget"
AUTHORITY = "results/paper3/office_sacrifice_authorization_2026_11_04.json"
READINESS = "results/paper3/office_sacrifice_checks_2026_11_04.json"
OLD_MANIFEST = "results/paper3/pivot_b_independent_validation_v1/reasoning_timeout_amendment_v1/manifest.json"
PROTECTED = "results/paper3/offline_mechanism_audit_2026_11_01.json"
TEST_FILE = "tests/test_paper3_office_sacrifice_probe_v1.py"
require, load, digest = durable.require, durable.load, durable.digest
probe_action = billing.bind(classifier.classify, service=billing.service,
    requests=SimpleNamespace(structured=design.structured))
probe_classify = billing.bind(failure.classify,
    previous=SimpleNamespace(classify=probe_action, CONFIG=classifier.CONFIG))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sources():
    names = list(load(REPO / OLD_MANIFEST)["sources"]) + [AUTHORITY, TEST_FILE,
        "experiments/paper3_office_sacrifice_probe_v1.py"]
    return {p.relative_to(REPO).as_posix(): digest(p)
            for p in closure(REPO, [REPO / n for n in names])}


def history():
    return {p.name: digest(p) for p in sorted((REPO / LEDGER / "entries").glob("*.json"))}


def protected():
    inventory = load(REPO / PROTECTED)["protected_inventory"]
    for name, sha in inventory.items():
        require(digest(REPO / name) == sha, "protected history changed: " + name)
    return dict(count=len(inventory), inventory_sha256=hashlib.sha256(canonical(inventory).encode()).hexdigest())


def prepare():
    root = REPO / ROOT_NAME
    require(not root.exists(), "new root only; never prepare twice")
    authority = load(REPO / AUTHORITY)
    spec = design.specification()
    require(authority["total_cumulative_cap_usd"] == "21.31" and
        authority["maximum_physical_requests"] == design.MAX_PHYSICAL and
        authority["new_allocation_cap_usd"] == spec["full_reservation_usd"] and
        authority["credit_purchase"] is False and authority["blog_deferred"] is True,
        "exact prospective scope")
    src = sources()
    ready = load(REPO / READINESS)
    require(ready["returncode"] == 0 and ready["ruff_returncode"] == 0 and
        ready["sources_before"] == ready["sources_after"] == src and
        "passed" in ready["stdout"] and not ready["stderr"].strip(), "genuine current-source checks")
    old = load(REPO / OLD_MANIFEST)
    for name, sha in old["sources"].items():
        require(digest(REPO / name) == sha, "old frozen source changed")
    protection = protected()
    book = budget.ProbeLedger(REPO / LEDGER)
    snapshot = book.snapshot()
    require(Decimal(snapshot["available_for_new_stages_usd"]) >=
        Decimal(spec["full_reservation_usd"]), "whole cohort must fit existing authority")
    # Scan original nonarchive raw calls; duplicated portable archives are excluded.
    new_seeds = {a["request"]["seed"] for a in design.assignments()}
    scanned = 0
    for path in (REPO / "results/paper3").glob("**/calls/*.json"):
        row = load(path)
        seed = row.get("request", {}).get("seed")
        require(seed not in new_seeds, "request seed overlaps prior raw call")
        scanned += 1
    manifest = dict(format=design.VERSION, sources=src, specification=spec,
        readiness_sha256=digest(REPO / READINESS), authority_sha256=digest(REPO / AUTHORITY),
        prior_entries=history(), prior_snapshot=snapshot, protected=protection,
        seed_scan=dict(scope="results/paper3/**/calls/*.json; no archives", files=scanned, overlap=0))
    root.mkdir()
    atomic(root / "manifest.json", manifest)
    return dict(protocol=digest(root / "manifest.json"), logical=spec["logical"],
                full_reservation_usd=spec["full_reservation_usd"], sources=len(src), model_calls=0)


def verify(protocol, full=False):
    root = REPO / ROOT_NAME
    require(digest(root / "manifest.json") == protocol, "external manifest pin")
    m = load(root / "manifest.json")
    for name, sha in m["sources"].items():
        require(digest(REPO / name) == sha, "source/authority changed: " + name)
    require(digest(REPO / READINESS) == m["readiness_sha256"], "readiness changed")
    if full:
        require(sources() == m["sources"], "source closure changed")
        require(canonical(design.specification()) == canonical(m["specification"]), "assignment drift")
        require(protected() == m["protected"], "historical inventory drift")
        for name, sha in m["prior_entries"].items():
            require(digest(REPO / LEDGER / "entries" / name) == sha, "historical charge changed")
    return m


def allocate(protocol, m):
    root = REPO / ROOT_NAME
    stage = "office-probe-" + protocol[:16]
    path = root / "allocation.json"
    book = budget.ProbeLedger(REPO / LEDGER)
    if not path.exists():
        group = REPO / LEDGER / budget.GROUPS / (stage + ".json")
        if group.exists():
            record = load(group)
            require(set(record["stages"]) == {stage} and
                record["stages"][stage]["prior_entries"] == m["prior_entries"] and
                record["cap_usd"] == m["specification"]["full_reservation_usd"], "allocation recovery")
            pins = {stage: digest(REPO / LEDGER / budget.STAGES / (stage + ".json"))}
        else:
            require(history() == m["prior_entries"], "baseline before allocation changed")
            result = book.allocate_group(stage, {stage: m["specification"]["full_reservation_usd"]})
            pins = result["stage_pins"]
        atomic(path, dict(protocol=protocol, stage=stage, stage_pins=pins))
    allocation = load(path)
    require(allocation["protocol"] == protocol and allocation["stage"] == stage and
        set(allocation["stage_pins"]) == {stage}, "pinned new stage")
    book = budget.ProbeLedger(REPO / LEDGER, stage_pins=allocation["stage_pins"])
    with book.locked():
        record = book._stage(stage)
        require(record["prior_entries"] == m["prior_entries"] and
            record["cap_usd"] == m["specification"]["full_reservation_usd"], "stage scope changed")
    return book, stage


def classify(row, assignment):
    return probe_classify(row, assignment["request"], assignment["game"], "vote")


def check_record(path, row, book, stage, *, reconcile=False, assignment=None):
    require(row["status"] == "recorded" and not row.get("instrument_error"), "durable complete physical record")
    entry_path = book.root / "entries" / (stage + "-" + row["id"] + ".json")
    entry = load(entry_path)
    assessed = billing.assess(row, classifier.CONFIG)
    require(row["assessment"] == assessed and
        entry["request_sha256"] == row["request_sha256"] and
        entry["reserved_usd"] == row["reserved_usd"], "physical/financial binding")
    if entry["status"] == "reserved" and reconcile:
        require(assignment is not None and row["request"] == assignment["request"] and
            row["result"] == classify(row, assignment) and
            row["request_text"] == route.reservation(assignment["request"])["request_text"],
            "saved response independently verified before interrupted settlement")
        book.settle(entry["request_id"], assessed["accounted_usd"],
                    assessed["receipt_certified"], digest(path))
        entry = load(entry_path)
    require(entry["status"] == "settled" and entry["evidence_sha256"] == digest(path) and
        entry["accounted_usd"] == assessed["accounted_usd"] and
        entry["certified"] == assessed["receipt_certified"], "exact settlement")
    require(Decimal(entry["accounted_usd"]) <= Decimal(entry["reserved_usd"]), "above-bound cost")
    if not entry["certified"]:
        require(Decimal(entry["accounted_usd"]) >= Decimal(entry["reserved_usd"]), "uncertainty released")


def summary_row(a, row=None, missing=None):
    score = classify(row, a) if row is not None else None
    if score is not None:
        require(score == row["result"], "stored classification changed")
    vote = score["action"]["vote"] if score and score["status"] == "recorded_valid" else None
    return dict(id=a["id"], case=a["case"], condition=a["condition"],
        status=score["status"] if score else missing, vote=vote,
        expected_mandate_or_fact=a["expected_mandate_or_fact"],
        classification=score, outcome=(a["consequences"]["yes" if vote else "no"]
            if vote is not None and a["condition"] != "factual" else None))


def accounting(book, stage):
    rows = book._entries()
    def totals(selected):
        return dict(certified_usd=str(sum((Decimal(r["accounted_usd"]) for r in selected
            if r["status"] == "settled" and r.get("certified") is True), Decimal(0))),
            uncertified_usd=str(sum((Decimal(r["accounted_usd"]) for r in selected
                if r["status"] == "settled" and r.get("certified") is False), Decimal(0))),
            pending_usd=str(sum((Decimal(r["reserved_usd"]) for r in selected
                if r["status"] != "settled"), Decimal(0))), entries=len(selected))
    return dict(study=totals([r for r in rows if r["stage"] == stage]), cumulative=totals(rows))


def live_admission(root, protocol, book, stage, secret):
    with book.locked():
        rows = book._entries()
        unresolved = sum((Decimal(r.get("accounted_usd", r["reserved_usd"])) for r in rows
            if r["status"] != "settled" or r.get("certified") is False), Decimal(0))
        remaining = Decimal(book._stage(stage)["cap_usd"]) - book._total(rows, stage)
    account = funding.observe(secret, remaining + unresolved)
    with diagnostic.opener().open(route.METADATA_URL, timeout=20) as response:
        metadata = json.load(response)
    observed = time.time()
    route.check_endpoint(metadata)
    path = root / "admissions" / (str(time.time_ns()) + ".json")
    atomic(path, dict(protocol=protocol, account=account, metadata=metadata,
                      metadata_observed_unix=observed))
    return observed


def bounded_admission(root, protocol, book, stage, secret):
    """Bounded read-only recovery before the first POST, never paid qualification."""
    for attempt in range(3):
        try:
            return live_admission(root, protocol, book, stage, secret)
        except (TimeoutError, ConnectionResetError, URLError) as exc:
            if isinstance(exc, HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                raise
            atomic(root / "admissions" / ("failure-" + str(time.time_ns()) + ".json"),
                dict(protocol=protocol, error_type=type(exc).__name__, http_status=getattr(exc, "code", None),
                     inference_sent=False, attempt=attempt + 1, observed_unix=time.time()))
            if attempt == 2:
                raise
            time.sleep(30 * (attempt + 1))


def run(protocol, *, secret=None, send=None, lookup=None, admit=None):
    root = REPO / ROOT_NAME
    with (root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        m = verify(protocol, full=True)
        require(not (root / "report.json").exists(), "already terminal; audit only")
        for folder in ("invocations", "admissions", "calls", "outcomes", "missing"):
            (root / folder).mkdir(exist_ok=True)
        starts = sorted((root / "invocations").glob("*-start.json"))
        if starts and (root / "invocations" / starts[-1].name.replace("start", "terminal")).exists():
            require(False, "prior invocation terminal; decision required, no repeat run")
        book, stage = allocate(protocol, m)
        index = len(starts)
        atomic(root / "invocations" / f"{index:04d}-start.json",
               dict(protocol=protocol, pid=os.getpid(), started_unix=time.time()))
        by_id = {a["id"]: a for a in design.assignments()}
        observed = None
        first_send = True
        window = root / "window.json"

        def guard():
            return verify(protocol), protocol

        def perform(request, key, physical_id):
            nonlocal observed
            # Cache recovery/cooldown happens before this first live observer.
            if observed is None:
                if window.exists():
                    require(time.time() < load(window)["deadline_unix"], "finite window expired")
                observed = (admit or bounded_admission)(root, protocol, book, stage, secret)
                if not window.exists():
                    atomic(window, dict(started_unix=observed, deadline_unix=observed + 86400))
                require(0 <= time.time() - observed <= 60, "strict route freshness")
            require(time.time() < load(window)["deadline_unix"], "finite window expired")
            case = dict(id=physical_id, request=request, **route.reservation(request),
                        context=dict(stage="vote", logical_id=key))
            case["request_sha256"] = hashlib.sha256(case["request_text"].encode()).hexdigest()
            calls = billing.Calls(root, book.root, stage, design.MAX_PHYSICAL, guard,
                lambda row, unused: classify(row, by_id[key]), classifier.CONFIG, secret,
                checked_send, lookup or diagnostic.receipt_lookup,
                time.time, time.sleep)
            calls.ledger = book
            with redirect_stdout(io.StringIO()):
                result = calls.one(case)
            require(result["status"] == "recorded", "physical request incomplete; preserve")
            return root / "calls" / (physical_id + ".json")

        def checked_send(wire, token):
            nonlocal first_send
            if first_send:
                require(observed is not None and 0 <= time.time() - observed <= 60,
                        "first POST strict route freshness")
                first_send = False
            return (send or transport.transmit)(wire, token)

        def recover_claim(record, request):
            entry = book.root / "entries" / (stage + "-" + record["physical_id"] + ".json")
            require(not entry.exists(), "uncertain sent request; no blind retry")
            return perform(request, record["logical_id"], record["physical_id"])

        cache = None
        try:
            cache = retry.DurableResponses(root, REPO, protocol=protocol,
                classify=lambda row, req, key: classify(row, by_id[key]), perform=perform,
                check_record=lambda p, r: check_record(p, r, book, stage, reconcile=True,
                    assignment=by_id[r["context"]["logical_id"]]),
                verify=guard, maximum_physical=design.MAX_PHYSICAL,
                maximum_reissues=design.MAX_REISSUES, recover_claim=recover_claim,
                clock=time.time, sleep=time.sleep)
            rows = []
            for a in design.assignments():
                missing = root / "missing" / (a["id"] + ".json")
                if missing.exists():
                    require(load(missing)["reason"] == "per_action_retry_limit", "local missingness scope")
                    result = summary_row(a, missing="retry_exhausted")
                else:
                    try:
                        row = cache.respond(a["request"], a["id"])
                        result = summary_row(a, row)
                    except durable.Paused as exc:
                        if exc.reason != "per_action_retry_limit":
                            raise
                        atomic(missing, dict(reason=exc.reason, protocol=protocol))
                        result = summary_row(a, missing="retry_exhausted")
                target = root / "outcomes" / (a["id"] + ".json")
                if target.exists():
                    require(canonical(load(target)) == canonical(result), "saved outcome changed")
                else:
                    atomic(target, result)
                rows.append(result)
                print(json.dumps(dict(event="logical_terminal", completed=len(rows),
                    assigned=len(by_id), id=a["id"], status=result["status"])), flush=True)
            report = design.readout(rows)
            report.update(protocol=protocol, accounting=accounting(book, stage), ledger_hashes=history())
            atomic(root / "report.json", report)
            terminal = dict(status="complete", completed_unix=time.time(), report_sha256=digest(root / "report.json"))
        except (durable.Paused, Exception) as exc:
            terminal = dict(status="paused", reason=exc.reason if isinstance(exc, durable.Paused)
                else type(exc).__name__ + ":" + str(exc), completed_unix=time.time())
        finally:
            if cache is not None:
                cache.close()
        atomic(root / "invocations" / f"{index:04d}-terminal.json", terminal)
        return terminal


def audit(protocol):
    m = verify(protocol, full=True)
    root = REPO / ROOT_NAME
    allocation = load(root / "allocation.json")
    book = budget.ProbeLedger(REPO / LEDGER, stage_pins=allocation["stage_pins"])
    stage = allocation["stage"]
    require(stage == "office-probe-" + protocol[:16] and allocation["protocol"] == protocol,
            "audit allocation binding")
    with book.locked():
        require(book._stage(stage)["cap_usd"] == m["specification"]["full_reservation_usd"], "cap")
    window = load(root / "window.json")
    require(window["deadline_unix"] - window["started_unix"] == 86400, "finite window")
    rows, physicals, total_reissues, all_raw = [], set(), 0, []
    for a in design.assignments():
        attempts = [load(p) for p in sorted((root / "attempts").glob(a["id"] + "-a*.json"))]
        require(1 <= len(attempts) <= 4, "bounded attempts for every assignment")
        prior = None
        accepted = None
        for n, claim in enumerate(attempts, 1):
            physical = a["id"] + f"-a{n}"
            wire = route.reservation(a["request"])["request_text"]
            require(claim["logical_id"] == a["id"] and claim["physical_id"] == physical and
                claim["attempt"] == n and claim["protocol"] == protocol and
                claim["request_sha256"] == hashlib.sha256(wire.encode()).hexdigest(), "claim/request/seed")
            path = root / "calls" / (physical + ".json")
            ref = dict(path=path.relative_to(REPO).as_posix(), sha256=digest(path))
            require(claim["evidence"] == ref, "raw reference")
            row = load(path)
            require(row["id"] == physical and row["protocol"] == protocol and row["request_text"] == wire and
                row["request"] == a["request"], "raw request identity")
            check_record(path, row, book, stage)
            require(window["started_unix"] <= row["admitted_unix"] < window["deadline_unix"] and
                row["admitted_unix"] <= row["ended_unix"], "physical time window")
            if prior:
                eligible = retry.eligibility(prior)
                require(eligible["eligible"] and row["admitted_unix"] >= prior["ended_unix"] +
                    max(durable.COOLDOWNS[n-2], eligible["delay"] or 0), "retry eligibility/cooldown")
            score = classify(row, a)
            require(score == row["result"], "classification equality")
            if score["status"] in ("recorded_valid", "content_failed", "resource_failed"):
                require(n == len(attempts) and load(root / "accepted" / (a["id"] + ".json")) == ref,
                        "never replace accepted/invalid complete answer")
                accepted = row
            else:
                require(retry.eligibility(row)["eligible"], "known failed attempt only")
            prior = row
            all_raw.append(row)
            physicals.add(physical)
            total_reissues += n > 1
        if accepted is None:
            require(len(attempts) == 4 and load(root / "missing" / (a["id"] + ".json")) ==
                dict(reason="per_action_retry_limit", protocol=protocol), "exhausted local failure")
        result = summary_row(a, accepted, "retry_exhausted")
        require(canonical(load(root / "outcomes" / (a["id"] + ".json"))) == canonical(result), "saved outcome")
        rows.append(result)
    require(physicals == {p.stem for p in (root / "calls").glob("*.json")} ==
        {p.stem for p in (root / "attempts").glob("*.json")}, "entire physical inventory")
    require(len(physicals) <= design.MAX_PHYSICAL and total_reissues <= design.MAX_REISSUES, "physical caps")
    admissions = [load(p) for p in (root / "admissions").glob("*.json")
                  if not p.name.startswith("failure-")]
    require(admissions and min(a["metadata_observed_unix"] for a in admissions) ==
            window["started_unix"], "initial finite admission window")
    for admission in admissions:
        require(admission["protocol"] == protocol and admission["account"]["account_funded"] is True
            and admission["account"]["research_authority_extended"] is False, "funded same authority")
        route.check_endpoint(admission["metadata"])
        observed = admission["metadata_observed_unix"]
        first = min((r for r in all_raw if r["admitted_unix"] >= observed),
                    key=lambda r: r["admitted_unix"])
        require(0 <= first["admitted_unix"] - observed <= 60 and
            0 <= first["stream"]["started_unix"] - observed <= 60, "actual first POST freshness")
    entries = [r for r in book._entries() if r["stage"] == stage]
    require({r["request_id"] for r in entries} == {stage + "-" + p for p in physicals}, "every charge covered")
    report = design.readout(rows)
    report.update(protocol=protocol, accounting=accounting(book, stage), ledger_hashes=history())
    require(canonical(load(root / "report.json")) == canonical(report), "ENTIRE report differs")
    return dict(entire_report_matched=True, entire_ledger_matched=True, logical=len(rows),
                physical=len(physicals), report_sha256=digest(root / "report.json"), accounting=report["accounting"])


def deny_live():
    def hook(event, args):
        if event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn")) or event in ("os.system", "os.fork", "os.posix_spawn"):
            raise RuntimeError("offline audit denied " + event)
    sys.addaudithook(hook)
    for event in ("socket.connect", "subprocess.Popen"):
        try:
            sys.audit(event, None)
        except RuntimeError:
            pass
        else:
            raise AssertionError("guard selftest failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("prepare", "run", "audit"):
        modes.add_argument("--" + mode, action="store_true")
    parser.add_argument("--expected-protocol")
    args = parser.parse_args()
    if args.prepare:
        require(args.expected_protocol is None, "prepare computes the pin")
        result = prepare()
    else:
        require(args.expected_protocol is not None, "external protocol required")
        if args.audit:
            deny_live()
            result = audit(args.expected_protocol)
        else:
            result = run(args.expected_protocol, secret=read_secret(REPO))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
