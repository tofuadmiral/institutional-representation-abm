"""Fresh-only serial bounded recovery through the preserved native service.

No preparation, paid transport defaults, old-run continuation or launch CLI.
Verified output-limit failures remain episode-local without executing an action.
Four immutable physical slots per logical action, 40 reissues per block, and a
24-hour admission deadline. Complete bad actions are never repaired/reissued.
"""
from copy import deepcopy
import fcntl
import math
from pathlib import Path
from threading import Event, Lock, RLock
import time

from experiments import paper3_transport_diagnostic as t
from paper3 import retrospective_anticipation_recovery_policy as policy
from paper3 import retrospective_billing_calls as service
from paper3 import retrospective_independent_calls as previous
from paper3 import retrospective_independent_execution as execution
from paper3 import retrospective_resource_budget_v1 as budget
from paper3.pivot_b_budget import atomic, identifier

normalized = previous.normalized


def physical(case, attempt):
    slots = policy.physical_slots(case["id"])
    t.require(type(attempt) is int and 1 <= attempt <= len(slots), "four physical slots")
    t.require(not {"logical_id", "logical_attempt"} & set(case["context"]), "reserved context keys")
    return dict(**{k: deepcopy(v) for k, v in case.items() if k not in ("id", "context")},
        id=slots[attempt - 1], context=dict(**case["context"], logical_id=case["id"], logical_attempt=attempt))


