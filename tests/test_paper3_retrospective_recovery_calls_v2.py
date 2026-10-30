"""Real service/controller, synthetic wire and copied authorities; zero paid calls."""
from decimal import Decimal
import json

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_recovery_policy as policy
from paper3 import retrospective_independent_execution as execution
from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_recovery_calls_v2 as calls
from paper3 import retrospective_recovery_journal_v2 as replay
from paper3.pivot_b_budget import atomic
from tests import test_paper3_retrospective_recovery_budget_v2 as copied
from tests.test_paper3_retrospective_independent_calls import Clock, answerless, case, classify
from tests.test_paper3_retrospective_independent_execution import action, assignments, row


@pytest.fixture
def ledger(tmp_path):
    return copied.ledger.__wrapped__(tmp_path)


def setup(tmp_path, ledger, *, rate=(), bad=(), unsafe=None, absent=False,
          maximum_logical=240, duration=1, stage="fabricated", root="run", allocate=True):
    if allocate:
        ledger.allocate(stage, "3")
    clock, sent = Clock(), []
    def send(wire, secret):
        assert secret is None
        request = json.loads(wire)
        sent.append((wire, clock()))
        n = len(sent)
        if n in rate:
            return answerless(clock)
        value = action(request)
        if n in bad:
            if "policy" in value:
                value["policy"] = True
            elif "support" in value:
                value["support"] = 1
            else:
                value["vote"] = 1
        trace = row(request, f"fake-{stage}-{n}", value=value, **(unsafe or {}))["stream"]
        trace["started_unix"] = clock()
        clock.sleep(duration)
        trace["ended_unix"] = clock()
        return trace
    def lookup(identifier, secret):
        if absent:
            return dict(http_status=404, error_type="HTTPError", data=None, secret_redacted=False)
        return dict(http_status=200, error_type=None, secret_redacted=False, data=dict(
            id=identifier, model=calls.execution.CONFIG["models"][0],
            provider_name=calls.execution.CONFIG["provider"], total_cost=.0001))
    bridge = calls.Calls(tmp_path / root, ledger, stage, lambda: ({}, "f" * 64), classify,
        send=send, lookup=lookup, maximum_logical=maximum_logical, clock=clock, sleep=clock.sleep)
    return bridge, sent, clock


def audited(bridge):
    return calls.audit(bridge.root, bridge.ledger.root, bridge.stage, bridge.protocol,
                       bridge.classify, bridge.maximum_logical)


def test_three_reissues_exact_wire_and_escalating_cooldowns(tmp_path, ledger):
    bridge, sent, clock = setup(tmp_path, ledger, rate=(1, 2, 3))
    result = bridge.one(case())
    assert result["physical_reference"]["id"] == "logical-a4"
    assert len({wire for wire, _ in sent}) == 1
    assert [stamp for _, stamp in sent] == [1000, 1300, 1900, 3100]
    assert clock() == 3101
    report = audited(bridge)
    assert report["reissues"] == report["recovery_events"] == 3
    assert Decimal(report["accounted_usd"]) == 3 * Decimal(case()["reserved_usd"]) + Decimal(".0001")
    for n in (1, 2, 3):
        failed = calls.t.load(ledger.root / f"entries/fabricated-logical-a{n}.json")
        assert failed["certified"] is False and failed["accounted_usd"] == failed["reserved_usd"]
    bridge.close()


def test_fourth_failure_stops_no_fifth_attempt(tmp_path, ledger):
    bridge, sent, _ = setup(tmp_path, ledger, rate=(1, 2, 3, 4))
    bridge.one(case())
    bridge.one(case("later"))
    assert bridge.stop.is_set() and len(sent) == 4
    assert audited(bridge)["reissues"] == 3
    assert not (bridge.root / "calls/logical-a5.json").exists()
    bridge.close()


def test_block_cap_forty_independent_of_per_action_cap(tmp_path, ledger):
    # Each of forty actions has one eligible failure, then a successful action.
    bridge, sent, _ = setup(tmp_path, ledger, rate=tuple(range(1, 82, 2)))
    for n in range(41):
        bridge.one(case(f"l{n:02}"))
    assert bridge.stop.is_set() and len(sent) == 81
    report = audited(bridge)
    assert report["reissues"] == report["recovery_events"] == 40
    bridge.close()


@pytest.mark.parametrize("absent", (False, True))
def test_valid_content_and_absent_receipts_preserve_full_cost(tmp_path, ledger, absent):
    bridge, sent, _ = setup(tmp_path, ledger, absent=absent)
    result = bridge.one(case())
    assert result["result"]["status"] == "recorded_valid" and len(sent) == 1
    report = audited(bridge)
    entry = calls.t.load(ledger.root / "entries/fabricated-logical-a1.json")
    assert entry["certified"] is (not absent)
    assert report["accounted_usd"] == (case()["reserved_usd"] if absent else "0.0001")
    bridge.close()


