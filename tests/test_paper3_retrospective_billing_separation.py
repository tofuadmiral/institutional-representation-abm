from copy import deepcopy
from decimal import Decimal
import json

import pytest

from paper3 import retrospective_billing_separation as billing
from paper3 import hosted_reasoning_calls as old
from paper3 import retrospective_contract_route_v2 as route

CONFIG = dict(models=[route.MODEL, route.MODEL_ALIAS], provider=route.PROVIDER, output_bound=14000)


def row():
    frames = [dict(id="one", model=route.MODEL, provider=route.PROVIDER,
        choices=[dict(index=0, delta=dict(reasoning="fixture"), finish_reason=None)]),
        dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0, id="call", type="function",
            function=dict(name="submit_decision", arguments='{"vote":true}'))]), finish_reason="tool_calls")]),
        dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=100, cost=.0001))]
    return dict(reserved_usd="0.01", input_token_bound=1000,
        stream=dict(http_status=200, error_type=None, secret_redacted=False,
            lines=[x for f in frames for x in ("data: " + json.dumps(f), "")] + ["data: [DONE]", ""]),
        receipts=[dict(http_status=404, error_type="HTTPError", data=None,
            secret_redacted=False, scheduled_offset_seconds=n) for n in billing.OFFSETS])


def test_only_absent_billing_is_separated_with_entire_reservation():
    r = row()
    before = deepcopy(r)
    assert not old.assess(r, CONFIG)["passed"]
    a = billing.assess(r, CONFIG)
    assert a["passed"] and not a["billing_passed"] and not a["receipt_certified"]
    assert a["accounted_usd"] == r["reserved_usd"] and a["certified_cost_usd"] is None
    assert a["billing_separation"]["uncertified_full_reservation"]
    assert r == before


@pytest.mark.parametrize("field,value", [("http_status",503),("http_status",200),
    ("secret_redacted",True),("error_type",None),("data",{}),("scheduled_offset_seconds",1)])
def test_other_receipt_failures_do_not_get_inference_retry_or_acceptance(field,value):
    r = row()
    r["receipts"][0][field] = value
    assert not billing.assess(r, CONFIG)["passed"]


def test_missing_duplicate_or_reordered_receipt_observations_fail_closed():
    for receipts in (row()["receipts"][:3], row()["receipts"] * 2, list(reversed(row()["receipts"]))):
        r = row()
        r["receipts"] = receipts
        assert not billing.assess(r, CONFIG)["passed"]


@pytest.mark.parametrize("mutate", [
    lambda r:r["stream"].update(http_status=502),
    lambda r:r["stream"].update(error_type="TimeoutError"),
    lambda r:r["stream"].update(secret_redacted=True),
    lambda r:r["stream"].update(lines=r["stream"]["lines"][:-2]),
    lambda r:r["stream"].update(lines=[s.replace('"tool_calls"}', '"length"}') for s in r["stream"]["lines"]]),
    lambda r:r["stream"].update(lines=[s.replace('"AtlasCloud"', '"wrong-provider"') for s in r["stream"]["lines"]]),
    lambda r:r["stream"].update(lines=[s.replace('"prompt_tokens": 100', '"prompt_tokens": 1000000') for s in r["stream"]["lines"]]),
    lambda r:r["stream"].update(lines=[s.replace('"cost": 0.0001', '"cost": 5.0') for s in r["stream"]["lines"]]),
])
def test_invalid_stream_stays_invalid_even_with_four404(mutate):
    r = row()
    mutate(r)
    a = billing.assess(r, CONFIG)
    # A length-finished stream passes cost accounting but not scientific action
    # completion in the runner; explicitly test that separate layer below.
    if a["stream"]["finish_reasons"] == ["length"]:
        assert a["length_ending"]
    else:
        assert not a["passed"]


def test_certified_receipt_same_cost_and_conflicting_cost_identity_are_distinct():
    r = row()
    r["receipts"] = [dict(http_status=200, error_type=None, secret_redacted=False,
        scheduled_offset_seconds=0,data=dict(id="one",model=route.MODEL,
            provider_name=route.PROVIDER,total_cost=.0001))]
    a = billing.assess(r, CONFIG)
    assert a["passed"] and a["billing_passed"] and a["receipt_certified"]
    assert Decimal(a["accounted_usd"]) == Decimal(".0001")
    assert not a["billing_separation"]["four_404_absence"]
    for field,value in [("id","wrong"),("provider_name","wrong"),("total_cost",.0002)]:
        bad = deepcopy(r)
        bad["receipts"][0]["data"][field] = value
        a = billing.assess(bad, CONFIG)
        assert not a["passed"] and not a["receipt_certified"]
        assert a["accounted_usd"] == "0.01"


def test_unknown_failure_then_valid_receipt_cannot_bypass_scientific_stop():
    r = row()
    r["receipts"] = [dict(http_status=503,error_type="HTTPError",data=None,
        secret_redacted=False,scheduled_offset_seconds=0),
        dict(http_status=200,error_type=None,secret_redacted=False,scheduled_offset_seconds=20,
            data=dict(id="one",model=route.MODEL,provider_name=route.PROVIDER,total_cost=.0001))]
    assert old.assess(r,CONFIG)["passed"]
    a = billing.assess(r,CONFIG)
    assert not a["passed"] and not a["billing_separation"]["receipt_sequence_allowed"]
    assert a["receipt_certified"]  # Expense evidence never fabricates a valid action.


@pytest.mark.parametrize("kind", ["length", "no_native", "illegal_action", "dual_channel"])
def test_four404_never_makes_an_invalid_scientific_action_valid(kind):
    from experiments import paper3_retrospective_billing_discovery_v1 as runner
    r = row()
    if kind == "length":
        r["stream"]["lines"] = [s.replace('"finish_reason": "tool_calls"',
            '"finish_reason": "length"') for s in r["stream"]["lines"]]
    elif kind == "no_native":
        r["stream"]["lines"] = [s.replace('"reasoning": "fixture"', '"reasoning": ""')
            for s in r["stream"]["lines"]]
    elif kind == "illegal_action":
        r["stream"]["lines"] = [s.replace('true', '0') for s in r["stream"]["lines"]]
    else:
        r["stream"]["lines"].insert(-2, 'data: ' + json.dumps(dict(choices=[dict(index=0,
            delta=dict(content='{"vote":true}'), finish_reason=None)])))
        r["stream"]["lines"].insert(-2, '')
    r.update(assessment={}, request=dict(reasoning=dict(enabled=True,exclude=False)))
    case = dict(context=dict(assignment_id=runner.requests.assignments()[0]["id"],stage="vote"))
    assert not runner.score(r,case)["valid_action"]
