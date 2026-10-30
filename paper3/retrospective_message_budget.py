"""Prospective OFFLINE instrument candidate; not attached to any frozen run.

Public communication is budgeted by Python Unicode-code-point count, exactly
like the existing controller. Preserve requested actions and execute a prefix
of public text only. No policy/vote inference, regeneration or content retry.
Approval, a fresh runner/protocol and independent audit integration are still
required before hosted use. Old failed decisions stay failed.
"""
from copy import deepcopy
from dataclasses import asdict

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_action_contract_v2 as interface

VERSION = "public_prefix_128_v1"


def map_action(game, stage, action):
    """Validate all raw fields, then record the deterministic executed message."""
    institution.require(stage in ("draft", "response", "final", "vote"), "action stage")
    institution.require(type(action) is dict, "action object")
    executed = deepcopy(action)
    requested_length = executed_length = None
    if stage != "vote":
        message = action.get("message")
        institution.require(type(message) is str, "public text string")
        # Check the ENTIRE raw string, including an unexecuted suffix. Reuse
        # existing character legality rather than silently hiding bad controls.
        for start in range(0, max(1, len(message)), institution.MAX_MESSAGE):
            institution._message(message[start:start + institution.MAX_MESSAGE])
        executed["message"] = message[:institution.MAX_MESSAGE]
        requested_length, executed_length = len(message), len(executed["message"])
    if stage in ("draft", "final"):
        executed = asdict(institution.parse_offer(game, executed))
    elif stage == "response":
        executed = asdict(institution.parse_response(game, executed))
    else:
        executed = dict(vote=institution.parse_vote(executed))
    return dict(version=VERSION, stage=stage, requested_action=deepcopy(action),
                executed_action=executed, requested_characters=requested_length,
                executed_characters=executed_length,
                clipped=requested_length is not None and requested_length > executed_length)


def decode(game, stage, trace):
    """Retain the same exact dual-channel decoder; map text after decoding."""
    decoded = interface.decision(trace)
    return dict(mapping=map_action(game, stage, decoded["arguments"]),
                channel=decoded["channel"], raw_action=decoded["raw_action"])


def verify_mapping(game, record):
    """Recompute a saved mapping, rejecting any changed raw/executed metadata."""
    institution.require(type(record) is dict, "mapping record")
    expected = map_action(game, record.get("stage"), record.get("requested_action"))
    institution.require(record == expected, "message mapping changed")
    return deepcopy(expected["executed_action"])
