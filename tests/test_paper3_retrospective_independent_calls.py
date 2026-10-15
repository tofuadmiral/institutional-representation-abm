"""Fabricated transport and copied authority only; never paid/provider evidence."""
from copy import deepcopy
from decimal import Decimal
from functools import cache
import json

import pytest

from paper3 import retrospective_contract_route_v2 as route
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_independent_calls as calls
from paper3 import retrospective_independent_execution as execution
from paper3 import retrospective_score_ledger_budget as requests
from paper3.pivot_b_budget import atomic
from tests import test_paper3_retrospective_extended_budget as copied_budget
from tests.test_paper3_retrospective_independent_execution import action, assignments, row
from tests.test_paper3_retrospective_score_ledger import fixture


@pytest.fixture
def ledger(tmp_path):
    return copied_budget.ledger.__wrapped__(tmp_path)


class Clock:
    def __init__(self):
        self.now = 1000
    def __call__(self):
        return self.now
    def sleep(self, seconds):
        assert seconds >= 0
        self.now += seconds


@cache
def first_request():
    saved = []
    def ask(actor, identity, term, stage, context, index):
        request = requests.action_request(fixture(2), "binding_sum", 3980000,
            actor, identity, term, stage, context, index)
        if not saved:
            saved.append(request)
        return action(request)
    institution.episode(fixture(2), "binding_sum", ask)
    return saved[0]


def case(identifier="logical", request=None):
    request = deepcopy(request or first_request())
    bound = route.reservation(request)
    return dict(id=identifier, request=request, **bound,
        request_sha256=calls.t.sha(bound["request_text"].encode()), context=dict(
            stage=json.loads(request["messages"][1]["content"])["stage"]))


def classify(evidence, item):
    return execution.classify(evidence, item["request"], fixture(2), item["context"]["stage"])


def answerless(clock):
    return dict(http_status=429, error_type="HTTPError", secret_redacted=False,
        generation_header=None, first_line_unix=None, last_line_unix=None,
        lines=[], line_count=0, byte_count=0, http_error_body_truncated=False,
        started_unix=clock(), ended_unix=clock(),
        http_error_body=json.dumps(dict(error=dict(message="Provider returned error", code=429,
            metadata=dict(provider_name=route.PROVIDER, limit_source="upstream_provider_shared_pool",
                is_byok=False, raw=route.MODEL + " is temporarily rate-limited upstream.")))))


def setup(tmp_path, ledger, *, bad=(), rate=(), absent=False, unsafe=None,
          maximum_logical=60, maximum_reissues=1, verify=None):
    ledger.allocate("fabricated", "2")
    clock, sent = Clock(), []
    def send(wire, secret):
        assert secret is None
        request = json.loads(wire)
        sent.append(wire)
        n = len(sent)
        if n in rate:
            return answerless(clock)
        value = action(request)
        if n in bad:
            value["policy"] = True
        options = unsafe or {} if n == 1 else {}
        trace = row(request, f"fake-{n}", value=value, **options)["stream"]
        trace["started_unix"] = clock()
        clock.sleep(1)
        trace["ended_unix"] = clock()
        return trace
    def lookup(identifier, secret):
        if absent:
            return dict(http_status=404, error_type="HTTPError", data=None, secret_redacted=False)
        return dict(http_status=200, error_type=None, secret_redacted=False,
            data=dict(id=identifier, model=route.MODEL_ALIAS, provider_name=route.PROVIDER, total_cost=.0001))
    bridge = calls.Calls(tmp_path / "run", ledger, "fabricated", verify or (lambda: ({}, "f" * 64)),
        classify, send=send, lookup=lookup, maximum_logical=maximum_logical,
        maximum_reissues=maximum_reissues, clock=clock, sleep=clock.sleep)
    return bridge, sent, clock


def audited(bridge):
    return calls.audit(bridge.root, bridge.ledger.root, bridge.stage, bridge.protocol,
                       classify, bridge.maximum_logical, bridge.maximum_reissues)


@pytest.mark.parametrize("absent", (False, True))
def test_physical_row_preserved_logical_reference_and_full_uncertified_cost(tmp_path, ledger, absent):
    bridge, sent, _ = setup(tmp_path, ledger, absent=absent)
    saved = bridge.one(case())
    assert saved["id"] == "logical" and saved["result"]["status"] == "recorded_valid"
    physical = bridge.root / "calls/logical-a1.json"
    assert calls.t.load(physical)["id"] == "logical-a1"
    assert saved["physical_reference"] == dict(id="logical-a1", sha256=calls.t.sha(physical.read_bytes()))
    report = audited(bridge)
    assert len(sent) == 1 and report["reissues"] == 0
    entry = calls.t.load(ledger.root / "entries/fabricated-logical-a1.json")
    assert entry["certified"] is (not absent)
    assert report["accounted_usd"] == (case()["reserved_usd"] if absent else "0.0001")
    assert not report["publication_evidence"]
    bridge.close()


