"""Append-only billing recovery of the same frozen graceful continuation."""

# ruff: noqa: E402
import argparse
from decimal import Decimal
import fcntl
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

from experiments import paper3_graceful_continuation as old
from paper3 import retrospective_receipt_recovery_v1 as billing

ROOT = REPO / old.ROOT_NAME
META = ROOT / "billing_amendment_v1"
OLD_PROTOCOL = "ad3ccdb2d3be68922cffeea6d5ed0de2c160b7299fdeeb0c9a5422692abdb964"
FAILED = "overload-r2-1-conflict-binding_sum-18-a1"
FAILED_SHA = "d3d4916921ded5d22789734bbba651b8b2f67276033590bb6270a5ec5fb54867"
AUTHORITY = "results/paper3/billing_recovery_authorization_2026_10_26.json"
READINESS = "results/paper3/billing_recovery_readiness_2026_10_26.json"
TESTS = [".venv/bin/python", "-B", "-m", "pytest",
         "tests/test_paper3_billing_recovery_v1.py",
         "tests/test_paper3_graceful_recovery.py", "-q", "--tb=short", "-x"]
require, load, digest, atomic = old.require, old.load, old.digest, old.atomic


def inventory():
    m, _ = old.verify(ROOT, OLD_PROTOCOL)
    paths = [REPO / p for p in m["sources"]]
    paths += [Path(__file__), REPO / "paper3/retrospective_receipt_recovery_v1.py",
              REPO / AUTHORITY, REPO / "tests/test_paper3_billing_recovery_v1.py"]
    return {p.relative_to(REPO).as_posix(): digest(p)
            for p in old.closure(REPO, paths)}


def original_files():
    return {p.relative_to(REPO).as_posix(): digest(p) for p in ROOT.rglob("*.json")
            if not p.is_relative_to(META)}


def prepare():
    with (ROOT / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not META.exists(), "amendment prepare once only")
        old.verify(ROOT, OLD_PROTOCOL)
        require(not (ROOT / "report.json").exists(), "already complete")
        terminal = load(ROOT / "invocations/0000-terminal.json")
        require(terminal["status"] == "paused"
                and terminal["reason"] == "nonretryable_instrument_failure",
                "expected documented billing pause")
        require(digest(ROOT / "block-1/calls" / (FAILED + ".json")) == FAILED_SHA,
                "saved complete response changed")
        ready = load(REPO / READINESS)
        sources = inventory()
        require(ready["argv"] == TESTS and ready["returncode"] == 0
                and not ready["stderr"].strip()
                and ready["sources_before"] == ready["sources_after"] == sources,
                "genuine current-source whole-file checks required")
        authority = load(REPO / AUTHORITY)
        require(authority["human_reply"] == "yes continue"
                and authority["total_cumulative_cap_usd"] == "19.30"
                and not authority["changed_science_cases_seeds_model_provider_parameters"],
                "exact billing-only authority")
        pins = load(ROOT / "allocation.json")
        old.validate_pins(pins, load(ROOT / "manifest.json"), OLD_PROTOCOL)
        book = old.ledger(pins["stage_pins"])
        snapshot = book.snapshot()
        entries = {p.name: digest(p) for p in (REPO / old.LEDGER / "entries").glob("*.json")}
        m = dict(version=billing.VERSION, old_protocol=OLD_PROTOCOL, sources=sources,
                 readiness_sha256=digest(REPO / READINESS),
                 prior_files=original_files(), prior_entries=entries,
                 authority_sha256=digest(REPO / AUTHORITY), budget=snapshot,
                 saved_response=FAILED, saved_response_sha256=FAILED_SHA,
                 disclosure="Billing-only technical continuation after failure; historical verdict/cost unchanged. Not independent validation.")
        protocol = hashlib.sha256(old.journal.canonical(m).encode()).hexdigest()
        META.mkdir()
        atomic(META / "manifest.json", m)
        return dict(amendment_protocol=protocol, legacy_protocol=OLD_PROTOCOL,
                    sources=len(sources), historical_entries=len(entries), new_model_calls=0)