class Calls(previous.Calls):
    def __init__(self, root, ledger, stage, verify, classify, *, send, lookup,
                 maximum_logical, secret=None, clock=time.time, sleep=time.sleep):
        t.require(isinstance(ledger, budget.RecoveryLedger), "prospective total19 resource ledger required")
        t.require(all(callable(f) for f in (verify, classify, send, lookup, clock, sleep)),
                  "explicit verification/classification/transport hooks required")
        t.require(type(maximum_logical) is int and 0 < maximum_logical <= 240,
                  "frozen per-block logical inventory")
        identifier(stage)
        self.root, self.ledger, self.stage = Path(root), ledger, stage
        self.verify, self.classify, self.send, self.lookup = verify, classify, send, lookup
        self.secret, self.clock, self.sleep = secret, clock, sleep
        self.maximum_logical = maximum_logical
        self.maximum_reissues = policy.MAX_REISSUES_PER_BLOCK
        self.maximum_physical = maximum_logical + self.maximum_reissues
        self.guard, self.stop, self.serial = RLock(), Event(), Lock()
        self.recoveries, self.cooldown_until = 0, 0
        self.protocol = verify()[1]
        self.started_unix = clock()
        policy.admission_open(started_unix=self.started_unix, now_unix=self.started_unix)
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
                    ("calls", "attempts", "logicals", "recoveries")), "fresh transport only; never restart")
            atomic(self.root / "sessions/transport_start.json", dict(protocol=self.protocol,
                stage=stage, stage_pins=ledger.stage_pins(), maximum_logical=maximum_logical,
                maximum_physical=self.maximum_physical, policy=policy.specification(),
                retirement_pins=dict(ledger._retirement_pins), started_unix=self.started_unix))
        except Exception:
            self.writer.close()
            raise

    def integrity_verify(self):
        value = self.verify()
        t.require(value[1] == self.protocol, "source/protocol changed")
        return value

    def admission_verify(self):
        while self.clock() < self.cooldown_until and not self.stop.is_set():
            self.sleep(min(1, self.cooldown_until - self.clock()))
        if not policy.admission_open(started_unix=self.started_unix, now_unix=self.clock()):
            self.halt("deadline", "block_admission_deadline")
        t.require(not self.stop.is_set(), "global transport stop")
        return self.integrity_verify()

    def execution_score(self, row, case):
        verdict = self.classify(row, case)
        t.require(verdict["status"] in ("recorded_valid", "content_failed", "resource_failed", "unsafe_failed"),
                  "known scientific disposition")
        if verdict["status"] in ("recorded_valid", "content_failed"):
            t.require(verdict["instrument_safe"] is True and
                (verdict["action"] is not None) == (verdict["status"] == "recorded_valid"),
                "safe disposition without invented action")
            return verdict
        if verdict["status"] == "resource_failed":
            t.require(verdict.get("independent_episode_safe") is True and
                verdict["instrument_safe"] is False and verdict["action"] is None and
                verdict.get("execution") is None and verdict["accepted_action"] is False,
                "verified resource failure is isolated, never executed")
            return verdict
        detected = self.clock()
        proposal = policy.eligibility(row, physical_attempt=case["context"]["logical_attempt"],
            block_reissues_used=self.recoveries, block_started_unix=self.started_unix,
            detected_unix=detected)
        if proposal["eligible"] and not self.stop.is_set():
            self.recoveries += 1
            self.cooldown_until = proposal["not_before_unix"]
            atomic(self.root / "recoveries" / (case["id"] + ".json"), dict(
                protocol=self.protocol, id=case["id"], logical_id=case["context"]["logical_id"],
                ordinal=self.recoveries, eligibility=proposal, detected_unix=detected,
                not_before_unix=self.cooldown_until, request_sha256=case["request_sha256"]))
        else:
            self.halt(case["id"], "unsafe_or_exhausted_reissue")
        return verdict

    def _one(self, case):
        slots = policy.physical_slots(case["id"])
        logical_path = self.root / "logicals" / (case["id"] + ".json")
        t.require(not logical_path.exists(), "logical action already attempted")
        t.require(len(list((self.root / "logicals").glob("*.json"))) < self.maximum_logical,
                  "logical inventory ceiling")
        record = dict(protocol=self.protocol, case=deepcopy(case), attempt_slots=list(slots),
            attempts=[], status="prepared", selected_id=None, returned_evidence=None)
        if not policy.admission_open(started_unix=self.started_unix, now_unix=self.clock()):
            self.halt(case["id"], "block_admission_deadline")
        if self.stop.is_set():
            record["status"] = "not_started"
            atomic(logical_path, record)
            return dict(id=case["id"], status="not_started", instrument_error="global_stop")
        atomic(logical_path, record)
        for attempt in range(1, len(slots) + 1):
            request = physical(case, attempt)
            policy.verify_identical_wire(case["request_text"], request["request_text"], case["request_sha256"])
            path = self.root / "attempts" / (request["id"] + ".json")
            t.require(not path.exists(), "physical slot already attempted")
            atomic(path, dict(case=request, result=dict(id=request["id"], status="prepared")))
            native = service.Calls(self.root, self.ledger.root, self.stage, self.maximum_physical,
                self.admission_verify, self.execution_score, execution.CONFIG, self.secret,
                self.send, self.lookup, self.clock, self.sleep)
            # One native instance is one physical request. This bridge owns all
            # prospective retry limits; no parent failure counter is relaxed.
            native.ledger, native.guard = self.ledger, self.guard
            # Native local length-ending stop remains intact. This prospective
            # controller owns its separate, never-cleared global stop and
            # classifies ONLY the approved resource disposition as episode-local.
            # Other local instrument failures halt below or in execution_score.
            status = native.one(request)
            atomic(path, dict(case=request, result=status))
            record["attempts"].append(status)
            raw_path = self.root / "calls" / (request["id"] + ".json")
            if raw_path.exists():
                row = t.load(raw_path)
                record["returned_evidence"] = normalized(row, raw_path, case["id"])
                result = row.get("result", {})
                if status["status"] == "recorded" and result.get("status") in ("recorded_valid", "content_failed", "resource_failed"):
                    # Received answers survive the deadline; only new admissions
                    # are closed. Sources/settlement integrity are still checked.
                    self.integrity_verify()
                    record.update(status=result["status"], selected_id=request["id"])
                    break
            event = self.root / "recoveries" / (request["id"] + ".json")
            if attempt < len(slots) and not self.stop.is_set() and event.exists():
                atomic(logical_path, record)
                try:
                    self.admission_verify()  # Never shorten the full cooldown.
                except Exception:
                    self.halt(request["id"], "reissue_admission_failure")
                    record["status"] = "unsafe_failed"
                    break
                continue
            self.halt(request["id"], "physical_or_scientific_failure")
            record["status"] = "unsafe_failed"
            break
        if record["returned_evidence"] is None:
            record["returned_evidence"] = dict(id=case["id"], status="instrument_error",
                                              instrument_error="no_complete_physical_record")
        atomic(logical_path, record)
        return deepcopy(record["returned_evidence"])


