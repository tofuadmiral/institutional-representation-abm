"""Prospective longer bounded advocacy for a fresh common-transcript run.

The first common-transcript run stopped before either institutional arm:
its one-key advocacy message was 576 serialized bytes versus an arbitrary
502-byte local cap. This revision never rescues or reuses that answer.
"""
from __future__ import annotations

import json

from paper3 import agenda_common_transcript as prior
from paper3 import agenda_schema_interface as schema_prior
from paper3 import agenda_sponsorship_institution as game
from paper3 import direct_ratification as base


ADVOCACY_MAX_CHARS = 1000
ADVOCACY_MAX_JSON_BYTES = 1600


def schema(stage, compromises):
    result = schema_prior.schema(stage, compromises)
    if stage == "advocacy":
        result["properties"]["message"]["maxLength"] = ADVOCACY_MAX_CHARS
        result["properties"]["message"]["description"] = (
            "A concise public advocacy message, at most 1000 characters")
    return result


def messages(item, arm, actor, stage, advocacy=None, prefix=None, floor=None):
    result = prior.messages(item, arm, actor, stage, advocacy, prefix, floor)
    if stage == "advocacy":
        task = 'Advocate publicly for a policy. Return {"message":"..."}.'
        if result[1]["content"].count(task) != 1:
            raise ValueError("source advocacy task changed")
        result[1]["content"] = result[1]["content"].replace(
            task, task + " Keep the message under 1000 characters.")
    return result


def parse_action(raw, stage, compromises):
    if stage != "advocacy":
        return game.parse_action(raw, stage, compromises)
    value = json.loads(raw, object_pairs_hook=game._unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(
                           ValueError("nonfinite")))
    base.require(type(value) is dict and set(value) == {"message"} and
                 type(value["message"]) is str and
                 len(value["message"]) <= ADVOCACY_MAX_CHARS and
                 len(json.dumps(value["message"]).encode()) <=
                 ADVOCACY_MAX_JSON_BYTES, "bounded advocacy action")
    return value


def advocacy(item, ask):
    """ask(actor, stage, messages, index) returns the exact final text."""
    game.validate_item(item)
    transcript = []
    for index, actor in enumerate(base.ACTORS):
        raw = ask(actor, "advocacy", messages(item, None, actor, "advocacy"),
                  index)
        action = parse_action(raw, "advocacy", item["compromises"])
        transcript.append(dict(actor=actor, message=action["message"]))
    return transcript


def arm_episode(item, arm, common_advocacy, ask):
    """Unchanged frozen sponsorship/ballot controller after shared advocacy."""
    return prior.arm_episode(item, arm, common_advocacy, ask)