def test_content_failure_is_not_retried_and_next_independent_action_can_run(tmp_path, ledger):
    bridge, sent, _ = setup(tmp_path, ledger, bad=(1,))
    first = bridge.one(case("first"))
    second = bridge.one(case("second"))
    assert first["result"]["status"] == "content_failed" and first["result"]["action"] is None
    assert second["result"]["status"] == "recorded_valid"
    assert not bridge.stop.is_set() and len(sent) == 2
    assert len(audited(bridge)["logicals"]) == 2
    bridge.close()


def test_one_exact_reissue_delays_and_keeps_both_reservations(tmp_path, ledger):
    bridge, sent, clock = setup(tmp_path, ledger, rate=(1,))
    saved = bridge.one(case())
    assert saved["physical_reference"]["id"] == "logical-a2"
    assert sent[0] == sent[1] and len(sent) == 2 and clock() >= 1301
    report = audited(bridge)
    assert report["reissues"] == 1
    assert Decimal(report["accounted_usd"]) == Decimal(case()["reserved_usd"]) + Decimal(".0001")
    failed = calls.t.load(ledger.root / "entries/fabricated-logical-a1.json")
    assert not failed["certified"] and failed["accounted_usd"] == failed["reserved_usd"]
    bridge.close()


@pytest.mark.parametrize("rate,ceiling,count", (((1,), 0, 1), ((1, 2), 1, 2), ((1, 3), 1, 3)))
def test_no_second_or_unapproved_reissue_and_global_stop(tmp_path, ledger, rate, ceiling, count):
    bridge, sent, _ = setup(tmp_path, ledger, rate=rate, maximum_reissues=ceiling)
    bridge.one(case("first"))
    if not bridge.stop.is_set():
        bridge.one(case("second"))
    assert bridge.stop.is_set() and len(sent) == count
    bridge.one(case("later"))
    assert len(sent) == count
    assert audited(bridge)["logicals"][-1]["status"] in ("unsafe_failed", "not_started")
    bridge.close()


@pytest.mark.parametrize("unsafe", (dict(native=False), dict(channel="both"), dict(bad_count=True), dict(provider="wrong")))
def test_unsafe_never_local_or_reissued(tmp_path, ledger, unsafe):
    bridge, sent, _ = setup(tmp_path, ledger, unsafe=unsafe)
    evidence = bridge.one(case())
    assert bridge.stop.is_set() and len(sent) == 1
    assert evidence["result"]["status"] == "unsafe_failed"
    assert audited(bridge)["reissues"] == 0
    bridge.close()


def test_controller_bridge_two_episodes_with_local_failure_and_all_missingness(tmp_path, ledger):
    bridge, sent, _ = setup(tmp_path, ledger, bad=(1,))
    events = []
    result = execution.execute(assignments(), respond=lambda req, key: bridge.one(case(key, req)),
        verify=lambda: None, persist=lambda event: events.append(deepcopy(event)))
    assert result["completed"] == 1 and result["content_failed"] == 1
    assert not result["global_safety_stop"] and len(sent) == 31
    first, second = result["assignments"]
    assert not first["first_term"]["complete"] and not first["two_term"]["complete"]
    assert all(s["status"] == "not_started" for s in first["logicals"][1:])
    assert second["first_term"]["complete"] and second["two_term"]["complete"]
    assert len(audited(bridge)["physical_reports"]) == 31
    assert events[-1]["event"] == "terminal"
    bridge.close()


@pytest.mark.parametrize("arm", institution.ARMS)
def test_full_two_term_economic_arms_execute_through_real_service_with_fake_wire(tmp_path, ledger, arm):
    bridge, sent, _ = setup(tmp_path, ledger)
    result = execution.execute(assignments((arm,)),
        respond=lambda req, key: bridge.one(case(key, req)), verify=lambda: None, persist=lambda _: None)
    assert result["completed"] == 1 and not result["global_safety_stop"] and len(sent) == 30
    assert result["assignments"][0]["two_term"]["complete"]
    assert len(audited(bridge)["physical_reports"]) == 30
    bridge.close()


def test_unknown_transport_exception_preserves_pending_cost_and_stops(tmp_path, ledger):
    bridge, sent, _ = setup(tmp_path, ledger)
    def broken_send(wire, secret):
        sent.append(wire)
        raise OSError("fabricated unknown failure")
    bridge.send = broken_send
    evidence = bridge.one(case())
    assert evidence["status"] == "instrument_error" and bridge.stop.is_set()
    report = audited(bridge)
    assert report["accounted_usd"] == case()["reserved_usd"]
    assert calls.t.load(ledger.root / "entries/fabricated-logical-a1.json")["status"] == "reserved"
    bridge.one(case("later"))
    assert len(sent) == 1
    bridge.close()