def audit(root, ledger_root, stage, protocol, classify, maximum_logical):
    """Recompute physical evidence, exact retry limits, timing and logical mapping."""
    root, ledger_root = Path(root), Path(ledger_root)
    t.require(type(maximum_logical) is int and 0 < maximum_logical <= 240, "bounded logical inventory")
    start = t.load(root / "sessions/transport_start.json")
    t.require(type(start["maximum_logical"]) is int and type(start["maximum_physical"]) is int,
              "typed transport declaration")
    t.require(t.canonical(start) == t.canonical(dict(protocol=protocol, stage=stage, stage_pins=start["stage_pins"],
        maximum_logical=maximum_logical, maximum_physical=maximum_logical + policy.MAX_REISSUES_PER_BLOCK,
        policy=policy.specification(), retirement_pins=start["retirement_pins"],
        started_unix=start["started_unix"])), "transport declaration changed")
    policy.admission_open(started_unix=start["started_unix"], now_unix=start["started_unix"])
    ledger = budget.RecoveryLedger(ledger_root, stage_pins=start["stage_pins"],
                                   retirement_pins=start["retirement_pins"])
    with ledger.locked():
        ledger._stage(stage)

    def inventory(directory, key):
        paths = sorted((root / directory).glob("*.json"))
        rows = [t.load(p) for p in paths]
        for path, row in zip(paths, rows, strict=True):
            t.require(path.name == identifier(key(row)) + ".json", "record filename changed")
        t.require(len({key(r) for r in rows}) == len(rows), "record identities changed")
        return rows

    logicals = inventory("logicals", lambda r: r["case"]["id"])
    attempts = inventory("attempts", lambda r: r["case"]["id"])
    t.require(len(logicals) <= maximum_logical and
        len(attempts) <= maximum_logical + policy.MAX_REISSUES_PER_BLOCK, "physical/logical ceiling")
    reports, cost = service.audit_records(root, ledger_root, stage, protocol,
        [r["case"] for r in attempts], dict(results=[r["result"] for r in attempts]), classify, execution.CONFIG)
    by_attempt = {r["case"]["id"]: r for r in attempts}
    call_rows = [t.load(p) for p in (root / "calls").glob("*.json")]
    stop_path = root / "sessions/transport_stop.json"
    stop = t.load(stop_path) if stop_path.exists() else None
    if stop:
        t.require(stop["protocol"] == protocol and type(stop["detected_unix"]) in (int, float) and
            math.isfinite(stop["detected_unix"]) and stop["detected_unix"] >= start["started_unix"],
            "stop provenance changed")
    for row in call_rows:
        t.require(policy.admission_open(started_unix=start["started_unix"], now_unix=row["admitted_unix"]),
                  "admission at/after block deadline")
        if stop:
            t.require(row["admitted_unix"] <= stop["detected_unix"], "admission after global stop")
    events = sorted(inventory("recoveries", lambda r: r["id"]), key=lambda r: r["ordinal"])
    t.require(all(type(e["ordinal"]) is int for e in events) and
        [e["ordinal"] for e in events] == list(range(1, len(events) + 1)) and
        len(events) <= policy.MAX_REISSUES_PER_BLOCK, "reissue inventory")
    last_detection = start["started_unix"]
    for event in events:
        row = t.load(root / "calls" / (event["id"] + ".json"))
        expected = policy.eligibility(row,
            physical_attempt=by_attempt[event["id"]]["case"]["context"]["logical_attempt"],
            block_reissues_used=event["ordinal"] - 1, block_started_unix=start["started_unix"],
            detected_unix=event["detected_unix"])
        t.require(expected["eligible"] and event["eligibility"] == expected and event["protocol"] == protocol and
            event["request_sha256"] == row["request_sha256"] and event["logical_id"] == row["context"]["logical_id"] and
            event["detected_unix"] >= last_detection and event["detected_unix"] >= row["ended_unix"] and
            event["not_before_unix"] == expected["not_before_unix"], "retry evidence/timing changed")
        last_detection = event["detected_unix"]
        t.require(all(not event["detected_unix"] < r["admitted_unix"] < event["not_before_unix"]
                      for r in call_rows), "admission during cooldown")
    matched, referenced = set(), set()
    reissues = 0
    for logical in logicals:
        case = logical["case"]
        slots = list(policy.physical_slots(case["id"]))
        t.require(logical["protocol"] == protocol and logical["attempt_slots"] == slots and
            len(logical["attempts"]) <= len(slots), "logical declaration changed")
        for index, status in enumerate(logical["attempts"], 1):
            expected = physical(case, index)
            t.require(by_attempt[expected["id"]] == dict(case=expected, result=status), "physical request/status changed")
            policy.verify_identical_wire(case["request_text"], expected["request_text"], case["request_sha256"])
            matched.add(expected["id"])
            if index > 1:
                reissues += 1
                event = t.load(root / "recoveries" / (slots[index - 2] + ".json"))
                row_path = root / "calls" / (expected["id"] + ".json")
                if row_path.exists():
                    t.require(t.load(row_path)["admitted_unix"] >= event["not_before_unix"], "premature reissue")
            if (root / "recoveries" / (expected["id"] + ".json")).exists():
                referenced.add(expected["id"])
        t.require(logical["status"] in ("recorded_valid", "content_failed", "resource_failed", "unsafe_failed", "not_started"),
                  "unfinished logical record; preserve interruption")
        selected = logical["selected_id"]
        if selected is not None:
            t.require(bool(logical["attempts"]) and selected == logical["attempts"][-1]["id"], "selected earlier answer")
            path = root / "calls" / (selected + ".json")
            row = t.load(path)
            t.require(logical["returned_evidence"] == normalized(row, path, case["id"]) and
                logical["status"] == row["result"]["status"] in ("recorded_valid", "content_failed", "resource_failed") and
                logical["attempts"][-1]["status"] == "recorded", "selected evidence changed")
        elif logical["status"] == "not_started":
            t.require(not logical["attempts"] and logical["returned_evidence"] is None and stop is not None,
                      "unstarted logical has physical evidence/no stop")
        else:
            t.require(logical["status"] == "unsafe_failed" and bool(logical["attempts"]) and stop is not None,
                      "unsafe failure without attempts/stop")
            path = root / "calls" / (logical["attempts"][-1]["id"] + ".json")
            expected = normalized(t.load(path), path, case["id"]) if path.exists() else dict(
                id=case["id"], status="instrument_error", instrument_error="no_complete_physical_record")
            t.require(logical["returned_evidence"] == expected, "failed evidence changed")
    t.require(matched == set(by_attempt), "unmatched physical attempt")
    t.require(referenced == {e["id"] for e in events}, "unmatched recovery evidence")
    t.require(reissues <= len(events) <= policy.MAX_REISSUES_PER_BLOCK, "physical reissue ceiling")
    return dict(protocol=protocol, logicals=logicals, physical_reports=reports, accounted_usd=str(cost),
        reissues=reissues, recovery_events=len(events), allocation_authorized=False, publication_evidence=False)