def test_bad_action_not_reissued_next_independent_episode_allowed(tmp_path, ledger):
    bridge, sent, _ = setup(tmp_path, ledger, bad=(1,))
    result = execution.execute(assignments(), respond=lambda req, key: bridge.one(case(key, req)),
        verify=lambda: None, persist=lambda event: None)
    assert result["content_failed"] == 1 and result["completed"] == 1
    assert not result["global_safety_stop"] and len(sent) == 31
    assert audited(bridge)["reissues"] == 0
    assert result["assignments"][0]["logicals"][1]["status"] == "not_started"
    bridge.close()


@pytest.mark.parametrize("unsafe", (dict(native=False), dict(channel="both"),
                                    dict(bad_count=True), dict(provider="wrong")))
def test_native_channel_route_and_usage_failure_never_reissued(tmp_path, ledger, unsafe):
    bridge, sent, _ = setup(tmp_path, ledger, unsafe=unsafe)
    bridge.one(case())
    assert bridge.stop.is_set() and len(sent) == 1
    assert audited(bridge)["reissues"] == 0
    bridge.close()


def test_complete_answer_crossing_deadline_retained_but_no_next_admission(tmp_path, ledger):
    bridge, sent, _ = setup(tmp_path, ledger, duration=policy.BLOCK_DEADLINE_SECONDS)
    result = bridge.one(case())
    assert result["result"]["status"] == "recorded_valid"
    later = bridge.one(case("later"))
    assert later["status"] == "not_started" and len(sent) == 1
    assert audited(bridge)["logicals"][0]["selected_id"] is None  # filename 'later' sorts first
    bridge.close()


def test_cooldown_that_would_exceed_deadline_never_shortened(tmp_path, ledger):
    bridge, sent, clock = setup(tmp_path, ledger, rate=(1,))
    clock.now += policy.BLOCK_DEADLINE_SECONDS - 299
    bridge.one(case())
    assert bridge.stop.is_set() and len(sent) == 1
    assert audited(bridge)["reissues"] == 0
    bridge.close()


def test_deadline_reached_during_cooldown_keeps_failed_evidence(tmp_path, ledger):
    bridge, sent, clock = setup(tmp_path, ledger, rate=(1,))
    def oversleep(seconds):
        clock.now = bridge.started_unix + policy.BLOCK_DEADLINE_SECONDS
    bridge.sleep = oversleep
    result = bridge.one(case())
    assert result["result"]["status"] == "unsafe_failed" and len(sent) == 1
    report = audited(bridge)
    assert report["reissues"] == 0 and report["recovery_events"] == 1
    bridge.close()


def test_unknown_exception_keeps_pending_reservation_and_stops(tmp_path, ledger):
    bridge, sent, _ = setup(tmp_path, ledger)
    def broken(wire, secret):
        sent.append((wire, 1000))
        raise OSError("fabricated")
    bridge.send = broken
    bridge.one(case())
    assert bridge.stop.is_set() and len(sent) == 1
    assert audited(bridge)["accounted_usd"] == case()["reserved_usd"]
    assert calls.t.load(ledger.root / "entries/fabricated-logical-a1.json")["status"] == "reserved"
    bridge.close()


@pytest.mark.parametrize("field", ("ordinal", "not_before_unix", "eligibility", "request_sha256", "logical_id"))
def test_audit_rejects_retry_evidence_tampering(tmp_path, ledger, field):
    bridge, _, _ = setup(tmp_path, ledger, rate=(1, 2, 3))
    bridge.one(case())
    path = bridge.root / "recoveries/logical-a2.json"
    data = calls.t.load(path)
    data[field] = 0
    atomic(path, data)
    with pytest.raises((ValueError, TypeError)):
        audited(bridge)
    bridge.close()


@pytest.mark.parametrize("mutation", ("wire", "slots", "reference", "unmatched", "unfinished"))
def test_audit_rejects_changed_logical_and_physical_provenance(tmp_path, ledger, mutation):
    bridge, _, _ = setup(tmp_path, ledger, rate=(1, 2, 3))
    bridge.one(case())
    path = bridge.root / "logicals/logical.json"
    data = calls.t.load(path)
    if mutation == "wire":
        path = bridge.root / "attempts/logical-a2.json"
        data = calls.t.load(path)
        data["case"]["request"]["seed"] += 1
    elif mutation == "slots":
        data["attempt_slots"].append("logical-a5")
    elif mutation == "reference":
        data["returned_evidence"]["physical_reference"]["sha256"] = "0" * 64
    elif mutation == "unmatched":
        data["attempts"].pop()
    else:
        data["status"] = "prepared"
    atomic(path, data)
    with pytest.raises(ValueError):
        audited(bridge)
    bridge.close()


