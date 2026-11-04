"""Prospective durable board adapter; no credentials, allocation or live CLI.

The caller must supply a pinned coordinator, ledger, admission and transport.
Private tests supply scripted streams. This module does not prepare or authorize
a study. Completed studies and their validators remain unchanged.
"""
from contextlib import redirect_stdout
from copy import deepcopy
from decimal import Decimal
import fcntl
import hashlib
import io
import math
import os
from pathlib import Path
import random
import time
from types import SimpleNamespace

from experiments import paper3_office_sacrifice_probe_v1 as prior
from paper3 import message_board_handoff_v1 as design
from paper3 import retrospective_deepinfra_classifier_v1 as native
from paper3 import retrospective_deepinfra_failure_v1 as resource
from paper3 import retrospective_graceful_recovery as durable
from paper3 import retrospective_reasoning_timeout_recovery_v1 as retry
from paper3 import retrospective_receipt_recovery_v1 as billing
from paper3 import retrospective_serialization_contract as grammar
from paper3.pivot_b_budget import atomic

VERSION = "message-board-durable-development-v1"
ORDER_SEED = 2026110702
require, load, file_sha = durable.require, durable.load, durable.digest
route = design.route


def same(a, b):
    return design.canonical(a) == design.canonical(b)


def payload(call, value):
    """Validate, never coerce, truncate, repair or infer a public response."""
    require(type(value) is dict, "public object")
    if call["kind"] == "post":
        require(set(value) == {"message"} and type(value["message"]) is str
                and 0 < len(value["message"].encode("utf-8")) <= design.POST_BYTES,
                "bounded public message")
    elif call["kind"] in ("decision", "score"):
        require(set(value) == {"decision"} and type(value["decision"]) is str
                and value["decision"] in ("plan_x", "plan_y", "review"), "plan schema")
    else:
        require(call["kind"] == "factual" and set(value) == {"answer"}
                and type(value["answer"]) is bool, "factual boolean schema")
    return deepcopy(value)


def channel(tool_name):
    # Identical stream grammar code; only the prospective tool name differs.
    envelope = billing.bind(grammar.stream_envelope, TOOL_NAME=tool_name)
    return SimpleNamespace(TOOL_NAME=tool_name, _frames=grammar._frames,
                           stream_envelope=envelope)


def known_channels(trace):
    """Do not silently discard an unfamiliar public/action channel."""
    require(all(type(line) is str and (not line or line.startswith(("data:", ":")))
                for line in trace["lines"]), "known SSE fields only")
    for frame in grammar._frames(trace):
        for choice in frame.get("choices", []):
            delta = choice.get("delta", {})
            require(type(delta) is dict and set(delta) <= {
                "role", "content", "tool_calls", "reasoning", "reasoning_content", "reasoning_details"},
                "known native and action channels only")


