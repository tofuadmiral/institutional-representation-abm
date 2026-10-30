"""Fabricated row/replay engineering only; no network, model or allocation."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_billing_calls as service
from paper3 import retrospective_contract_route_v2 as route
from paper3 import retrospective_independent_execution as engine
from tests.test_paper3_retrospective_score_ledger import fixture


def action(request):
    stage = json.loads(request["messages"][1]["content"])["stage"]
    if stage in ("draft", "final"):
        return dict(policy=1, message="fabricated")
    if stage == "response":
        return dict(support=False, counter_policy=0, message="fabricated")
    return dict(vote=True)


def row(request, identifier, *, value=None, raw=None, native=True, channel="tool",
        absent=False, bad_count=False, provider=None):
    bound = route.reservation(request)
    text = json.dumps(action(request) if value is None else value) if raw is None else raw
    finish = "tool_calls" if channel in ("tool", "both") else "stop"
    delta = (dict(tool_calls=[dict(index=0, id="one", type="function",
        function=dict(name="submit_decision", arguments=text))])
        if channel in ("tool", "both") else dict(content=text))
    if channel == "both":
        delta["content"] = text
    frames = [dict(id=identifier, model=route.MODEL_ALIAS,
        provider=provider or route.PROVIDER, choices=[dict(index=0,
        delta=dict(reasoning="fabricated" if native else ""), finish_reason=None)]),
        dict(choices=[dict(index=0, delta=delta, finish_reason=finish)]),
        dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=100, cost=.0001,
            completion_tokens_details=dict(reasoning_tokens=101 if bad_count else 80)))]
    trace = dict(http_status=200, error_type=None, secret_redacted=False,
        started_unix=1000, ended_unix=1001,
        lines=[line for frame in frames for line in ("data: " + json.dumps(frame), "")]
              + ["data: [DONE]", ""])
    receipts = ([dict(http_status=404, error_type="HTTPError", data=None,
        secret_redacted=False, scheduled_offset_seconds=offset) for offset in (0, 20, 40, 60)]
        if absent else [dict(http_status=200, error_type=None, secret_redacted=False,
            scheduled_offset_seconds=0, data=dict(id=identifier, model=route.MODEL_ALIAS,
                provider_name=route.PROVIDER, total_cost=.0001))])
    evidence = dict(id=identifier, status="recorded", request=deepcopy(request),
        **bound, request_sha256=sha256(bound["request_text"].encode()).hexdigest(),
        stream=trace, receipts=receipts)
    evidence["assessment"] = service.assess(evidence, engine.CONFIG)
    return evidence


def assignments(arms=("binding_majority", "binding_sum")):
    game = fixture(2)
    return tuple(dict(id=f"offline-{i}", game=game, arm=arm, seed_base=3980000 + 64 * i)
                 for i, arm in enumerate(arms))


def run(items=None, *, bad_at=None, mutation=None, throw_at=None,
        verify=None, persist=None):
    items = assignments() if items is None else items
    sent, events = [], []
    def respond(request, identifier):
        sent.append((deepcopy(request), identifier))
        if len(sent) == throw_at:
            raise RuntimeError("unknown response failure")
        if len(sent) == bad_at:
            value = action(request)
            if "policy" in value:
                value["policy"] = True
            elif "support" in value:
                value["support"] = 1
            else:
                value["vote"] = 1
            saved = row(request, identifier, value=value)
        else:
            saved = row(request, identifier)
        if mutation and len(sent) == 1:
            mutation(saved)
        return saved
    def save(event):
        events.append(deepcopy(event))
        if persist:
            persist(event)
    result = engine.execute(items, respond=respond, verify=verify or (lambda: None),
                            persist=save)
    return result, sent, events


@pytest.mark.parametrize("arm", institution.ARMS)
def test_full_two_term_controller_preserves_requested_actions_roles_and_public_history(arm):
    result, sent, events = run(assignments((arm,)))
    record = result["assignments"][0]
    assert result["completed"] == 1 and not result["global_safety_stop"]
    assert len(sent) == result["logical_attempts"] == 30
    assert all(s["status"] == "recorded_valid" for s in record["logicals"])
    expected = institution.episode(fixture(2), arm, lambda a, i, t, s, c, n:
        dict(policy=1, message="fabricated") if s in ("draft", "final") else
        dict(support=False, counter_policy=0, message="fabricated") if s == "response" else
        dict(vote=True))
    assert record["outcome"] == expected
    assert record["first_term"]["complete"] and record["two_term"]["complete"]
    assert all(t.requested == t.executed for t in record["terms"])
    for slot in record["logicals"]:
        payload = json.loads(slot["request"]["messages"][1]["content"])
        assert len(payload["history"]) == slot["term"]
        if slot["stage"] == "response":
            assert "responses" not in payload
        assert "requested" not in payload and "executed" not in payload
        assert payload["score_ledger"]["districts"][f"district_{slot['actor']}"]["acting_identity"] == slot["identity"]
    assert events[0]["event"] == "inventory" and events[-1]["event"] == "terminal"
    assert not result["allocation_authorized"] and not result["publication_evidence"]


@pytest.mark.parametrize("bad_index", range(30))
def test_every_safe_content_failure_retains_prefix_and_continues_independent_assignment(bad_index):
    result, sent, events = run(bad_at=bad_index + 1)
    first, second = result["assignments"]
    assert result["content_failed"] == 1 and result["completed"] == 1
    assert not result["global_safety_stop"]
    assert first["status"] == "content_failed" and second["status"] == "completed"
    assert len(sent) == bad_index + 1 + 30
    assert first["logicals"][bad_index]["status"] == "content_failed"
    assert first["logicals"][bad_index]["classification"]["instrument_safe"]
    assert first["logicals"][bad_index]["evidence"] is not None
    assert all(s["status"] == "not_started" for s in first["logicals"][bad_index + 1:])
    assert first["outcome"] is None
    assert first["first_term"]["complete"] is (bad_index >= 15)
    assert not first["two_term"]["complete"]
    assert len(first["two_term"]["citizen_utility_bounds"]) == 7
    assert all(len(r) == 9 for r in first["two_term"]["citizen_utility_bounds"])
    assert events[-1]["report"]["assigned"] == 2
    assert {identifier for _, identifier in sent} == {
        *(f"offline-0-{i:02d}" for i in range(bad_index + 1)),
        *(f"offline-1-{i:02d}" for i in range(30))}


@pytest.mark.parametrize("failure", ("native", "count", "provider", "both", "done",
    "request", "hash", "bound", "assessment", "id", "receipt503", "mixed_receipt"))
def test_instrument_or_unknown_billing_failures_stop_globally_not_just_the_episode(failure):
    def mutation(saved):
        request = saved["request"]
        options = dict(native=False) if failure == "native" else (
            dict(bad_count=True) if failure == "count" else
            dict(provider="wrong") if failure == "provider" else
            dict(channel="both") if failure == "both" else {})
        if options:
            saved.update(row(request, saved["id"], **options))
        if failure == "done":
            saved["stream"]["lines"] = saved["stream"]["lines"][:-2]
        elif failure == "request":
            saved["request"]["reasoning"]["enabled"] = 1
        elif failure == "hash":
            saved["request_sha256"] = "wrong"
        elif failure == "bound":
            saved["input_token_bound"] = True
        elif failure == "assessment":
            saved["assessment"]["passed"] = 1
        elif failure == "id":
            saved["id"] = "wrong"
        elif failure in ("receipt503", "mixed_receipt"):
            unknown = dict(http_status=503, error_type="HTTPError", data=None,
                           secret_redacted=False, scheduled_offset_seconds=0)
            saved["receipts"] = [unknown] + (
                [dict(**{k: v for k, v in saved["receipts"][0].items()
                    if k != "scheduled_offset_seconds"}, scheduled_offset_seconds=20)]
                if failure == "mixed_receipt" else [])
        if failure not in ("request", "hash", "bound", "assessment", "id"):
            saved["assessment"] = service.assess(saved, engine.CONFIG)
    result, sent, _ = run(mutation=mutation)
    first, second = result["assignments"]
    assert len(sent) == 1 and result["global_safety_stop"]
    assert first["status"] == "unsafe_failed" and second["status"] == "not_started"
    assert all(s["status"] == "not_started" for s in second["logicals"])
    assert first["logicals"][0]["evidence"] is not None
    assert result["completed"] == 0


def test_source_divergence_after_response_retains_evidence_but_never_executes_action():
    calls = [0]
    def verify():
        calls[0] += 1
        # Entry/prepared/pre-response/post-response guards.
        if calls[0] == 4:
            raise ValueError("source changed")
    result, sent, _ = run(verify=verify)
    first = result["assignments"][0]
    assert len(sent) == 1 and result["global_safety_stop"]
    assert first["logicals"][0]["evidence"] is not None
    assert first["logicals"][0]["classification"] is None
    assert first["terms"] == [None, None]


def test_unknown_response_exception_never_invokes_another_case_or_response_retry():
    result, sent, _ = run(throw_at=1)
    assert len(sent) == 1 and result["global_safety_stop"]
    assert result["assignments"][1]["status"] == "not_started"


def test_persistence_failure_after_evidence_stops_before_action_or_next_assignment():
    raised = [False]
    def persist(event):
        if event["event"] == "evidence" and not raised[0]:
            raised[0] = True
            raise OSError("persistence failed")
    result, sent, _ = run(persist=persist)
    assert len(sent) == 1 and result["global_safety_stop"]
    first = result["assignments"][0]
    assert first["logicals"][0]["evidence"] is not None
    assert first["logicals"][0]["classification"] is None
    assert first["outcome"] is None


def request_for_test():
    captured = []
    def ask(actor, identity, term, stage, context, index):
        if index == 0:
            captured.append(engine.requests.action_request(fixture(2), "binding_sum",
                3980000, actor, identity, term, stage, context, index))
        if stage in ("draft", "final"):
            return dict(policy=1, message="")
        if stage == "response":
            return dict(support=False, counter_policy=0, message="")
        return dict(vote=True)
    institution.episode(fixture(2), "binding_sum", ask)
    return captured[0]


@pytest.mark.parametrize("raw", ('{"policy":1,"policy":1,"message":""}',
    "explanation then JSON", '{"policy":true,"message":""}', '{"policy":1}'))
def test_clean_complete_illegal_content_is_local_not_inferred_or_coerced(raw):
    request = request_for_test()
    saved = row(request, "offline-0-00", raw=raw)
    result = engine.classify(saved, request, fixture(2), "draft")
    assert result["status"] == "content_failed" and result["instrument_safe"]
    assert result["action"] is None and result["execution"] is None


def test_four404_preserves_full_reservation_and_approved_raw_vs_executed_text():
    request = request_for_test()
    saved = row(request, "offline-0-00", value=dict(policy=1, message="a" * 140), absent=True)
    before = deepcopy(saved)
    result = engine.classify(saved, request, fixture(2), "draft")
    assert saved == before
    assert result["status"] == "recorded_valid"
    assert result["execution"]["requested_characters"] == 140
    assert result["execution"]["executed_characters"] == 128
    assert result["execution"]["requested_action"]["message"] == "a" * 140
    assert result["action"]["message"] == "a" * 128
    assert result["assessment"]["accounted_usd"] == saved["reserved_usd"]
    assert not result["assessment"]["receipt_certified"]


def test_illegal_unexecuted_suffix_remains_failed_no_silent_prefix_repair():
    request = request_for_test()
    saved = row(request, "offline-0-00", value=dict(policy=1, message="a" * 128 + "\x00"))
    result = engine.classify(saved, request, fixture(2), "draft")
    assert result["status"] == "content_failed" and result["action"] is None


def test_unencodable_executed_message_is_failed_before_future_wire_construction():
    request = request_for_test()
    saved = row(request, "offline-0-00", value=dict(policy=1, message="\ud800"))
    result = engine.classify(saved, request, fixture(2), "draft")
    assert result["status"] == "content_failed" and result["action"] is None


def test_undeclared_duplicate_assignment_rejected_before_response_or_persistence():
    called = []
    item = assignments()[0]
    with pytest.raises(ValueError, match="unique"):
        engine.execute((item, item), respond=lambda *x: called.append("response"),
                       verify=lambda: None, persist=lambda x: called.append("persist"))
    assert not called


@pytest.mark.parametrize("field", ("reasoning", "temperature", "max_tokens", "provider", "tool"))
def test_classifier_rejects_unqualified_expected_request_even_with_matching_saved_row(field):
    request = request_for_test()
    if field == "reasoning":
        request[field]["enabled"] = 1  # Python equality would accept as True.
    elif field == "temperature":
        request[field] = 0
    elif field == "max_tokens":
        request[field] = 500
    elif field == "tool":
        request["tools"][0]["function"]["description"] = "Different description"
    else:
        request[field]["allow_fallbacks"] = True
    saved = row(request, "offline-0-00")
    result = engine.classify(saved, request, fixture(2), "draft")
    assert result["status"] == "unsafe_failed" and not result["instrument_safe"]


def test_negative_verification_return_stops_before_first_response():
    result, sent, _ = run(verify=lambda: False)
    assert not sent and result["global_safety_stop"]
    assert result["assignments"][1]["status"] == "not_started"


@pytest.mark.parametrize("field", ("game_id", "office_value", "chairs", "acting_identity",
                                  "acting_district", "assessment_binding", "selected_assessment"))
def test_classifier_rejects_changed_role_or_economic_metadata_in_expected_prompt(field):
    request = request_for_test()
    payload = json.loads(request["messages"][1]["content"])
    payload[field] = dict(game_id="different", office_value=99, chairs=[1, 3],
        acting_identity="successor-r0", acting_district=True, assessment_binding=1,
        selected_assessment="majority")[field]
    request["messages"][1]["content"] = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    saved = row(request, "offline-0-00")
    result = engine.classify(saved, request, fixture(2), "draft")
    assert result["status"] == "unsafe_failed" and not result["instrument_safe"]