def test_no_duplicate_action_restart_or_parallel_worker(tmp_path, ledger):
    bridge, sent, _ = setup(tmp_path, ledger)
    bridge.one(case())
    with pytest.raises(ValueError, match="already attempted"):
        bridge.one(case())
    assert len(sent) == 1
    bridge.close()
    with pytest.raises(ValueError, match="never restart"):
        calls.Calls(bridge.root, ledger, bridge.stage, bridge.verify, classify,
            send=bridge.send, lookup=bridge.lookup, maximum_logical=240)


def test_full_480_action_sixteen_episode_four_arm_controller_path(tmp_path, ledger):
    # Engineering coverage only: these are scripted fixture games, not the
    # selected fresh scientific frames or empirical results/readiness evidence.
    ledger.allocate_group("full", {"block0": "3", "block1": "3"})
    completed = actions = 0
    for block in range(2):
        bridge, sent, _ = setup(tmp_path, ledger, stage=f"block{block}", root=f"block{block}",
                               allocate=False, maximum_logical=240, rate=(1, 2, 3))
        items = []
        for stratum in ("aligned", "conflict"):
            for item in assignments(institution.ARMS):
                items.append(dict(item, id=f"b{block}-{stratum}-{item['id']}"))
        assert len(items) == 8
        writer = journal.Journal(bridge.root, tuple(items), bridge.protocol, verify=bridge.verify)
        result = execution.execute(tuple(items), respond=lambda req, key: bridge.one(case(key, req)),
            verify=lambda: None, persist=writer.append)
        assert result["completed"] == 8 and not result["global_safety_stop"]
        assert all(a["first_term"]["complete"] and a["two_term"]["complete"] for a in result["assignments"])
        report = audited(bridge)
        assert len(report["physical_reports"]) == len(sent) == 243 and report["reissues"] == 3
        exact = replay.audit(bridge.root, ledger.root, bridge.stage, tuple(items),
                             bridge.protocol, verify=bridge.verify)
        assert exact["report"] == result and exact["physical_attempts"] == 243
        writer.close()
        completed += result["completed"]
        actions += result["logical_attempts"]
        bridge.close()
    assert completed == 16 and actions == 480
    assert ledger.snapshot()["pending"] == 1  # Preserved fabricated old pending.
    assert ledger.snapshot()["uncertified"] == 7  # One old, six failed attempts.


@pytest.mark.parametrize("mode", ("deadline_before", "deadline_after", "four_failures", "content"))
def test_failure_or_deadline_controller_journal_replays_exact_missingness(tmp_path, ledger, mode):
    bridge, _, clock = setup(tmp_path, ledger, rate=(1, 2, 3, 4) if mode == "four_failures" else (),
        bad=(1,) if mode == "content" else (),
        maximum_logical=60,
        duration=policy.BLOCK_DEADLINE_SECONDS if mode == "deadline_after" else 1)
    if mode == "deadline_before":
        clock.now += policy.BLOCK_DEADLINE_SECONDS
    items = assignments()
    writer = journal.Journal(bridge.root, items, bridge.protocol, verify=bridge.verify)
    result = execution.execute(items, respond=lambda req, key: bridge.one(case(key, req)),
                               verify=lambda: None, persist=writer.append)
    exact = replay.audit(bridge.root, ledger.root, bridge.stage, items, bridge.protocol, verify=bridge.verify)
    assert exact["report"] == result
    assert result["global_safety_stop"] is (mode != "content")
    if mode == "content":
        assert result["content_failed"] == 1 and result["completed"] == 1
    else:
        assert result["completed"] == 0
    writer.close()
    bridge.close()


def test_source_change_after_answer_preserves_record_but_refuses_false_closure(tmp_path, ledger):
    bridge, sent, _ = setup(tmp_path, ledger)
    count = [0]
    def verify():
        count[0] += 1
        if count[0] == 3:  # native init, admission, then post-settlement integrity
            raise ValueError("fabricated source change")
        return {}, "f" * 64
    bridge.verify = verify
    with pytest.raises(ValueError, match="source change"):
        bridge.one(case())
    assert len(sent) == 1 and (bridge.root / "calls/logical-a1.json").exists()
    with pytest.raises(ValueError, match="unfinished"):
        audited(bridge)
    bridge.close()