def classify(row, call):
    """Exact reconstructed request plus unchanged native/billing safety checks.

The scheduler reconstructs the actual history; it supplies the expected call.
Unlike the old electoral classifier, this adapter has no synthetic game/actor
fields. Unknown/partial/ambiguous channels remain global instrument failures.
Whole complete JSON content is local missingness when it does not use the tool
requested by this prospective task. It is never regenerated.
"""
    result = dict(status="unsafe_failed", action=None, execution=None,
                  instrument_safe=False, assessment=None, channel=None, reason=None)
    request = call["request"]
    try:
        schemas = {"post": design.POST_TOOL, "decision": design.DECISION_TOOL,
                   "score": design.DECISION_TOOL, "factual": design.FACT_TOOL}
        schema = schemas[call["kind"]]
        expected = design.make_request(request["messages"], schema, request["seed"])
        require(same(request, expected), "exact route/tool envelope")
        bound = route.reservation(request)
        require(type(row) is dict and row["status"] == "recorded"
                and not row.get("instrument_error"), "complete durable evidence")
        require(same(row["request"], request)
                and row["request_text"] == bound["request_text"]
                and row["request_sha256"] == hashlib.sha256(bound["request_text"].encode()).hexdigest()
                and type(row["input_token_bound"]) is int
                and row["input_token_bound"] == bound["input_token_bound"]
                and row["reserved_usd"] == bound["reserved_usd"], "exact request/reservation")
        assessed = billing.assess(row, native.CONFIG)
        require(same(row["assessment"], assessed), "saved assessment equality")
        result["assessment"] = assessed
        if assessed["stream"]["complete"]:
            # Run before native_evidence is exposed to the resource predicate:
            # a completed length ending cannot hide an unknown action channel.
            known_channels(row["stream"])
        evidence = billing.service.native_evidence(assessed["stream"])
        result["native_evidence"] = evidence
        require(assessed["passed"] is True and evidence["present"] is True
                and evidence["reported_count_consistent"] is True
                and assessed["stream"]["finish_reasons"] in (["tool_calls"], ["stop"])
                and request["reasoning"] == dict(enabled=True, exclude=False),
                "transport/billing/native/usage/completion")
        result["channel"] = channel(schema["function"]["name"]).stream_envelope(row["stream"])
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        result["reason"] = "instrument:" + type(exc).__name__
        # Reuse the exact verified output-limit predicate and structural parser.
        adapted = channel(request["tools"][0]["function"]["name"])
        length_channels = billing.bind(resource._length_channels, grammar=adapted)
        length_check = billing.bind(resource.classify,
            previous=SimpleNamespace(classify=lambda *unused: result),
            _length_channels=length_channels)
        return length_check(row, request, None, None)
    result["instrument_safe"] = True
    try:
        require(result["channel"]["channel"] == "tool", "requested public tool required")
        value = payload(call, grammar._object(result["channel"]["raw_action"]))
        result.update(status="recorded_valid", action=value,
                      execution=dict(public_payload=deepcopy(value)), reason=None)
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        result.update(status="content_failed", reason="content:" + type(exc).__name__)
    return result


check_record = billing.bind(prior.check_record, classify=classify)


def schedule(cases):
    units = [(c.index, condition) for c in cases for condition in
             (*design.CONDITIONS, "factual", "score")]
    random.Random(ORDER_SEED).shuffle(units)
    return units


def drive(cases, respond, persist):
    """Reconstruct every history in fixed order, including missing public posts."""
    episodes, controls, logicals = [], [], []
    by_case = {c.index: c for c in cases}

    def step(call):
        result = respond(call)
        require(result["status"] in ("recorded_valid", *design.MISSING, "retry_exhausted"),
                "unsafe evidence cannot enter public history")
        if result["status"] == "recorded_valid":
            payload(call, result["payload"])
        else:
            require(result["payload"] is None, "missing payload is never inferred")
        record = dict(key=call["key"], request_sha256=design.digest(call["request"]),
                      result=deepcopy(result))
        persist("transitions", call["key"], record)
        logicals.append(record)
        return result

    for index, condition in schedule(cases):
        case = by_case[index]
        if condition in design.CONDITIONS:
            e = design.Episode(case, condition)
            while not e.done:
                call = e.next_call()
                r = step(call)
                # The raw transition retains retry_exhausted separately. The
                # board shows an unavailable post, never a fabricated message.
                status = "resource_failed" if r["status"] == "retry_exhausted" else r["status"]
                e.accept(call["key"], status, r["payload"])
                persist("events", call["key"], e.events[-1])
            result = e.result()
            persist("outcomes", f"board-{index:03d}-{condition}", result)
            episodes.append(result)
        else:
            call = design.control(case, condition)
            r = step(call)
            result = dict(case=index, kind=condition, status=r["status"],
                          observed=r["payload"], expected=call["expected"],
                          correct=(r["payload"] == call["expected"]
                                   if r["status"] == "recorded_valid" else None))
            persist("controls", call["key"], result)
            controls.append(result)
    report = design.readout(cases, episodes)
    report.update(logicals=logicals, controls=controls,
        control_summary={kind: dict(assigned=len(cases),
            valid=sum(r["status"] == "recorded_valid" for r in controls if r["kind"] == kind),
            correct=sum(r["correct"] is True for r in controls if r["kind"] == kind),
            missing=sum(r["correct"] is None for r in controls if r["kind"] == kind))
            for kind in ("factual", "score")},
        quality_summary={condition: {quality: dict(
            assigned=sum(c.better_successor == better for c in cases),
            resolved=sum(r["replacement"] is not None for r in episodes
                if r["condition"] == condition and r["better_successor"] == better),
            correct=sum(r["replacement"] == better for r in episodes
                if r["condition"] == condition and r["better_successor"] == better
                and r["replacement"] is not None))
            for quality, better in (("better", True), ("worse", False))}
            for condition in design.CONDITIONS})
    return report


