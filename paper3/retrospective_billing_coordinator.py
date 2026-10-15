"""Unfrozen successor transport coordinator; no experiment/launch authority.

Explicit transport functions are required. A future approved runner must pin
cases, source closure, qualification replay, metadata, stage/total authority
and this coordinator before calling it. Never attach it to a closed run.
"""
from pathlib import Path
from threading import Event, RLock
import time

from experiments import paper3_transport_diagnostic as t
from paper3 import retrospective_billing_calls as service
from paper3 import retrospective_contract_recovery as recovery
from paper3.pivot_b_budget import atomic
from paper3.retrospective_serial_execution import StopLedger, STOP

MAX_LOGICAL = 240
MAX_PHYSICAL = 265


def valid(result):
    return all(result.get(k) is True for k in ("usable", "valid_action", "exact"))


def physical(case, attempt):
    t.require(type(attempt) is int and attempt in (1, 2), "two physical slots")
    t.require(not {"logical_id", "logical_attempt"} & set(case["context"]),
              "ambiguous logical context")
    return dict(**{k: v for k, v in case.items() if k not in ("id", "context")},
        id=case["id"] + f"-a{attempt}", context=dict(**case["context"],
        logical_id=case["id"], logical_attempt=attempt))


class Calls:
    def __init__(self, root, ledger_root, stage, verify, score, *, send, lookup,
                 secret=None, clock=time.time, sleep=time.sleep):
        self.root, self.stage = Path(root), stage
        self.verify, self.score, self.clock, self.sleep = verify, score, clock, sleep
        self.send, self.lookup, self.secret = send, lookup, secret
        self.ledger = StopLedger(ledger_root)
        self.guard, self.stop = RLock(), Event()
        self.recoveries, self.cooldown_until = 0, 0
        self.protocol = verify()[1]
        for name in ("calls", "attempts", "logicals", "recoveries", "sessions"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        t.require(not (self.root / "sessions/transport_start.json").exists() and
            all(not list((self.root / n).glob("*")) for n in
                ("calls", "attempts", "logicals", "recoveries")), "fresh transport only; no restart")
        atomic(self.root / "sessions/transport_start.json", dict(protocol=self.protocol,
            stage=stage, maximum_logical=MAX_LOGICAL, maximum_physical=MAX_PHYSICAL,
            maximum_reissues=recovery.MAX_REISSUES, delay_seconds=recovery.DELAY_SECONDS,
            started_unix=clock()))

    def halt(self, call_id, reason):
        # Set immediately, before waiting for a coordinator/admission lock.
        self.stop.set()
        detected = self.clock()
        with self.guard:
            path = self.root / "sessions/transport_stop.json"
            if not path.exists():
                atomic(path, dict(protocol=self.protocol, id=call_id, reason=reason,
                                  detected_unix=detected, admission_barrier_unix=self.clock()))

    def admission_verify(self):
        # The native service invokes this under the shared RLock immediately
        # before reserve/admission. Cooldown cannot race a different worker.
        while self.clock() < self.cooldown_until and not self.stop.is_set():
            self.sleep(min(1, self.cooldown_until - self.clock()))
        t.require(not self.stop.is_set(), "global transport stop")
        return self.verify()

    def execution_score(self, row, case):
        result = self.score(row, case)
        if valid(result):
            return result
        attempt = case["context"]["logical_attempt"]
        # A bad answer/unknown failure must stop admissions immediately, even
        # if another worker currently holds the admission lock for cooldown.
        if not recovery.eligibility(row, logical_attempt=attempt, recoveries_used=0)["eligible"]:
            self.halt(case["id"], "nonrecoverable_action_or_transport")
            return result
        with self.guard:
            proposal = recovery.eligibility(row, logical_attempt=attempt,
                                            recoveries_used=self.recoveries)
            if proposal["eligible"] and not self.stop.is_set():
                self.recoveries += 1
                detected = self.clock()
                self.cooldown_until = max(self.cooldown_until, detected + recovery.DELAY_SECONDS)
                # Persist before any sleep/second physical request. Do not
                # inspect tool arguments or release the first reservation.
                atomic(self.root / "recoveries" / (case["id"] + ".json"), dict(
                    protocol=self.protocol, id=case["id"], logical_id=case["context"]["logical_id"],
                    ordinal=self.recoveries, eligibility=proposal, detected_unix=detected,
                    not_before_unix=self.cooldown_until, request_sha256=case["request_sha256"]))
                return result
        self.halt(case["id"], "nonrecoverable_action_or_transport")
        return result

    def one(self, case):
        logical_path = self.root / "logicals" / (case["id"] + ".json")
        record = dict(protocol=self.protocol, case=case,
            attempt_slots=[case["id"] + "-a1", case["id"] + "-a2"],
            attempts=[], status="prepared", selected_id=None, action=None)
        with self.guard:
            t.require(not logical_path.exists(), "logical action already assigned; no replay")
            t.require(len(list((self.root / "logicals").glob("*.json"))) < MAX_LOGICAL,
                      "logical action ceiling")
            if self.stop.is_set():
                record["status"] = "not_started"
                atomic(logical_path, record)
                return record
            atomic(logical_path, record)
        for attempt in (1, 2):
            request = physical(case, attempt)
            path = self.root / "attempts" / (request["id"] + ".json")
            with self.guard:
                t.require(not path.exists(), "physical attempt already assigned")
                atomic(path, dict(case=request, result=dict(id=request["id"], status="prepared")))
            native = service.Calls(self.root, self.ledger.root, self.stage, MAX_PHYSICAL,
                self.verify, self.execution_score, recovery.CONFIG, self.secret,
                self.send, self.lookup, self.clock, self.sleep)
            native.ledger, native.guard, native.stop = self.ledger, self.guard, self.stop
            native.verify = self.admission_verify
            status = native.one(request)
            atomic(path, dict(case=request, result=status))
            record["attempts"].append(status)
            if status["status"] != "recorded":
                self.halt(request["id"], "physical_request_not_recorded")
                record["status"] = "failed"
                break
            row = t.load(self.root / "calls" / (request["id"] + ".json"))
            if valid(row["result"]):
                record.update(status="recorded", selected_id=request["id"], action=row["result"]["action"])
                break
            event = self.root / "recoveries" / (request["id"] + ".json")
            if attempt == 1 and event.exists() and not self.stop.is_set():
                atomic(logical_path, record)
                continue
            record["status"] = "failed"
            break
        atomic(logical_path, record)
        return record


def audit(root, ledger_root, stage, protocol, score, *, controller_stops=()):
    """Recompute every physical score, recovery, wire and charge; no inference.

This is component integrity, not institutional coverage. The future parent
auditor must also reconstruct the full assigned controller trajectories.
    """
    root = Path(root)
    start = t.load(root / "sessions/transport_start.json")
    t.require(start["protocol"] == protocol and start["stage"] == stage and
        start["maximum_logical"] == MAX_LOGICAL and start["maximum_physical"] == MAX_PHYSICAL and
        start["maximum_reissues"] == recovery.MAX_REISSUES and start["delay_seconds"] == recovery.DELAY_SECONDS,
        "transport start changed")
    def inventory(directory, key):
        rows = []
        for path in sorted((root / directory).glob("*.json")):
            row = t.load(path)
            t.require(path.stem == key(row), "record filename/identity changed")
            rows.append(row)
        t.require(len({key(row) for row in rows}) == len(rows), "duplicate record identity")
        return rows

    logicals = inventory("logicals", lambda r: r["case"]["id"])
    decisions = inventory("attempts", lambda r: r["case"]["id"])
    cases, statuses = [d["case"] for d in decisions], [d["result"] for d in decisions]
    reports, cost = service.audit_records(root, ledger_root, stage, protocol, cases,
                                          dict(results=statuses), score, recovery.CONFIG)
    by_report = {r["id"]: r for r in reports}
    by_decision = {d["case"]["id"]: d for d in decisions}
    events = sorted(inventory("recoveries", lambda r: r["id"]), key=lambda r: r["ordinal"])
    t.require([e["ordinal"] for e in events] == list(range(1, len(events) + 1)) and
              len(events) <= recovery.MAX_REISSUES, "global recovery count/sequence")
    by_event = {e["id"]: e for e in events}
    cooldown, previous_detection = 0, 0
    for event in events:
        decision = by_decision[event["id"]]
        row = t.load(root / "calls" / (event["id"] + ".json"))
        expected = recovery.eligibility(row, logical_attempt=decision["case"]["context"]["logical_attempt"],
                                        recoveries_used=event["ordinal"] - 1)
        t.require(expected["eligible"] and event["eligibility"] == expected and
            event["protocol"] == protocol and event["request_sha256"] == row["request_sha256"] and
            event["logical_id"] == row["context"]["logical_id"] and
            event["detected_unix"] >= row["ended_unix"] and
            event["detected_unix"] >= previous_detection and
            event["not_before_unix"] == max(cooldown, event["detected_unix"] + recovery.DELAY_SECONDS) and
            not valid(by_report[event["id"]]["result"]),
            "recovery eligibility/provenance/timing changed")
        cooldown, previous_detection = event["not_before_unix"], event["detected_unix"]
        for p in (root / "calls").glob("*.json"):
            admitted = t.load(p)["admitted_unix"]
            t.require(not event["detected_unix"] < admitted < event["not_before_unix"],
                      "admission during global cooldown")
    matched = set()
    for logical in logicals:
        case, attempts = logical["case"], logical["attempts"]
        t.require(t.canonical(case["request"]) == case["request_text"] and
                  t.sha(case["request_text"].encode()) == case["request_sha256"], "logical request hash")
        t.require(logical["protocol"] == protocol and logical["attempt_slots"] ==
            [case["id"] + "-a1", case["id"] + "-a2"] and len(attempts) <= 2, "logical slot inventory")
        for index, status in enumerate(attempts, 1):
            expected = physical(case, index)
            t.require(by_decision[expected["id"]] == dict(case=expected, result=status),
                      "physical wire/status changed")
            matched.add(expected["id"])
            if index == 2:
                event = by_event[case["id"] + "-a1"]
                row = root / "calls" / (expected["id"] + ".json")
                if row.exists():
                    t.require(t.load(row)["admitted_unix"] >= event["not_before_unix"], "premature reissue")
        if logical["status"] == "recorded":
            last = attempts[-1]["id"]
            result = by_report[last]["result"]
            t.require(by_report[last]["status"] == "recorded" and valid(result) and
                logical["selected_id"] == last and logical["action"] == result["action"],
                "selected logical action changed")
        elif logical["status"] == "not_started":
            t.require(not attempts and logical["selected_id"] is None and logical["action"] is None,
                      "unstarted logical evidence")
        else:
            t.require(logical["status"] == "failed" and attempts and logical["selected_id"] is None and
                      logical["action"] is None, "incomplete/changed logical outcome")
            last = by_report[attempts[-1]["id"]]
            t.require(last["status"] != "recorded" or not valid(last["result"]), "discarded valid action")
    t.require(matched == set(by_decision) and len(logicals) <= MAX_LOGICAL and
              len(list((root / "calls").glob("*.json"))) <= MAX_PHYSICAL, "physical/logical ceilings/inventory")
    stop = root / "sessions/transport_stop.json"
    failed = any(logical["status"] == "failed" for logical in logicals)
    stopped = failed or bool(controller_stops)
    t.require(stop.exists() == stopped, "global terminal stop missing/extra")
    if stop.exists():
        event = t.load(stop)
        call_failure = event["id"] in by_report and (
            by_report[event["id"]]["status"] != "recorded" or not valid(by_report[event["id"]]["result"]))
        controller_failure = event["id"] in controller_stops and event["reason"] == "controller_instrument_error"
        t.require(event["protocol"] == protocol and (call_failure or controller_failure),
            "global stop provenance")
        # A request whose reservation was already inside the admission lock
        # may finish admitting while the stop is observed outside that lock.
        # Retain both times; no admission after the serialized stop barrier.
        t.require(event["detected_unix"] <= event["admission_barrier_unix"], "stop timing changed")
        t.require(all(t.load(p)["admitted_unix"] <= event["admission_barrier_unix"]
            for p in (root / "calls").glob("*.json")), "admission after global stop")
    ledger = StopLedger(ledger_root)
    # Pure audit reads, not a nested flock: portable export holds the ledger
    # lock already. Parent auditing also verifies its complete ledger inventory.
    t.require(cost <= recovery.PROPOSED_STAGE_CAP and
              ledger._total(ledger._entries()) <= STOP,
              "conservative spending exceeded admission authority")
    return dict(protocol=protocol, logical_actions=len(logicals), physical_calls=len(list((root / "calls").glob("*.json"))),
                recorded=sum(logical["status"] == "recorded" for logical in logicals), recoveries=len(events),
                global_safety_stop=stopped, accounted_usd=str(cost), call_reports=reports, publication_evidence=False)
