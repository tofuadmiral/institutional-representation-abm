from copy import deepcopy
import json

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design
from paper3 import retrospective_interface as interface


def trace(raw, name=interface.TOOL_NAME, finish="tool_calls", content=None):
    frame = dict(choices=[dict(index=0, delta=dict(content=content, tool_calls=[dict(
        index=0, id="one", type="function", function=dict(name=name, arguments=raw))]),
        finish_reason=finish)])
    return dict(lines=["data: " + json.dumps(frame), "", "data: [DONE]", ""])


def examples(stage, policy):
    if stage in ("draft", "final"):
        return dict(policy=policy, message="offer")
    if stage == "response":
        return dict(support=True, counter_policy=policy, message="counteroffer")
    return dict(vote=True)


def test_all_thirty_actions_expose_one_function_and_same_system_instruction():
    profile = design.generate(94100).conflict
    seen = []

    def ask(actor, identity, term, stage, context, index):
        messages = interface.messages(profile, "binding_majority", actor, identity, term, stage, context)
        assert messages[0]["content"] == interface.SYSTEM
        request = interface.structured(messages, profile, stage)
        assert len(request["tools"]) == 1 and "response_format" not in request
        assert request["tool_choice"] == "auto"
        seen.append((stage, deepcopy(context)))
        action = examples(stage, 1)
        return interface.decode(profile, stage, trace(json.dumps(action), content="not the action"))

    outcome = institution.episode(profile, "binding_majority", ask)
    assert len(seen) == outcome.calls == 30
    assert all("responses" not in context for stage, context in seen if stage == "response")


@pytest.mark.parametrize("stage", interface.STAGES)
def test_schema_matches_controller_and_rejects_extra_boolean_and_long_message(stage):
    profile = design.generate(94101).aligned
    shape = interface.schema(profile, stage)
    valid = examples(stage, 2)
    assert set(shape["required"]) == set(valid)
    assert not shape["additionalProperties"]
    assert interface.decode(profile, stage, trace(json.dumps(valid))) == valid
    with pytest.raises(ValueError):
        interface.decode(profile, stage, trace(json.dumps(dict(valid, extra=True))))
    if stage in ("draft", "final"):
        with pytest.raises(ValueError):
            interface.decode(profile, stage, trace(json.dumps(dict(valid, policy=True))))
    if "message" in valid:
        with pytest.raises(ValueError):
            interface.decode(profile, stage, trace(json.dumps(dict(valid, message="a" * 129))))


def test_prose_wrong_tool_wrong_finish_duplicate_key_and_json_fence_not_repaired():
    profile = design.generate(94102).aligned
    raw = '{"vote":true}'
    for stream in (trace(raw, name="other"), trace(raw, finish="stop"),
                   trace('{"vote":true,"vote":false}'), trace("```json\n" + raw + "\n```")):
        with pytest.raises(ValueError):
            interface.decode(profile, "vote", stream)
    prose_only = dict(lines=["data: " + json.dumps(dict(choices=[dict(index=0,
        delta=dict(content=raw), finish_reason="stop")])), "", "data: [DONE]", ""])
    with pytest.raises(ValueError):
        interface.decode(profile, "vote", prose_only)


def test_context_identity_game_and_sealed_stage_are_checked():
    profile = design.generate(94103).aligned

    def ask(actor, identity, term, stage, context, index):
        if index == 0:
            for changed in (dict(context, requested=(True,) * 7), dict(context, arm="binding_sum"),
                            dict(context, utilities=()), dict(context, menu_assessments=()),
                            dict(context, history=[{}]),
                            dict(context, occupants=tuple(map(institution.successor, institution.ACTORS)))):
                with pytest.raises(ValueError):
                    interface.messages(profile, "advisory_sum", actor, identity, term, stage, changed)
            with pytest.raises(ValueError, match="identity"):
                interface.messages(profile, "advisory_sum", actor, "wrong", term, stage, context)
        return examples(stage, 1)

    institution.episode(profile, "advisory_sum", ask)


def test_removed_agent_cannot_act_using_forged_second_term_roster_or_history():
    profile = design.generate(94104).conflict

    def ask(actor, identity, term, stage, context, index):
        if term == 1 and stage == "draft":
            changed = dict(context, occupants=("wrong",) * 7)
            with pytest.raises(ValueError, match="officeholder roster"):
                interface.messages(profile, "binding_majority", actor, "wrong", term, stage, changed)
            changed = deepcopy(context)
            changed["history"][0]["executed"] = (False,) * 7
            with pytest.raises(ValueError, match="predecessor history"):
                interface.messages(profile, "binding_majority", actor, identity, term, stage, changed)
        return examples(stage, 1)

    institution.episode(profile, "binding_majority", ask)


def test_unicode_public_text_is_preserved_and_nontext_controls_fail():
    profile = design.generate(94105).aligned
    for message in ("élections\t\n", "😀" * 128, "\\" * 128):
        action = dict(policy=1, message=message)
        assert interface.decode(profile, "draft", trace(json.dumps(action))) == action
    for message in ("bad\x00", "bad\x1f", "bad\x7f", "bad\x85"):
        with pytest.raises(ValueError, match="public text"):
            interface.decode(profile, "draft", trace(json.dumps(dict(policy=1, message=message))))