def saved(root, folder, key, value, *, audit=False):
    path = root / folder / (key + ".json")
    if path.exists():
        require(same(load(path), value), "entire saved " + folder + " differs")
    else:
        require(not audit, "missing saved " + folder)
        path.parent.mkdir(exist_ok=True)
        atomic(path, value)


class Session:
    """No defaults can send traffic: pinned coordinator dependencies required."""

    def __init__(self, root, repo, protocol, cases, book, stage, verify, *,
                 send, lookup, admit, secret=None, clock=time.time, sleep=time.sleep):
        self.root, self.repo = Path(root), Path(repo).resolve(strict=True)
        self.protocol, self.book, self.stage, self.verify = protocol, book, stage, verify
        self.send, self.lookup, self.admit, self.secret = send, lookup, admit, secret
        self.clock, self.sleep, self.calls = clock, sleep, {}
        self.bound = design.request_bound(cases)
        self.observed, self.first_send = None, True
        require(verify()[1] == protocol, "pinned coordinator verification")
        for name in ("calls", "admissions", "missing"):
            (self.root / name).mkdir(exist_ok=True)
        self.cache = retry.DurableResponses(root, repo, protocol=protocol,
            classify=lambda row, req, key: classify(row, self.calls[key]),
            perform=self.perform, check_record=self.check, verify=verify,
            maximum_physical=self.bound["maximum_physical_calls"],
            maximum_reissues=self.bound["maximum_reissues"],
            recover_claim=self.recover, clock=clock, sleep=sleep)

    def close(self):
        self.cache.close()

    def check(self, path, row):
        call = self.calls[row["context"]["logical_id"]]
        check_record(path, row, self.book, self.stage, reconcile=True, assignment=call)

    def recover(self, record, request):
        path = self.book.root / "entries" / (self.stage + "-" + record["physical_id"] + ".json")
        require(not path.exists(), "uncertain sent request; no blind repeat")
        return self.perform(request, record["logical_id"], record["physical_id"])

    def checked_send(self, wire, secret):
        if self.first_send:
            require(self.observed is not None and 0 <= self.clock() - self.observed <= 60,
                    "first actual POST strict route freshness")
            self.first_send = False
        return self.send(wire, secret)

    def perform(self, request, key, physical_id):
        require(same(request, self.calls[key]["request"]), "expected dynamic request")
        reservation = route.reservation(request)
        require(Decimal(reservation["reserved_usd"]) <=
                Decimal(self.bound["per_call_bounds"][key]), "dynamic request exceeds frozen bound")
        window_path = self.root / "window.json"
        if self.observed is None:
            if window_path.exists():
                require(self.clock() < load(window_path)["deadline_unix"], "finite window expired")
            self.observed = self.admit(self.root, self.protocol, self.book, self.stage, self.secret)
            require(0 <= self.clock() - self.observed <= 60, "strict admission freshness")
            if not window_path.exists():
                atomic(window_path, dict(started_unix=self.observed,
                                        deadline_unix=self.observed + 86400))
        require(self.clock() < load(window_path)["deadline_unix"], "finite window expired")
        case = dict(id=physical_id, request=request, **reservation,
                    context=dict(logical_id=key, kind=self.calls[key]["kind"]))
        case["request_sha256"] = hashlib.sha256(reservation["request_text"].encode()).hexdigest()
        calls = billing.Calls(self.root, self.book.root, self.stage,
            self.bound["maximum_physical_calls"], self.verify,
            lambda row, unused: classify(row, self.calls[key]), native.CONFIG, self.secret,
            self.checked_send, self.lookup, self.clock, self.sleep)
        calls.ledger = self.book
        with redirect_stdout(io.StringIO()):
            result = calls.one(case)
        require(result["status"] == "recorded", "physical request incomplete; preserve")
        return self.root / "calls" / (physical_id + ".json")

    def respond(self, call):
        key = call["key"]
        require(key not in self.calls, "one scheduler visit per logical call")
        self.calls[key] = deepcopy(call)
        missing = self.root / "missing" / (key + ".json")
        if not missing.exists():
            try:
                row = self.cache.respond(call["request"], key)
                score = classify(row, call)
                require(score == row["result"], "classification equality")
                return dict(status=score["status"], payload=score["action"],
                            classification=score,
                            evidence=load(self.root / "accepted" / (key + ".json")))
            except durable.Paused as exc:
                if exc.reason != "per_action_retry_limit":
                    raise
                atomic(missing, dict(reason=exc.reason, protocol=self.protocol))
        require(load(missing) == dict(reason="per_action_retry_limit", protocol=self.protocol),
                "only bounded exhausted retries become missing")
        # Even on resume prove the entire failed sequence before trusting a marker.
        return audit_call(self.root, self.repo, self.protocol, self.book, self.stage, call)[0]


