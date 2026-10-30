from copy import deepcopy
import json

import pytest

from paper3 import retrospective_transport_recovery as policy

CONFIG = dict(models=["model", "alias"], provider="provider", output_bound=14000)


def row(finish=None, done=False, usage=False):
    first = dict(id="one", model="alias", provider="provider",
                 choices=[dict(index=0, delta=dict(reasoning="reasoning"), finish_reason=finish)])
    lines = ["data: " + json.dumps(first), ""]
    if usage:
        lines += ["data: " + json.dumps(dict(choices=[], usage=dict(cost=.001,
                                               prompt_tokens=100, completion_tokens=100))), ""]
    if done:
        lines += ["data: [DONE]", ""]
    return dict(stream=dict(http_status=200, error_type=None, secret_redacted=False, lines=lines),
                result=dict(exact=False, valid_action=False), receipts=[])


def eligible(value, **extra):
    return policy.eligibility(value, CONFIG, attempt_number=extra.get("attempt", 1),
                              recoveries_used=extra.get("used", 0))["eligible"]


def test_incomplete_eof_blind_to_answer_and_assessment_contents():
    value = row()
    assert eligible(value)
    for exact in (True, False, None):
        changed = deepcopy(value)
        changed.update(result=dict(exact=exact, action=dict(policy=5)),
                       final_content="malformed or entirely correct or hypothesis-favorable",
                       assessment=dict(passed=exact))
        assert policy.eligibility(changed, CONFIG, attempt_number=1, recoveries_used=0) == (
            policy.eligibility(value, CONFIG, attempt_number=1, recoveries_used=0))


@pytest.mark.parametrize("finish", ["tool_calls", "stop", "length", "error"])
def test_any_terminal_not_recoverable_even_wrong_or_uncertified(finish):
    assert not eligible(row(finish=finish))
    assert not eligible(row(finish=finish, done=True, usage=True))


def test_completed_response_no_recovery_for_billing_or_native_failure():
    value = row(finish="tool_calls", done=True, usage=True)
    value.update(result=dict(exact=False, action=None), receipts=[dict(http_status=404)])
    assert not eligible(value)


def test_finite_attempt_and_global_caps():
    assert not eligible(row(), attempt=2)
    assert not eligible(row(), used=2)
    assert not eligible(row(), used=-1)
    assert not eligible(row(), attempt=True)
    assert not eligible(row(), used=True)
    assert eligible(row(), used=1)


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_http_transport_failures_only_with_no_terminal(status):
    value = row()
    value["stream"].update(http_status=status, error_type="HTTPError", lines=[])
    assert eligible(value)
    value["stream"]["lines"] = row(finish="stop")["stream"]["lines"]
    assert not eligible(value)


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404])
def test_fatal_http_errors_not_recoverable(status):
    value = row()
    value["stream"].update(http_status=status, error_type="HTTPError", lines=[])
    assert not eligible(value)


def test_route_redaction_malformed_and_done_conflicts_stop():
    for mutation in (dict(secret_redacted=True), dict(error_type="ValueError"),
                     dict(generation_header="different"),
                     dict(lines=['data: {"id":"one","model":"other","provider":"provider"}', ""]),
                     dict(lines=['data: {"id":"one","model":"alias","provider":"other"}', ""]),
                     dict(lines=["data: broken-json", ""]),
                     dict(lines=['data: {"error":{"message":"server failure"}}', ""]),
                     dict(lines=["data: [DONE]", ""])):
        value = row()
        value["stream"].update(mutation)
        assert not eligible(value)


def test_unclassified_or_instrument_errors_stop():
    value = row()
    value["instrument_error"] = "ValueError"
    assert not eligible(value)
    assert not eligible({})
    value = row()
    value["stream"]["lines"] = []
    assert not eligible(value)


@pytest.mark.parametrize("delta", [dict(content="possibly wrong or correct"),
    dict(tool_calls=[dict(index=0, function=dict(arguments="{partial"))]),
    dict(function_call=dict(name="submit_decision")), dict(refusal="refused")])
def test_no_reissue_of_any_answer_fragment_before_terminal(delta):
    value = row()
    frame = json.loads(value["stream"]["lines"][0][6:])
    frame["choices"][0]["delta"].update(delta)
    value["stream"]["lines"][0] = "data: " + json.dumps(frame)
    assert not eligible(value)


def test_nonzero_or_boolean_choice_indices_not_recoverable():
    for index in (1, False):
        value = row()
        frame = json.loads(value["stream"]["lines"][0][6:])
        frame["choices"][0]["index"] = index
        value["stream"]["lines"][0] = "data: " + json.dumps(frame)
        assert not eligible(value)