def verify(protocol, *, full=False):
    m = load(META / "manifest.json")
    require(hashlib.sha256(old.journal.canonical(m).encode()).hexdigest() == protocol,
            "external amendment pin differs")
    require(m["authority_sha256"] == digest(REPO / AUTHORITY)
            and m["readiness_sha256"] == digest(REPO / READINESS), "authority/readiness changed")
    for name, sha in m["sources"].items():
        require(digest(REPO / name) == sha, "frozen source changed: " + name)
    if full:
        for name, sha in m["prior_files"].items():
            require(digest(REPO / name) == sha, "historical evidence changed: " + name)
        for name, sha in m["prior_entries"].items():
            require(digest(REPO / old.LEDGER / "entries" / name) == sha,
                    "historical expense changed")
    return m


def key_classify(row, request, key):
    assignment = next(a for a in old.items() if key.startswith(a["id"] + "-"))
    stage = json.loads(request["messages"][1]["content"])["stage"]
    return billing.classify(row, request, assignment["game"], stage)


def make_view(row, supplement):
    view = billing.recovered_view(row, supplement)
    view["result"] = key_classify(view, view["request"], view["context"]["logical_id"])
    return view


def recover(protocol, *, lookup=None, secret=None, clock=time.time, sleep=time.sleep):
    """GET only; at most the three unconsumed slots of the saved generation."""
    with (ROOT / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify(protocol, full=True)
        original_path = ROOT / "block-1/calls" / (FAILED + ".json")
        row = load(original_path)
        require(digest(original_path) == FAILED_SHA, "saved response changed")
        original_assessment = old.native.assess(row, old.failure.previous.CONFIG)
        require(original_assessment == row["assessment"]
                and original_assessment["stream"]["complete"]
                and original_assessment["reasons"] == ["receipt:unavailable, invalid or conflicting"]
                and len(row["receipts"]) == 1 and billing.temporary(row["receipts"][0]),
                "billing-only recovery of complete saved answer")
        path = META / "recovered.json"
        if path.exists():
            supplement = load(path)
            view = make_view(row, supplement)
            require(view["result"] == supplement["result"], "saved recovery differs")
            require(view["result"]["status"] in ("recorded_valid", "content_failed", "resource_failed"),
                    "billing recovery not complete")
            return dict(status="recovered", model_calls=0, result=view["result"]["status"])
        receipts = META / "receipt_observations"
        receipts.mkdir(exist_ok=True)
        observations = []
        lookup = lookup or old.diagnostic.receipt_lookup
        summary = original_assessment["stream"]
        for offset in billing.OFFSETS[1:]:
            p = receipts / (str(offset) + ".json")
            if p.exists():
                observation = load(p)
            else:
                # Receipt GET is read-only and may be resumed after an uncertain
                # GET; there is deliberately no inference transmit function here.
                sleep(max(0, row["stream"]["ended_unix"] + offset - clock()))
                observation = lookup(summary["generation_id"], secret)
                observation, hit = old.diagnostic.redact(observation, secret)
                observation["secret_redacted"] = hit or observation.get("secret_redacted", False)
                observation["scheduled_offset_seconds"] = offset
                atomic(p, observation)
            observations.append(observation)
            supplement = dict(amendment_protocol=protocol,
                original=dict(path=original_path.relative_to(REPO).as_posix(), sha256=FAILED_SHA),
                observations=observations, recovered_unix=clock(), full_historical_charge_retained=True)
            view = make_view(row, supplement)
            if view["assessment"]["passed"]:
                supplement["result"] = view["result"]
                atomic(path, supplement)
                require(view["result"]["status"] in ("recorded_valid", "content_failed", "resource_failed"),
                        "saved answer has an independent instrument failure; preserve and pause")
                return dict(status="recovered", model_calls=0,
                            result=view["result"]["status"], new_receipt_GETs=len(observations),
                            old_full_reservation_retained=row["reserved_usd"])
            require(billing.benign(observation), "nonretryable/conflicting receipt; preserve and pause")
        raise ValueError("receipt recovery did not validate")


def drivers(protocol):
    """Explicitly bind only billing/provenance dependencies of the frozen driver."""
    amendment = verify(protocol)
    historic = set(amendment["prior_files"])
    pins = load(ROOT / "allocation.json")
    old_manifest = load(ROOT / "manifest.json")

    def guard(root, legacy):
        require(Path(root) == ROOT and legacy == OLD_PROTOCOL, "same experiment only")
        verify(protocol)
        return old.verify(root, legacy)

    def view(row):
        if (row.get("id") == FAILED and
                (ROOT / "block-1/calls" / (FAILED + ".json")).relative_to(REPO).as_posix() in historic):
            supplement = load(META / "recovered.json")
            require(supplement["amendment_protocol"] == protocol
                    and supplement["original"]["sha256"] == FAILED_SHA,
                    "recovery authority/original pin differs")
            result = make_view(row, supplement)
            require(result["result"] == supplement["result"], "recovery result changed")
            return result
        return row

    new_check = billing.bind(old.check_record,
        native=SimpleNamespace(assess=billing.assess), classify=key_classify)

    def check(path, row, m, financial, *, reconcile=False):
        relative = Path(path).relative_to(REPO).as_posix()
        if relative in historic:
            require(digest(path) == amendment["prior_files"][relative], "historical raw changed")
            raw = load(path)
            old.check_record(path, raw, m, financial)
            require(row == raw or row == view(raw), "unbound derived response")
        else:
            new_check(path, row, m, financial, reconcile=reconcile)

    class Cache(old.recovery.DurableResponses):
        def read(self, ref):
            return view(super().read(ref))

    def checked_load(path):
        path = Path(path)
        if path == ROOT / "block-1/admission.json":
            return load(META / "remaining_frame_admission.json")
        value = load(path)
        return view(value) if path == ROOT / "block-1/calls" / (FAILED + ".json") else value

    def readout(reports):
        result = old.readout(reports)
        result["billing_amendment"] = dict(protocol=protocol,
            original_paused_response_preserved=True, historical_charge_retained=True,
            disclosure=amendment["disclosure"])
        return result

    shared = dict(verify=guard, classify=key_classify, check_record=check,
                  execution=SimpleNamespace(execute=billing.execute), readout=readout,
                  load=checked_load)
    run = billing.bind(old.run, **shared, native=SimpleNamespace(Calls=billing.Calls),
        recovery=SimpleNamespace(DurableResponses=Cache, Paused=old.recovery.Paused))
    audit = billing.bind(old.audit, **shared)
    return run, audit, old_manifest, pins


def run(protocol, *, secret):
    verify(protocol, full=True)
    require((META / "recovered.json").exists(), "recover saved receipt before inference")
    if not (META / "remaining_frame_admission.json").exists():
        atomic(META / "remaining_frame_admission.json", dict(
            started_unix=time.time(), deadline_unix=time.time() + 86400,
            reason="26 October approved billing-only continuation; old deadline unchanged"))
    driver, _, _, pins = drivers(protocol)

    def admission(unused):
        verify(protocol, full=True)
        book = old.ledger(pins["stage_pins"])
        with book.locked():
            rows = book._entries()
            unresolved = sum((Decimal(e.get("accounted_usd", e["reserved_usd"]))
                for e in rows if e["status"] != "settled" or e.get("certified") is False), Decimal(0))
            stage = pins["stages"][1]
            remaining = Decimal(book._stage(stage)["cap_usd"]) - book._total(rows, stage)
        account = old.funding.observe(secret, remaining + unresolved)
        with old.diagnostic.opener().open(old.route.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
        old.route.check_endpoint(metadata)
        atomic(META / ("admission-" + str(time.time_ns()) + ".json"),
               dict(account=account, metadata=metadata, amendment_protocol=protocol))

    return driver(ROOT, OLD_PROTOCOL, secret=secret, admission=admission)


def audit(protocol):
    verify(protocol, full=True)
    _, driver, _, _ = drivers(protocol)
    result = driver(ROOT, OLD_PROTOCOL)
    result["amendment_protocol"] = protocol
    result["saved_response_model_reissued"] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("prepare", "recover", "run", "audit"):
        modes.add_argument("--" + mode, action="store_true")
    parser.add_argument("--expected-protocol")
    args = parser.parse_args()
    if args.prepare:
        require(args.expected_protocol is None, "new amendment has no prior pin")
        result = prepare()
    else:
        require(args.expected_protocol is not None, "external amendment pin required")
        if args.audit:
            result = audit(args.expected_protocol)
        else:
            secret = old.original_runner.read_secret(REPO)
            result = (recover(args.expected_protocol, secret=secret) if args.recover
                      else run(args.expected_protocol, secret=secret))
    print(json.dumps(result, default=str), flush=True)


if __name__ == "__main__":
    main()