def test_source_divergence_after_spending_is_not_certified_as_terminal_closure(tmp_path, ledger):
    count = [0]
    def verify():
        count[0] += 1
        # Bridge init, per-physical service init, pre-admission, post-settlement barrier.
        if count[0] == 4:
            raise ValueError("fabricated source divergence")
        return {}, "f" * 64
    bridge, sent, _ = setup(tmp_path, ledger, verify=verify)
    with pytest.raises(ValueError, match="source divergence"):
        bridge.one(case())
    assert len(sent) == 1 and bridge.stop.is_set()
    assert (bridge.root / "calls/logical-a1.json").exists()
    assert calls.t.load(ledger.root / "entries/fabricated-logical-a1.json")["status"] == "settled"
    with pytest.raises(ValueError, match="unfinished"):
        audited(bridge)
    bridge.close()


def test_writer_lock_and_logical_concurrency_reject_parallel_work(tmp_path, ledger):
    bridge, sent, _ = setup(tmp_path, ledger)
    with pytest.raises(BlockingIOError):
        calls.Calls(bridge.root, ledger, bridge.stage, bridge.verify, classify,
            send=bridge.send, lookup=bridge.lookup, maximum_logical=60, maximum_reissues=1)
    bridge.serial.acquire()
    try:
        with pytest.raises(ValueError, match="one worker"):
            bridge.one(case())
    finally:
        bridge.serial.release()
    assert bridge.stop.is_set() and not sent
    bridge.close()


@pytest.mark.parametrize("field", ("not_before_unix", "request_sha256", "eligibility", "ordinal", "logical_id"))
def test_reissue_audit_rejects_changed_recovery_or_delay(tmp_path, ledger, field):
    bridge, _, _ = setup(tmp_path, ledger, rate=(1,))
    bridge.one(case())
    path = bridge.root / "recoveries/logical-a1.json"
    data = calls.t.load(path)
    data[field] = 0
    atomic(path, data)
    with pytest.raises((ValueError, TypeError)):
        audited(bridge)
    bridge.close()


def test_declared_logical_limit_stops_without_another_reservation(tmp_path, ledger):
    bridge, sent, _ = setup(tmp_path, ledger, maximum_logical=1)
    bridge.one(case())
    with pytest.raises(ValueError, match="inventory ceiling"):
        bridge.one(case("extra"))
    assert len(sent) == 1
    assert not (ledger.root / "entries/fabricated-extra-a1.json").exists()
    bridge.close()


@pytest.mark.parametrize("mutate", ("filename", "logical_copy", "stage_pin", "attempt_wire", "failed_copy", "unfinished"))
def test_audit_rejects_evidence_scope_and_closure_tampering(tmp_path, ledger, mutate):
    bridge, _, _ = setup(tmp_path, ledger, unsafe=dict(native=False) if mutate == "failed_copy" else None)
    bridge.one(case())
    if mutate == "filename":
        (bridge.root / "logicals/logical.json").rename(bridge.root / "logicals/other.json")
    elif mutate == "stage_pin":
        p = ledger.root / "stages/fabricated.json"
        data = calls.t.load(p)
        data["cap_usd"] = "3"
        atomic(p, data)
    elif mutate == "attempt_wire":
        p = bridge.root / "attempts/logical-a1.json"
        data = calls.t.load(p)
        data["case"]["request"]["seed"] += 1
        atomic(p, data)
    else:
        p = bridge.root / "logicals/logical.json"
        data = calls.t.load(p)
        if mutate == "unfinished":
            data["status"] = "prepared"
        else:
            data["returned_evidence"]["id"] = "changed"
        atomic(p, data)
    with pytest.raises(ValueError):
        audited(bridge)
    bridge.close()


def test_no_transport_restart_and_no_duplicate_action(tmp_path, ledger):
    bridge, sent, _ = setup(tmp_path, ledger)
    bridge.one(case())
    with pytest.raises(ValueError, match="already attempted"):
        bridge.one(case())
    assert len(sent) == 1
    bridge.close()
    with pytest.raises(ValueError, match="never restart"):
        calls.Calls(bridge.root, ledger, bridge.stage, bridge.verify, classify,
            send=bridge.send, lookup=bridge.lookup, maximum_logical=60, maximum_reissues=1)


@pytest.mark.parametrize("ceiling", (True, -1, 26, None))
def test_no_implicit_unbounded_reissue_policy(ceiling):
    with pytest.raises(ValueError):
        calls.eligibility({}, 1, 0, ceiling)
