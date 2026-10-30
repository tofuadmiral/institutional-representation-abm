"""Candidate seven-position coalition interface; never reinterpret old answers.

This adapter changes only how an offer encodes coalition membership. The game
controller, mandate, action sequence, and substantive four-member rule remain
those of the existing constituent institution. No live run uses it yet.
"""
from __future__ import annotations

import json

from paper3 import coalition_contracts as game
from paper3 import constituent_b_institution as original
from paper3 import constituent_contract_bridge as bridge


MASK_RULE = ("coalition_mask is an array of seven booleans in representative "
             "order 0 through 6. Use exactly four true values for a contract, "
             "or seven false values to seek no contract;")
OLD_RULE = ("coalition is an array of four distinct representative integers "
            "from 0 through 6, or [] to seek no contract;")


def messages(prepared, arm, actor, stage, events):
    result = original.messages(prepared, arm, actor, stage, events)
    if stage in ("draft", "response", "final"):
        task = game.task_text(stage, events).replace("your principal", "your district")
        if task.count(OLD_RULE) != 1 or task.count("coalition, message") != 1:
            raise ValueError("historical offer-task format changed")
        masked = task.replace(OLD_RULE, MASK_RULE).replace(
            "coalition, message", "coalition_mask, message")
        if not result[1]["content"].endswith(task):
            raise ValueError("historical prompt format changed")
        result[1]["content"] = result[1]["content"][:-len(task)] + masked
    return result


def parse_action(raw, stage):
    """Reject bad masks; map only a legal 0-or-4 mask to historical IDs."""
    if stage not in ("draft", "response", "final"):
        return game.parse_action(raw, stage)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(
                           ValueError("nonfinite JSON")))
    expected = {"projects", "first", "coalition_mask", "message"}
    if stage == "response":
        expected.add("support")
    if type(value) is not dict or set(value) != expected:
        raise ValueError("masked offer fields")
    mask = value["coalition_mask"]
    if (type(mask) is not list or len(mask) != 7 or
            any(type(flag) is not bool for flag in mask) or
            sum(mask) not in (0, 4)):
        raise ValueError("coalition mask must select zero or four of seven")
    mapped = {key: item for key, item in value.items() if key != "coalition_mask"}
    mapped["coalition"] = [actor for actor, selected in enumerate(mask) if selected]
    return game.parse_action(json.dumps(mapped, separators=(",", ":")), stage)


def episode(prepared, arm, ask):
    """Run the unchanged thirty-decision institution through the mask parser."""
    profile = prepared["contract_profile"]
    game.validate_profile(profile)
    if arm not in game.ARMS:
        raise ValueError("invalid arm")
    events, index = [], 0

    def decision(actor, stage):
        nonlocal index
        content = ask(actor, stage, messages(prepared, arm, actor, stage, events), index)
        index += 1
        return parse_action(content, stage)

    for stage in ("draft", "response", "final", "consent", "first_vote", "second_vote"):
        if stage in ("draft", "final"):
            action = decision(profile["proposer"], stage)
            events.append(dict(type=stage, actor=profile["proposer"], action=action))
        elif stage == "response":
            actions = [dict(actor=i, action=decision(i, stage)) for i in game.ACTORS]
            events.append(dict(type=stage, responses=actions))
        elif stage == "consent":
            approvals = [decision(i, stage)["consent"] for i in game.ACTORS]
            events.append(dict(type=stage, approvals=approvals))
        else:
            requested = [decision(i, stage)["vote"] for i in game.ACTORS]
            events.append(game.resolve_vote(events, arm, requested, stage))
    if index != 30:
        raise ValueError("unexpected decision count")
    outcome = game.readout(profile, arm, events)
    return dict(events=events, outcome=outcome,
                citizen_outcome=bridge.evaluate_passed(prepared, outcome["passed"]),
                calls=index)