def run(root, repo, protocol, cases, book, stage, verify, **dependencies):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "coordinator supplies an existing fresh root")
    with (root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(verify()[1] == protocol, "external coordinator pin")
        require(not (root / "report.json").exists(), "complete root: audit only")
        (root / "invocations").mkdir(exist_ok=True)
        starts = sorted((root / "invocations").glob("*-start.json"))
        require(not starts or not starts[-1].with_name(starts[-1].name.replace("start", "terminal")).exists(),
                "latest terminal requires a decision, never repeat a paused run")
        n = len(starts)
        clock = dependencies.get("clock", time.time)
        atomic(root / "invocations" / f"{n:04d}-start.json",
               dict(protocol=protocol, pid=os.getpid(), started_unix=clock()))
        session = None
        try:
            session = Session(root, repo, protocol, cases, book, stage, verify, **dependencies)
            report = drive(cases, session.respond, lambda *args: saved(root, *args))
            report.update(protocol=protocol, accounting=prior.accounting(book, stage),
                          ledger_hashes=ledger_hashes(book))
            atomic(root / "report.json", report)
            terminal = dict(status="complete", report_sha256=file_sha(root / "report.json"))
        except (durable.Paused, Exception) as exc:
            terminal = dict(status="paused", reason=exc.reason if isinstance(exc, durable.Paused)
                            else type(exc).__name__ + ":" + str(exc))
        finally:
            if session is not None:
                session.close()
        terminal["completed_unix"] = clock()
        atomic(root / "invocations" / f"{n:04d}-terminal.json", terminal)
        return terminal


def ledger_hashes(book):
    return {p.name: file_sha(p) for p in sorted((book.root / "entries").glob("*.json"))}


def audit_call(root, repo, protocol, book, stage, call):
    key, request = call["key"], call["request"]
    claims = [load(p) for p in sorted((root / "attempts").glob(key + "-a*.json"))]
    require(1 <= len(claims) <= 4, "bounded physical attempts per assigned call")
    wire = route.reservation(request)["request_text"]
    used, previous, answer = [], None, None
    window = load(root / "window.json")
    for n, claim in enumerate(claims, 1):
        physical = key + f"-a{n}"
        require(claim["logical_id"] == key and claim["physical_id"] == physical
                and claim["attempt"] == n and claim["protocol"] == protocol
                and claim["request_sha256"] == hashlib.sha256(wire.encode()).hexdigest(),
                "claim/request/seed identity")
        path = root / "calls" / (physical + ".json")
        ref = dict(path=path.relative_to(repo).as_posix(), sha256=file_sha(path))
        require(claim["evidence"] == ref, "exact raw evidence reference")
        row = load(path)
        require(row["id"] == physical and row["protocol"] == protocol
                and row["request_text"] == wire and same(row["request"], request)
                and row["context"] == dict(logical_id=key, kind=call["kind"]), "dynamic raw identity")
        check_record(path, row, book, stage)
        for stamp in (row["admitted_unix"], row["ended_unix"],
                      row["stream"]["started_unix"], row["stream"]["ended_unix"]):
            require(type(stamp) in (int, float) and math.isfinite(stamp), "finite physical timestamp")
        require(window["started_unix"] <= row["admitted_unix"] < window["deadline_unix"]
                and row["admitted_unix"] <= row["stream"]["started_unix"]
                <= row["stream"]["ended_unix"] <= row["ended_unix"], "physical window/timing")
        if previous:
            eligible = retry.eligibility(previous)
            require(eligible["eligible"] and row["admitted_unix"] >= previous["ended_unix"] +
                    max(durable.COOLDOWNS[n-2], eligible["delay"] or 0), "identical-wire retry cooldown")
        score = classify(row, call)
        require(score == row["result"], "raw classification equality")
        if score["status"] in ("recorded_valid", *design.MISSING):
            require(n == len(claims) and load(root / "accepted" / (key + ".json")) == ref
                    and not (root / "missing" / (key + ".json")).exists(), "accepted complete answer never replaced")
            answer = dict(status=score["status"], payload=score["action"],
                          classification=score, evidence=ref)
        else:
            require(retry.eligibility(row)["eligible"], "only known failed attempts")
        used.append(row)
        previous = row
    if answer is None:
        require(len(claims) == 4 and load(root / "missing" / (key + ".json")) ==
                dict(reason="per_action_retry_limit", protocol=protocol)
                and not (root / "accepted" / (key + ".json")).exists(), "exhausted retry evidence")
        answer = dict(status="retry_exhausted", payload=None, classification=None, evidence=None)
    return answer, used


def audit(root, repo, protocol, cases, book, stage, verify):
    root, repo = Path(root), Path(repo).resolve(strict=True)
    require(verify()[1] == protocol, "pinned coordinator audit")
    require(not list(root.rglob("*.partial")), "partial records preserved for review")
    used, inventories = [], {k: set() for k in ("transitions", "events", "outcomes", "controls")}
    bound = design.request_bound(cases)

    def respond(call):
        require(Decimal(route.reservation(call["request"])["reserved_usd"]) <=
                Decimal(bound["per_call_bounds"][call["key"]]), "dynamic bound")
        answer, physical = audit_call(root, repo, protocol, book, stage, call)
        if used:
            require(physical[0]["admitted_unix"] >= used[-1]["ended_unix"], "sequential physical order")
        used.extend(physical)
        return answer

    def persist(folder, key, value):
        inventories[folder].add(key)
        saved(root, folder, key, value, audit=True)

    report = drive(cases, respond, persist)
    report.update(protocol=protocol, accounting=prior.accounting(book, stage), ledger_hashes=ledger_hashes(book))
    for folder, keys in inventories.items():
        require(keys == {p.stem for p in (root / folder).glob("*.json")}, "entire " + folder + " inventory")
    physicals = {r["id"] for r in used}
    require(len(physicals) == len(used) <= bound["maximum_physical_calls"]
            and len(used) - len(report["logicals"]) <= bound["maximum_reissues"], "cohort physical limits")
    require(physicals == {p.stem for p in (root / "calls").glob("*.json")} ==
            {p.stem for p in (root / "attempts").glob("*.json")}, "entire raw/attempt inventory")
    require({r["key"] for r in report["logicals"] if r["result"]["status"] == "retry_exhausted"} ==
            {p.stem for p in (root / "missing").glob("*.json")}, "entire missing inventory")
    require({r["key"] for r in report["logicals"] if r["result"]["status"] != "retry_exhausted"} ==
            {p.stem for p in (root / "accepted").glob("*.json")}, "entire accepted inventory")
    window = load(root / "window.json")
    require(window["deadline_unix"] - window["started_unix"] == 86400, "finite unreset window")
    admissions = [load(p) for p in (root / "admissions").glob("*.json")
                  if not p.name.startswith("failure-")]
    require(admissions and min(a["metadata_observed_unix"] for a in admissions) ==
            window["started_unix"], "initial window binding")
    for a in admissions:
        require(a["protocol"] == protocol and a["account"]["account_funded"] is True
                and a["account"]["research_authority_extended"] is False, "funding without extension")
        route.check_endpoint(a["metadata"])
        observed = a["metadata_observed_unix"]
        first = next(r for r in used if r["admitted_unix"] >= observed)
        require(0 <= first["admitted_unix"] - observed <= 60
                and 0 <= first["stream"]["started_unix"] - observed <= 60, "actual first POST freshness")
    own = [r for r in book._entries() if r["stage"] == stage]
    require({r["request_id"] for r in own} == {stage + "-" + p for p in physicals}, "every physical charge covered")
    require(same(load(root / "report.json"), report), "ENTIRE dynamic-history report differs")
    return dict(entire_report_matched=True, entire_ledger_matched=True,
                logical=len(report["logicals"]), physical=len(used),
                report_sha256=file_sha(root / "report.json"), accounting=report["accounting"])
