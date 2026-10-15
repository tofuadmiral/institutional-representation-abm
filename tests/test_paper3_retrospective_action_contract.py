from copy import deepcopy
from dataclasses import asdict
import json

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_action_contract as contract
from paper3 import retrospective_electorates as design
from paper3 import retrospective_interface as original
from paper3 import retrospective_keyed_interface as keyed


def stream(raw, channel="json", finish=None):
    if channel == "tool":
        delta = dict(tool_calls=[dict(index=0, id="one", type="function",
                                     function=dict(name="submit_decision", arguments=raw))])
        finish = finish or "tool_calls"
    else:
        delta = dict(content=("submit_decision\n" if channel == "labelled_json" else "") + raw)
        finish = finish or "stop"
    frame = dict(choices=[dict(index=0, delta=delta, finish_reason=finish)])
    return pack([frame])


def pack(frames):
    return dict(lines=[line for frame in frames for line in ("data: " + json.dumps(frame), "")]
                + ["data: [DONE]", ""])


def action(stage, policy=4):
    if stage in ("draft", "final"):
        return dict(policy=policy, message="fixture é\n\t")
    if stage == "response":
        return dict(support=True, counter_policy=1, message="fixture")
    return dict(vote=True)


@pytest.mark.parametrize("channel", ("tool", "json", "labelled_json"))
@pytest.mark.parametrize("stage", original.STAGES)
def test_channels_share_exact_typed_action_semantics(channel, stage):
    game = design.generate(3601001).conflict
    value = action(stage)
    trace = stream(json.dumps(value), channel)
    assert contract.decode(game, stage, trace) == value
    evidence = contract.decision(trace)
    assert evidence["channel"] == channel
    assert evidence["arguments"] == value


@pytest.mark.parametrize("arm", institution.ARMS)
@pytest.mark.parametrize("alignment", ("aligned", "conflict"))
@pytest.mark.parametrize("channel", ("tool", "json", "labelled_json"))
def test_all_thirty_actions_preserve_institution_cards_history_schema_and_outcomes(arm, alignment, channel):
    game = getattr(design.generate(3601002), alignment)
    seen = []

    def ask(actor, identity, term, stage, context, index):
        old = keyed.messages(game, arm, actor, identity, term, stage, context)
        new = contract.messages(game, arm, actor, identity, term, stage, context)
        assert new[1] == old[1]  # Byte-identical information and public history.
        assert new[0]["content"].replace(contract.NEW, contract.OLD) == old[0]["content"]
        before = keyed.structured(old, game, stage)
        after = contract.structured(new, game, stage)
        assert after["tools"] == before["tools"]
        assert after["tool_choice"] == before["tool_choice"] == "auto"
        assert "response_format" not in after
        seen.append(identity)
        return contract.decode(game, stage, stream(json.dumps(action(stage)), channel))

    actual = institution.episode(game, arm, ask)
    expected = institution.episode(game, arm, lambda a, i, t, s, c, n: action(s))
    assert len(seen) == actual.calls == 30
    assert asdict(actual) == asdict(expected)


@pytest.mark.parametrize("channel", ("tool", "json", "labelled_json"))
@pytest.mark.parametrize("raw", (
    '{"vote":true,"vote":false}', '{"vote":NaN}', '{"vote":Infinity}',
    '{"vote":1e999}', '[{"vote":true}]', 'true', '',
    '```json\n{"vote":true}\n```', 'Here: {"vote":true}',
    '{"vote":true} {"vote":false}', '{"vote":true} explanation',
    'other_function\n{"vote":true}',
))
def test_no_duplicate_nonfinite_extraction_fence_or_second_decision(channel, raw):
    with pytest.raises(ValueError):
        contract.decision(stream(raw, channel))


@pytest.mark.parametrize("channel", ("tool", "json", "labelled_json"))
@pytest.mark.parametrize("value", (dict(vote=1), dict(vote="true"), dict(vote=None),
                                   dict(vote=True, extra=1), {}))
