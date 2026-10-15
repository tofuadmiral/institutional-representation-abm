"""Unfrozen request bridge: explicit transport, no allocation/launch on import.

Only fabricated hooks may be used before a new approved runner/protocol exists.
This preserves the qualified native/billing service and supplies the separately
tested $12 ledger. Safe content failures stay local; unsafe failures stop this
serial block. Reissues need prospective authority and an explicit frozen ceiling.
"""
from copy import deepcopy
import fcntl
import math
from pathlib import Path
from threading import Event, Lock, RLock
import time

from experiments import paper3_transport_diagnostic as t
from paper3 import retrospective_billing_calls as service
from paper3 import retrospective_contract_recovery as recovery
from paper3 import retrospective_extended_budget as extended
from paper3 import retrospective_independent_execution as execution
from paper3.pivot_b_budget import atomic, identifier


def eligibility(row, attempt, used, ceiling):
    t.require(type(ceiling) is int and 0 <= ceiling <= recovery.MAX_REISSUES,
              "explicit bounded reissue policy")
    result = recovery.eligibility(row, logical_attempt=attempt, recoveries_used=used)
    if used >= ceiling:
        result.update(eligible=False, reason="prospective_block_reissue_ceiling")
    return result


def physical(case, attempt):
    t.require(type(attempt) is int and attempt in (1, 2), "two physical slots")
    t.require(not {"logical_id", "logical_attempt"} & set(case["context"]), "reserved context keys")
    return dict(**{k: deepcopy(v) for k, v in case.items() if k not in ("id", "context")},
        id=case["id"] + f"-a{attempt}", context=dict(**case["context"],
        logical_id=case["id"], logical_attempt=attempt))


def normalized(row, path, logical_id):
    """Reference the immutable physical record; never overwrite/rename it."""
    return dict(**{k: deepcopy(v) for k, v in row.items() if k != "id"},
        id=logical_id, physical_reference=dict(id=row["id"], sha256=t.sha(Path(path).read_bytes())))


