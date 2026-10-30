from copy import deepcopy
import json

import pytest

from paper3 import retrospective_action_contract_v2 as prior
from paper3 import retrospective_contract_qualification_v2 as qualification
from paper3 import retrospective_required_tool as candidate


def trace(value, tool=True):
    delta = (dict(tool_calls=[dict(index=0, id="fixture", type="function",
        function=dict(name=prior.TOOL_NAME, arguments=json.dumps(value)))])
        if tool else dict(content=json.dumps(value)))
    frame = dict(choices=[dict(index=0, delta=delta,
                              finish_reason="tool_calls" if tool else "stop")])
    return dict(lines=["data: " + json.dumps(frame), "", "data: [DONE]", ""])


@pytest.mark.parametrize("index", range(18))
def test_changes_only_output_instruction_and_tool_choice(index):
    original = qualification.structured(qualification.cases()[index])
    before = deepcopy(original)
    revised = candidate.fragment(original)
    assert original == before
    assert revised["tools"] == before["tools"]
    assert revised["messages"][1] == before["messages"][1]
    assert revised["tool_choice"] == candidate.CHOICE
    revised["tool_choice"] = "auto"
    revised["messages"][0]["content"] = revised["messages"][0]["content"].replace(
        candidate.INSTRUCTION, prior.NEW)
    assert revised == before


def test_real_tools_only_without_changing_boolean_vote():
    assert candidate.decision(trace(dict(vote=False)))["arguments"] == dict(vote=False)
    with pytest.raises(ValueError, match="actual function"):
        candidate.decision(trace(dict(vote=False), tool=False))


def test_actual_historical_failed_form_still_rejected():
    frame = dict(choices=[dict(index=0, delta=dict(content=
        'submit_decision\n```json\n{"vote": false}\n```'), finish_reason="stop")])
    with pytest.raises(ValueError):
        candidate.decision(dict(lines=["data: " + json.dumps(frame), "",
                                      "data: [DONE]", ""]))


def test_reasoning_markup_is_never_an_executed_tool_call():
    frame = dict(choices=[dict(index=0, delta=dict(content="", reasoning=
        '<｜DSML｜function_calls><｜DSML｜invoke name="submit_decision">'
        '{"vote":false}</｜DSML｜invoke></｜DSML｜function_calls>'), finish_reason="stop")])
    with pytest.raises(ValueError):
        candidate.decision(dict(lines=["data: " + json.dumps(frame), "",
                                      "data: [DONE]", ""]))


def test_advertised_support_does_not_override_runtime_failure():
    endpoint = dict(status=0, supports_tool_choice=dict(function=True),
                    supported_parameters=["reasoning", "tools", "tool_choice"])
    candidate.check_support(endpoint)
    with pytest.raises(ValueError):
        candidate.decision(trace(dict(vote=False), tool=False))


@pytest.mark.parametrize("change", (
    dict(status=-2), dict(supports_tool_choice=dict(function=False)),
    dict(supported_parameters=["tools", "tool_choice"]),
))
def test_unsupported_or_unhealthy_route_fails_before_calls(change):
    endpoint = dict(status=0, supports_tool_choice=dict(function=True),
                    supported_parameters=["reasoning", "tools", "tool_choice"])
    candidate.check_support(endpoint)
    endpoint.update(change)
    with pytest.raises(ValueError):
        candidate.check_support(endpoint)


def test_ambiguous_fragment_not_silently_rewritten():
    original = qualification.structured(qualification.cases()[0])
    original["tools"].append(deepcopy(original["tools"][0]))
    with pytest.raises(ValueError):
        candidate.fragment(original)