def test_never_coerces_types_or_drops_fields(channel, value):
    game = design.generate(3601001).aligned
    with pytest.raises(ValueError):
        contract.decode(game, "vote", stream(json.dumps(value), channel))


@pytest.mark.parametrize("channel", ("tool", "json", "labelled_json"))
def test_all_legal_policies_and_both_votes_accepted_without_optimality_filter(channel):
    game = design.generate(3601001).conflict
    for p in range(6):
        for stage in original.STAGES:
            value = action(stage, p)
            if stage == "response":
                value.update(counter_policy=p, support=bool(p % 2))
            if stage == "vote":
                value["vote"] = bool(p % 2)
            assert contract.decode(game, stage, stream(json.dumps(value), channel)) == value
    for value in (dict(policy=True, message=""), dict(policy=1.0, message=""),
                  dict(policy=-1, message=""), dict(policy=6, message=""),
                  dict(policy=1, message="x" * 129), dict(policy=1, message="bad\x85")):
        with pytest.raises(ValueError):
            contract.decode(game, "draft", stream(json.dumps(value), channel))


@pytest.mark.parametrize("text", ('{"vote":true}', '{"vote":false}', 'explanation'))
def test_two_channels_rejected_even_if_decisions_agree(text):
    trace = stream('{"vote":true}', "tool")
    frame = json.loads(trace["lines"][0][6:])
    frame["choices"][0]["delta"]["content"] = text
    with pytest.raises(ValueError, match="ambiguous"):
        contract.decision(pack([frame]))


@pytest.mark.parametrize("channel", ("tool", "json", "labelled_json"))
def test_chunked_unicode_reasoning_usage_and_channel_evidence(channel):
    raw = '{"policy":1,"message":"élections 😀"}'
    full = stream(raw, channel)
    final = json.loads(full["lines"][0][6:])["choices"][0]
    frames = [dict(choices=[dict(index=0, delta=dict(role="assistant", reasoning="private"),
                                finish_reason=None)])]
    for key in ("content", "tool_calls"):
        if key not in final["delta"]:
            continue
        if key == "content":
            fragments = [dict(content=character) for character in final["delta"][key]]
        else:
            tool = deepcopy(final["delta"][key][0])
            text = tool["function"].pop("arguments")
            fragments = [dict(tool_calls=[tool])] + [dict(tool_calls=[dict(
                index=0, function=dict(arguments=character))]) for character in text]
        frames.extend(dict(choices=[dict(index=0, delta=delta, finish_reason=None)]) for delta in fragments)
    frames.append(dict(choices=[dict(index=0, delta={}, finish_reason=final["finish_reason"])]))
    frames.append(dict(choices=[], usage=dict(completion_tokens=77)))
    trace = pack(frames)
    assert contract.decision(trace)["channel"] == channel
    assert contract.decode(design.generate(3601001).aligned, "draft", trace) == json.loads(raw)