class Calls:
    def __init__(self, root, ledger, stage, verify, classify, *, send, lookup,
                 maximum_logical, maximum_reissues, secret=None, clock=time.time, sleep=time.sleep):
        t.require(isinstance(ledger, extended.ExtendedLedger), "prospective extended ledger required")
        t.require(all(callable(f) for f in (verify, classify, send, lookup, clock, sleep)),
                  "explicit verification classification and transport hooks required")
        t.require(type(maximum_logical) is int and 0 < maximum_logical <= 480,
                  "bounded frozen logical inventory")
        eligibility({}, 1, 0, maximum_reissues)
        identifier(stage)
        self.root, self.ledger, self.stage = Path(root), ledger, stage
        self.verify, self.classify, self.send, self.lookup = verify, classify, send, lookup
        self.secret, self.clock, self.sleep = secret, clock, sleep
        self.maximum_logical, self.maximum_reissues = maximum_logical, maximum_reissues
        self.maximum_physical = maximum_logical + maximum_reissues
        self.guard, self.stop, self.serial = RLock(), Event(), Lock()
        self.recoveries, self.cooldown_until = 0, 0
        self.protocol = verify()[1]
        # Caller must have allocated the whole cap and scoped this fresh stage.
        with ledger.locked():
            ledger._stage(stage)
        self.root.mkdir(parents=True, exist_ok=True)
        self.writer = (self.root / "transport_writer.lock").open("a")
        try:
            fcntl.flock(self.writer, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for name in ("calls", "attempts", "logicals", "recoveries", "sessions"):
                (self.root / name).mkdir(exist_ok=True)
            t.require(not (self.root / "sessions/transport_start.json").exists() and
                all(not list((self.root / n).iterdir()) for n in
                    ("calls", "attempts", "logicals", "recoveries")),
                "fresh transport only; never restart")
            atomic(self.root / "sessions/transport_start.json", dict(protocol=self.protocol,
                stage=stage, stage_pins=ledger.stage_pins(), maximum_logical=maximum_logical,
                maximum_physical=self.maximum_physical, maximum_reissues=maximum_reissues,
                workers=1, delay_seconds=recovery.DELAY_SECONDS, started_unix=clock()))
        except Exception:
            self.writer.close()
            raise

    def close(self):
        """Release only the writer lock; no financial or scientific closure."""
        self.writer.close()

    def halt(self, key, reason):
        self.stop.set()
        with self.guard:
            path = self.root / "sessions/transport_stop.json"
            if not path.exists():
                atomic(path, dict(protocol=self.protocol, id=key, reason=reason,
                                  detected_unix=self.clock()))

    def admission_verify(self):
        while self.clock() < self.cooldown_until and not self.stop.is_set():
            self.sleep(min(1, self.cooldown_until - self.clock()))
        t.require(not self.stop.is_set(), "global transport stop")
        value = self.verify()
        t.require(value[1] == self.protocol, "source/protocol changed")
        return value

    def execution_score(self, row, case):
        verdict = self.classify(row, case)
        t.require(verdict["status"] in ("recorded_valid", "content_failed", "unsafe_failed"),
                  "known scientific disposition")
        if verdict["status"] == "recorded_valid":
            t.require(verdict["instrument_safe"] is True and verdict["action"] is not None,
                      "safe executed action")
            return verdict
        if verdict["status"] == "content_failed":
            t.require(verdict["instrument_safe"] is True and verdict["action"] is None,
                      "safe content failure, no inferred decision")
            return verdict  # Never halt or regenerate a known complete bad action.
        proposal = eligibility(row, case["context"]["logical_attempt"],
                               self.recoveries, self.maximum_reissues)
        if proposal["eligible"] and not self.stop.is_set():
            self.recoveries += 1
            detected = self.clock()
            self.cooldown_until = max(self.cooldown_until, detected + recovery.DELAY_SECONDS)
            atomic(self.root / "recoveries" / (case["id"] + ".json"), dict(
                protocol=self.protocol, id=case["id"], logical_id=case["context"]["logical_id"],
                ordinal=self.recoveries, eligibility=proposal, detected_unix=detected,
                not_before_unix=self.cooldown_until, request_sha256=case["request_sha256"]))
        else:
            self.halt(case["id"], "unsafe_or_exhausted_reissue")
        return verdict

    def one(self, case):
        if not self.serial.acquire(blocking=False):
            self.halt(case["id"], "concurrent_logical_request")
            raise ValueError("one worker only")
        try:
            return self._one(case)
        except Exception:
            self.halt(case["id"], "coordinator_exception")
            raise
        finally:
            self.serial.release()

    def _one(self, case):
        identifier(case["id"])
        logical_path = self.root / "logicals" / (case["id"] + ".json")
        t.require(not logical_path.exists(), "logical action already attempted")
        t.require(len(list((self.root / "logicals").glob("*.json"))) < self.maximum_logical,
                  "logical inventory ceiling")
        record = dict(protocol=self.protocol, case=deepcopy(case),
            attempt_slots=[case["id"] + "-a1", case["id"] + "-a2"], attempts=[],
            status="prepared", selected_id=None, returned_evidence=None)
        if self.stop.is_set():
            record["status"] = "not_started"
            atomic(logical_path, record)
            return dict(id=case["id"], status="not_started", instrument_error="global_stop")
        atomic(logical_path, record)
        for attempt in (1, 2):
            request = physical(case, attempt)
            path = self.root / "attempts" / (request["id"] + ".json")
            t.require(not path.exists(), "physical slot already attempted")
            atomic(path, dict(case=request, result=dict(id=request["id"], status="prepared")))
            native = service.Calls(self.root, self.ledger.root, self.stage, self.maximum_physical,
                self.admission_verify, self.execution_score, execution.CONFIG, self.secret,
                self.send, self.lookup, self.clock, self.sleep)
            native.ledger, native.guard, native.stop = self.ledger, self.guard, self.stop
            status = native.one(request)
            atomic(path, dict(case=request, result=status))
            record["attempts"].append(status)
            raw_path = self.root / "calls" / (request["id"] + ".json")
            if raw_path.exists():
                row = t.load(raw_path)
                record["returned_evidence"] = normalized(row, raw_path, case["id"])
                result = row.get("result", {})
                if status["status"] == "recorded" and result.get("status") in ("recorded_valid", "content_failed"):
                    self.admission_verify()  # Integrity barrier after spending/settlement.
                    record.update(status=result["status"], selected_id=request["id"])
                    break
            if (attempt == 1 and not self.stop.is_set() and
                    (self.root / "recoveries" / (request["id"] + ".json")).exists()):
                atomic(logical_path, record)
                self.admission_verify()  # Shared cooldown, identical original request.
                continue
            self.halt(request["id"], "physical_or_scientific_failure")
            record["status"] = "unsafe_failed"
            break
        if record["returned_evidence"] is None:
            record["returned_evidence"] = dict(id=case["id"], status="instrument_error",
                                              instrument_error="no_complete_physical_record")
        atomic(logical_path, record)
        return deepcopy(record["returned_evidence"])


def audit(root, ledger_root, stage, protocol, classify, maximum_logical, maximum_reissues):
    """Read-only physical and logical closure, cost, retry and exact-wire audit."""
    root, ledger_root = Path(root), Path(ledger_root)
    start = t.load(root / "sessions/transport_start.json")
    eligibility({}, 1, 0, maximum_reissues)
    t.require(type(maximum_logical) is int and 0 < maximum_logical <= 480,
              "bounded logical inventory")
    t.require(type(start["workers"]) is int and type(start["maximum_logical"]) is int and
              type(start["maximum_reissues"]) is int and type(start["maximum_physical"]) is int,
              "typed transport declaration")
    t.require(start["protocol"] == protocol and start["stage"] == stage and start["workers"] == 1 and
        start["maximum_logical"] == maximum_logical and start["maximum_reissues"] == maximum_reissues and
        start["maximum_physical"] == maximum_logical + maximum_reissues and
        start["delay_seconds"] == recovery.DELAY_SECONDS, "transport declaration changed")
    ledger = extended.ExtendedLedger(ledger_root, stage_pins=start["stage_pins"])
    with ledger.locked():
        ledger._stage(stage)
    def inventory(directory, key):
        paths = sorted((root / directory).glob("*.json"))
        rows = [t.load(p) for p in paths]
        for path, row in zip(paths, rows, strict=True):
            identifier(key(row))
            t.require(path.name == key(row) + ".json", "record filename changed")
        t.require(len({key(r) for r in rows}) == len(rows), "record identities changed")
        return rows
    logicals = inventory("logicals", lambda r: r["case"]["id"])
    attempts = inventory("attempts", lambda r: r["case"]["id"])
    t.require(len(logicals) <= maximum_logical and len(attempts) <= maximum_logical + maximum_reissues,
              "physical/logical inventory ceiling")
    reports, cost = service.audit_records(root, ledger_root, stage, protocol,
        [r["case"] for r in attempts], dict(results=[r["result"] for r in attempts]),
        classify, execution.CONFIG)
    by_attempt = {r["case"]["id"]: r for r in attempts}
    stop_path = root / "sessions/transport_stop.json"
    if stop_path.exists():
        stop = t.load(stop_path)
        t.require(stop["protocol"] == protocol and type(stop["detected_unix"]) in (int, float)
            and math.isfinite(stop["detected_unix"]) and stop["detected_unix"] >= start["started_unix"],
            "stop provenance changed")
        t.require(all(t.load(p)["admitted_unix"] <= stop["detected_unix"]
            for p in (root / "calls").glob("*.json")), "admission after global stop")
    events = sorted(inventory("recoveries", lambda r: r["id"]), key=lambda r: r["ordinal"])
    t.require([e["ordinal"] for e in events] == list(range(1, len(events) + 1)) and
              len(events) <= maximum_reissues, "reissue inventory")
    cooldown, last_detection = 0, start["started_unix"]
    for event in events:
        row = t.load(root / "calls" / (event["id"] + ".json"))
        expected = eligibility(row, by_attempt[event["id"]]["case"]["context"]["logical_attempt"],
                               event["ordinal"] - 1, maximum_reissues)
        t.require(expected["eligible"] and event["eligibility"] == expected and
            event["protocol"] == protocol and event["request_sha256"] == row["request_sha256"] and
            event["logical_id"] == row["context"]["logical_id"] and
            event["detected_unix"] >= last_detection and
            event["detected_unix"] >= row["ended_unix"] and
            event["not_before_unix"] == max(cooldown, event["detected_unix"] + recovery.DELAY_SECONDS),
            "reissue evidence or timing changed")
        cooldown = event["not_before_unix"]
        last_detection = event["detected_unix"]
        for p in (root / "calls").glob("*.json"):
            admitted = t.load(p)["admitted_unix"]
            t.require(not event["detected_unix"] < admitted < event["not_before_unix"],
                      "admission during cooldown")
    matched, referenced_events = set(), set()
    for logical in logicals:
        case = logical["case"]
        t.require(logical["protocol"] == protocol and logical["attempt_slots"] ==
            [case["id"] + "-a1", case["id"] + "-a2"] and len(logical["attempts"]) <= 2,
            "logical declaration changed")
        for index, status in enumerate(logical["attempts"], 1):
            expected = physical(case, index)
            t.require(by_attempt[expected["id"]] == dict(case=expected, result=status),
                      "physical request/status changed")
            matched.add(expected["id"])
            if index == 2:
                event = t.load(root / "recoveries" / (case["id"] + "-a1.json"))
                row_path = root / "calls" / (expected["id"] + ".json")
                if row_path.exists():
                    t.require(t.load(row_path)["admitted_unix"] >= event["not_before_unix"],
                              "premature reissue")
        selected = logical["selected_id"]
        t.require(logical["status"] in ("recorded_valid", "content_failed", "unsafe_failed", "not_started"),
                  "unfinished logical record; interruption is not terminal closure")
        if selected is not None:
            t.require(selected == logical["attempts"][-1]["id"], "selected an earlier answer")
            p = root / "calls" / (selected + ".json")
            row = t.load(p)
            t.require(logical["returned_evidence"] == normalized(row, p, case["id"]) and
                logical["status"] == row["result"]["status"] in ("recorded_valid", "content_failed"),
                "selected evidence/action changed")
            t.require(logical["attempts"][-1]["status"] == "recorded", "selected incomplete physical row")
        else:
            t.require(logical["status"] in ("unsafe_failed", "not_started"), "missing selected answer")
            if logical["status"] == "not_started":
                t.require(not logical["attempts"] and logical["returned_evidence"] is None,
                          "unstarted logical has physical evidence")
                t.require(stop_path.exists(), "unstarted transport without stop")
            else:
                t.require(bool(logical["attempts"]) and
                    (root / "sessions/transport_stop.json").exists(), "unsafe failure without stop")
                p = root / "calls" / (logical["attempts"][-1]["id"] + ".json")
                expected = normalized(t.load(p), p, case["id"]) if p.exists() else dict(
                    id=case["id"], status="instrument_error", instrument_error="no_complete_physical_record")
                t.require(logical["returned_evidence"] == expected, "failed evidence changed")
        for status in logical["attempts"]:
            if (root / "recoveries" / (status["id"] + ".json")).exists():
                referenced_events.add(status["id"])
    t.require(matched == set(by_attempt), "unmatched physical attempt")
    t.require(referenced_events == {e["id"] for e in events}, "unmatched recovery evidence")
    return dict(protocol=protocol, logicals=logicals, physical_reports=reports,
                accounted_usd=str(cost), reissues=len(events), allocation_authorized=False,
                publication_evidence=False)
