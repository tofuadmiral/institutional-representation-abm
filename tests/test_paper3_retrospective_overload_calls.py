"""Fabricated transport only: no API key, live route or paid allocation."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from threading import Barrier, Event, Lock, Thread

import pytest

from experiments import paper3_transport_diagnostic as t
from paper3 import hosted_reasoning_channel_calls as service
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_keyed_interface as interface
from paper3 import retrospective_overload_calls as coordinator
from paper3 import retrospective_overload_requests as requests
from paper3 import retrospective_deepseek_route as route
from paper3.pivot_b_budget import BUDGET_ID, atomic
from tests.test_paper3_retrospective_overload_recovery import rejection


def fixture_cases():
    assignment = requests.assignments()[0]
    cases = []

    def ask(actor, identity, term, stage, context, index):
        request = requests.action_request(assignment, actor, identity, term, stage, context, index)
        bound = route.reservation(request)
        cases.append(dict(id=f"fixture-{index:02d}", request=request, **bound,
            request_sha256=t.sha(bound["request_text"].encode()),
            context=dict(stage=stage, index=index)))
        if stage in ("draft", "final"):
            return dict(policy=0, message="fabricated")
        if stage == "response":
            return dict(support=False, counter_policy=0, message="fabricated")
        return dict(vote=False)

    institution.episode(assignment["game"], assignment["arm"], ask)
    return assignment["game"], cases


@pytest.fixture
def fixture(tmp_path):
    game, cases = fixture_cases()
    root, ledger = tmp_path / "run", tmp_path / "ledger"
    (ledger / "entries").mkdir(parents=True)
    atomic(ledger / "authority.json", dict(budget_id=BUDGET_ID, cap_usd="10.00",
                                         credit_purchases_authorized=False))
    atomic(ledger / "entries/old-pending.json", dict(stage="old", status="reserved", reserved_usd=".01"))
    atomic(ledger / "entries/old-uncertified.json", dict(stage="old", status="settled",
        reserved_usd=".01", accounted_usd=".01", certified=False))
    coordinator.StopLedger(ledger).allocate("fixture", "3.20")
    now, sent = [1000.0], []
    choices = []

    def sleep(seconds):
        now[0] += seconds

    def score(row, case):
        result = dict(usable=False, valid_action=False, exact=False, action=None)
        if row.get("instrument_error") or "assessment" not in row:
            return result
        assessed = service.assess(row, coordinator.recovery.CONFIG)
        usable = assessed["passed"] and assessed["stream"]["finish_reasons"] == ["tool_calls"] and (
            service.native_evidence(assessed["stream"])["present"])
        result["usable"] = usable
        if usable:
            try:
                action = interface.decode(game, case["context"]["stage"], row["stream"])
                result.update(valid_action=True, exact=True, action=action)
            except (ValueError, TypeError, KeyError):
                pass
        return result

    def send(wire, secret):
        sent.append(dict(wire=wire, at=now[0]))
        kind = choices.pop(0) if choices else "valid"
        if kind in ("429", "quota", "502", "fragment"):
            stream = rejection()["stream"]
            stream.update(started_unix=now[0], ended_unix=now[0])
            if kind == "quota":
                error = json.loads(stream["http_error_body"])
                error["error"]["metadata"]["limit_source"] = "account"
                stream["http_error_body"] = json.dumps(error)
            if kind == "502":
                stream["http_status"] = 502
            if kind == "fragment":
                stream["lines"], stream["line_count"] = ["data: fragment"], 1
            return stream
        request = json.loads(wire)
        stage = json.loads(request["messages"][1]["content"])["stage"]
        action = (dict(policy=0, message="fabricated") if stage in ("draft", "final") else
                  dict(support=False, counter_policy=0, message="fabricated") if stage == "response" else
                  dict(vote=False))
        if kind == "bad":
            action["extra"] = True
        frames = [dict(id=f"fabricated-{len(sent)}", model=route.MODEL_ALIAS, provider=route.PROVIDER,
            choices=[dict(index=0, delta=dict(reasoning="" if kind == "no_native" else "fabricated"),
                          finish_reason=None)]),
            dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0, id="one", type="function",
                function=dict(name="submit_decision", arguments=json.dumps(action)))]), finish_reason="tool_calls")]),
            dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=100, cost=.0001))]
        if kind == "prose":
            frames[1] = dict(choices=[dict(index=0, delta=dict(content=json.dumps(action)), finish_reason="stop")])
        return dict(http_status=200, error_type=None, secret_redacted=False,
            lines=[line for f in frames for line in ("data: " + json.dumps(f), "")] + ["data: [DONE]", ""],
            started_unix=now[0], ended_unix=now[0])

    def lookup(gid, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
            data=dict(id=gid, model=route.MODEL_ALIAS, provider_name=route.PROVIDER, total_cost=.0001))

    def make():
        return coordinator.Calls(root, ledger, "fixture", lambda: (None, "fixture-protocol"), score,
            send=send, lookup=lookup, clock=lambda: now[0], sleep=sleep)

    def audit():
        return coordinator.audit(root, ledger, "fixture", "fixture-protocol", score)

    return dict(root=root, ledger=ledger, cases=cases, choices=choices, now=now,
                sent=sent, make=make, audit=audit, score=score)


def test_identical_wire_reissue_retains_failed_reservation_and_old_entries(fixture):
    f = fixture
    before = {p.name: p.read_bytes() for p in (f["ledger"] / "entries").glob("old-*.json")}
    f["choices"].extend(["429", "valid"])
    calls = f["make"]()
    result = calls.one(f["cases"][0])
    assert result["status"] == "recorded" and result["selected_id"] == "fixture-00-a2"
    assert f["sent"][0]["wire"] == f["sent"][1]["wire"]
    assert f["sent"][1]["at"] - f["sent"][0]["at"] == 60
    report = f["audit"]()
    assert report["physical_calls"] == 2 and report["recoveries"] == 1 and not report["global_safety_stop"]
    assert Decimal(report["accounted_usd"]) == Decimal(f["cases"][0]["reserved_usd"]) + Decimal(".0001")
    assert not report["publication_evidence"]
    assert before == {name: (f["ledger"] / "entries" / name).read_bytes() for name in before}
    assert calls.ledger.snapshot()["uncertified"] == 2
    with pytest.raises(ValueError, match="restart"):
        f["make"]()
    with pytest.raises(ValueError, match="already assigned"):
        calls.one(f["cases"][0])


@pytest.mark.parametrize("kind", ["bad", "no_native", "prose", "quota", "502", "fragment"])
def test_noneligible_failure_never_reissues_and_stops_new_logical_actions(fixture, kind):
    f = fixture
    f["choices"].append(kind)
    calls = f["make"]()
    assert calls.one(f["cases"][0])["status"] == "failed"
    assert calls.one(f["cases"][1])["status"] == "not_started"
    report = f["audit"]()
    assert report["physical_calls"] == 1 and report["recoveries"] == 0 and report["global_safety_stop"]


def test_second_overload_is_terminal_no_third_attempt(fixture):
    f = fixture
    f["choices"].extend(["429", "429", "valid"])
    calls = f["make"]()
    assert calls.one(f["cases"][0])["status"] == "failed"
    report = f["audit"]()
    assert report["physical_calls"] == 2 and report["recoveries"] == 1 and report["global_safety_stop"]
    assert f["choices"] == ["valid"]
    assert Decimal(report["accounted_usd"]) == 2 * Decimal(f["cases"][0]["reserved_usd"])


def test_global25_reissues_not25_per_action(fixture):
    f = fixture
    calls = f["make"]()
    for i in range(25):
        f["choices"].extend(["429", "valid"])
        assert calls.one(f["cases"][i])["status"] == "recorded"
    f["choices"].extend(["429", "valid"])
    assert calls.one(f["cases"][25])["status"] == "failed"
    report = f["audit"]()
    assert report["physical_calls"] == 51 and report["recoveries"] == 25 and report["global_safety_stop"]
    assert len(f["sent"]) == 51 and f["choices"] == ["valid"]


@pytest.mark.parametrize("mutation", ["delay", "ordinal", "wire", "filename", "logical", "charge", "stop"])
def test_independent_component_audit_rejects_evidence_tampering(fixture, mutation):
    f = fixture
    f["choices"].extend(["429", "valid"])
    calls = f["make"]()
    calls.one(f["cases"][0])
    f["audit"]()
    if mutation in ("delay", "ordinal", "wire", "filename"):
        path = f["root"] / "recoveries/fixture-00-a1.json"
        row = t.load(path)
        if mutation == "filename":
            path.rename(path.with_name("wrong.json"))
        else:
            key = {"delay": "not_before_unix", "ordinal": "ordinal", "wire": "request_sha256"}[mutation]
            row[key] = "0" * 64 if mutation == "wire" else row[key] + 1
            atomic(path, row)
    elif mutation == "logical":
        path = f["root"] / "logicals/fixture-00.json"
        row = t.load(path)
        row["action"]["policy"] = 1
        atomic(path, row)
    elif mutation == "charge":
        path = f["ledger"] / "entries/fixture-fixture-00-a1.json"
        row = t.load(path)
        row["accounted_usd"] = "0"
        atomic(path, row)
    else:
        atomic(f["root"] / "sessions/transport_stop.json", dict(protocol="fixture-protocol"))
    with pytest.raises((ValueError, KeyError)):
        f["audit"]()


def test_invalid_answer_sets_stop_before_waiting_for_admission_lock(fixture):
    f = fixture
    calls = f["make"]()
    entered = Event()
    # The score callback can observe an invalid answer while another worker
    # holds the admission/cooldown lock. Stop must become visible immediately.
    def invalid():
        entered.set()
        calls.execution_score(dict(status="recorded", instrument_error="fixture"),
                              coordinator.physical(f["cases"][0], 1))
    with calls.guard:
        worker = Thread(target=invalid)
        worker.start()
        assert entered.wait(2)
        assert calls.stop.wait(2)
    worker.join(2)
    assert not worker.is_alive()


def test_logical_limit_stops_before_send(fixture):
    f = fixture
    calls = f["make"]()
    for i in range(coordinator.MAX_LOGICAL):
        case = deepcopy(f["cases"][0])
        case["id"] = f"limit-{i}"
        calls.one(case)
    with pytest.raises(ValueError, match="logical action ceiling"):
        calls.one(f["cases"][1])
    assert f["audit"]()["physical_calls"] == 240


def test_second_attempt_cannot_change_wire(fixture):
    case = fixture["cases"][0]
    first, second = coordinator.physical(case, 1), coordinator.physical(case, 2)
    assert first["request"] == second["request"] == case["request"]
    assert first["request_text"] == second["request_text"] and first["request_sha256"] == second["request_sha256"]
    assert first["context"]["logical_attempt"] == 1 and second["context"]["logical_attempt"] == 2
    case = deepcopy(case)
    case["context"]["logical_id"] = "ambiguous"
    with pytest.raises(ValueError, match="ambiguous"):
        coordinator.physical(case, 1)


def test_four_workers_share_recovery_counter_and_admission_cooldown(fixture):
    f = fixture
    calls = f["make"]()
    first_requests = Barrier(4)
    guard, counts, original = Lock(), {}, calls.send

    def send(wire, secret):
        with guard:
            counts[wire] = counts.get(wire, 0) + 1
            attempt = counts[wire]
        if attempt == 1:
            first_requests.wait(timeout=5)
            stream = rejection()["stream"]
            stream.update(started_unix=f["now"][0], ended_unix=f["now"][0])
            return stream
        with guard:
            return original(wire, secret)

    calls.send = send
    with ThreadPoolExecutor(max_workers=4) as workers:
        futures = [workers.submit(calls.one, case) for case in f["cases"][:4]]
        outcomes = [future.result(timeout=10) for future in futures]
    assert all(row["status"] == "recorded" for row in outcomes)
    report = f["audit"]()
    assert report["recoveries"] == 4 and report["physical_calls"] == 8
    assert not report["global_safety_stop"] and calls.recoveries == 4


def test_budget_admission_failure_preserves_assignment_without_sending(fixture):
    f = fixture
    path = f["ledger"] / "stages/fixture.json"
    stage = t.load(path)
    stage["cap_usd"] = ".00005"  # fabricated authority, never a live ledger edit
    atomic(path, stage)
    calls = f["make"]()
    assert calls.one(f["cases"][0])["status"] == "failed"
    assert not f["sent"]
    report = f["audit"]()
    assert report["physical_calls"] == 0 and report["global_safety_stop"]
    assert report["logical_actions"] == 1 and report["accounted_usd"] == "0"