@pytest.mark.parametrize("mutation", (
    "missing_done", "double_done", "after_done", "duplicate_finish", "after_finish",
    "wrong_finish", "length", "multiple_choices", "bool_index", "wrong_index",
    "missing_index", "invalid_delta", "legacy_function", "refusal", "stream_error",
    "malformed_frame", "duplicate_frame_key", "invalid_content", "nonobject_frame",
))
def test_incomplete_ambiguous_or_malformed_streams_fail(mutation):
    trace = stream('{"vote":true}')
    frame = json.loads(trace["lines"][0][6:])
    choice = frame["choices"][0]
    if mutation == "missing_done":
        trace["lines"] = trace["lines"][:2]
    elif mutation == "double_done":
        trace["lines"] += ["data: [DONE]", ""]
    elif mutation == "after_done":
        trace["lines"] += trace["lines"][:2]
    elif mutation in ("duplicate_finish", "after_finish"):
        next_frame = deepcopy(frame)
        if mutation == "after_finish":
            next_frame["choices"][0]["finish_reason"] = None
        trace = pack([frame, next_frame])
    elif mutation in ("wrong_finish", "length"):
        choice["finish_reason"] = "tool_calls" if mutation == "wrong_finish" else "length"
        trace = pack([frame])
    elif mutation == "multiple_choices":
        frame["choices"].append(deepcopy(choice))
        trace = pack([frame])
    elif mutation in ("bool_index", "wrong_index", "missing_index"):
        choice["index"] = True if mutation == "bool_index" else 1
        if mutation == "missing_index":
            choice.pop("index")
        trace = pack([frame])
    elif mutation == "invalid_delta":
        choice["delta"] = []
        trace = pack([frame])
    elif mutation in ("legacy_function", "refusal", "invalid_content"):
        choice["delta"][{"legacy_function": "function_call", "refusal": "refusal",
                         "invalid_content": "content"}[mutation]] = {"x": 1}
        trace = pack([frame])
    elif mutation == "stream_error":
        frame["error"] = dict(message="failed")
        trace = pack([frame])
    elif mutation in ("malformed_frame", "duplicate_frame_key", "nonobject_frame"):
        trace["lines"][0] = "data: " + {"malformed_frame": "{", "nonobject_frame": "[]",
                                        "duplicate_frame_key": '{"choices":[],"choices":[]}'}[mutation]
    with pytest.raises(ValueError):
        contract.decision(trace)


@pytest.mark.parametrize("mutation", ("multiple", "wrong_name", "wrong_id", "missing_id",
                                     "wrong_type", "arguments_object", "wrong_finish"))
def test_malformed_actual_tool_calls_not_reinterpreted_as_text(mutation):
    frame = json.loads(stream('{"vote":true}', "tool")["lines"][0][6:])
    choice = frame["choices"][0]
    part = choice["delta"]["tool_calls"][0]
    frames = [frame]
    if mutation == "multiple":
        choice["delta"]["tool_calls"].append(deepcopy(part))
    elif mutation == "wrong_name":
        part["function"]["name"] = "other"
    elif mutation == "wrong_id":
        choice["finish_reason"] = None
        frames.append(dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0, id="two")]),
                                        finish_reason="tool_calls")]))
    elif mutation == "missing_id":
        part.pop("id")
    elif mutation == "wrong_type":
        part["type"] = "other"
    elif mutation == "arguments_object":
        part["function"]["arguments"] = dict(vote=True)
    else:
        choice["finish_reason"] = "stop"
    with pytest.raises(ValueError):
        contract.decision(pack(frames))


def test_prompt_replacement_is_exact_nonmutating_and_cannot_apply_twice():
    prior = [dict(role="system", content=keyed.SYSTEM), dict(role="user", content="fixture")]
    before = deepcopy(prior)
    changed = contract.replace_instruction(prior)
    assert prior == before and changed[1] == prior[1]
    with pytest.raises(ValueError):
        contract.replace_instruction(changed)
    with pytest.raises(ValueError):
        contract.structured(prior, design.generate(3601001).aligned, "vote")


def test_exact_optional_label_only_and_whitespace_not_another_action():
    for raw in ('submit_decision {"vote":true}', 'submit_decision:\n{"vote":true}',
                'submit_decision\r\n{"vote":true}', 'submit_decision\nsubmit_decision\n{"vote":true}'):
        with pytest.raises(ValueError):
            contract.decision(stream(raw))
    frame = json.loads(stream('{"vote":true}', "tool")["lines"][0][6:])
    frame["choices"][0]["delta"]["content"] = " \t\r\n"
    assert contract.decision(pack([frame]))["channel"] == "tool"
    assert contract.decision(stream(' \n {"vote":false}\t'))["arguments"] == dict(vote=False)
