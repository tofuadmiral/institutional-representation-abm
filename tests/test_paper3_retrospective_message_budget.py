"""Synthetic, offline mapping/controller checks; no paid runner or network."""
from copy import deepcopy
from dataclasses import asdict
import json

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_message_budget as budget
from tests.test_paper3_retrospective_action_contract_v2 import pack, stream


@pytest.fixture
def game():
    district = tuple((0, -1, 1, 2, 3, 4) for _ in range(9))
    table = tuple(district for _ in range(7))
    return institution.Game("offline-message-budget", (table, table), (0, 1), 24)


@pytest.mark.parametrize("stage", ["draft", "response", "final"])
@pytest.mark.parametrize("length", [0, 1, 127, 128, 129, 143, 4096])
def test_prefix_and_full_raw_retention(game, stage, length):
    action = (dict(policy=2, message="x" * length) if stage != "response" else
              dict(support=True, counter_policy=2, message="x" * length))
    old = deepcopy(action)
    mapped = budget.map_action(game, stage, action)
    assert action == old == mapped["requested_action"]
    assert mapped["executed_action"] == dict(old, message="x" * min(length, 128))
    assert mapped["clipped"] == (length > 128)
    assert mapped["requested_characters"] == length
    assert mapped["executed_characters"] == min(length, 128)
    assert budget.verify_mapping(game, mapped) == mapped["executed_action"]
    mapped["executed_action"]["message"] = "tampered"
    assert action == old
    with pytest.raises(ValueError, match="mapping changed"):
        budget.verify_mapping(game, mapped)


@pytest.mark.parametrize("vote", [False, True])
def test_votes_untouched(game, vote):
    record = budget.map_action(game, "vote", dict(vote=vote))
    assert record["requested_action"] == record["executed_action"] == dict(vote=vote)
    assert record["requested_characters"] is record["executed_characters"] is None
    assert record["clipped"] is False


@pytest.mark.parametrize("message", [None, 143, True, [], "\x00", "x" * 128 + "\x7f",
                                    "x" * 256 + "\x85"])
def test_bad_message_even_after_prefix_rejected(game, message):
    with pytest.raises(ValueError):
        budget.map_action(game, "draft", dict(policy=0, message=message))


@pytest.mark.parametrize("stage,action", [
    ("draft", dict(policy=True, message="x" * 143)),
    ("draft", dict(policy=6, message="x" * 143)),
    ("draft", dict(policy=-1, message="x" * 143)),
    ("draft", dict(policy="1", message="x" * 143)),
    ("draft", dict(policy=1, message="x" * 143, extra=0)),
    ("response", dict(support=1, counter_policy=1, message="x" * 143)),
    ("response", dict(support=True, counter_policy=True, message="x" * 143)),
    ("response", dict(support=True, message="x" * 143)),
    ("vote", dict(vote=1)), ("vote", dict(vote=True, message="x" * 143)),
    ("invalid", dict(policy=1, message="x" * 143)),
])
def test_not_a_policy_or_schema_repair(game, stage, action):
    with pytest.raises(ValueError):
        budget.map_action(game, stage, action)


def test_unicode_count_and_permitted_whitespace(game):
    message = "🗳é\t\n\r" * 40
    mapped = budget.map_action(game, "draft", dict(policy=1, message=message))
    assert mapped["requested_characters"] == 200
    assert mapped["executed_action"]["message"] == message[:128]
    assert mapped["executed_characters"] == 128


@pytest.mark.parametrize("channel", ["tool", "json", "labelled_json"])
@pytest.mark.parametrize("stage", ["draft", "response", "final", "vote"])
def test_exact_dual_channel_decoder_retained(game, channel, stage):
    action = (dict(policy=3, message="x" * 143) if stage in ("draft", "final") else
              dict(support=False, counter_policy=3, message="x" * 143) if stage == "response" else
              dict(vote=False))
    raw = json.dumps(action)
    decoded = budget.decode(game, stage, stream(raw, channel))
    assert decoded["channel"] == channel
    assert decoded["raw_action"] == raw
    assert decoded["mapping"]["requested_action"] == action
    assert budget.verify_mapping(game, decoded["mapping"]) == decoded["mapping"]["executed_action"]


@pytest.mark.parametrize("channel", ["tool", "json", "labelled_json"])
@pytest.mark.parametrize("raw", ['{"vote":true,"vote":false}', '{"vote":NaN}',
                                 '{"vote":true} explanation', '[{"vote":true}]',
                                 '```json\n{"vote":true}\n```'])
def test_no_json_repair(game, channel, raw):
    with pytest.raises(ValueError):
        budget.decode(game, "vote", stream(raw, channel))


def test_ambiguous_channels_still_rejected(game):
    trace = stream('{"vote":true}', "tool")
    frame = json.loads(trace["lines"][0][6:])
    frame["choices"][0]["delta"]["content"] = '{"vote":true}'
    with pytest.raises(ValueError, match="ambiguous"):
        budget.decode(game, "vote", pack([frame]))


@pytest.mark.parametrize("arm", institution.ARMS)
def test_same_full_controller_trajectory_for_same_executed_actions(game, arm):
    mappings = []

    def action(stage, message):
        if stage in ("draft", "final"):
            return dict(policy=2, message=message)
        if stage == "response":
            return dict(support=True, counter_policy=2, message=message)
        return dict(vote=True)

    def short(actor, identity, term, stage, context, index):
        return action(stage, "x" * 128)

    def long(actor, identity, term, stage, context, index):
        mapped = budget.map_action(game, stage, action(stage, "x" * 128 + "unexecuted suffix"))
        mappings.append(mapped)
        return budget.verify_mapping(game, mapped)

    reference = institution.episode(game, arm, short)
    candidate = institution.episode(game, arm, long)
    assert asdict(candidate) == asdict(reference)
    assert len(mappings) == 30
    assert sum(m["clipped"] for m in mappings) == 16
    assert all(t.requested == t.executed for t in candidate.terms)
