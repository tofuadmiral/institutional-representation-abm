"""Prospective ratification instrument with explicit aggregate mandates.

The old direct-ratification engine is immutable evidence. This separate
instrument changes what agents can see (exact district sums alongside raw
citizen rows) and uses a prospectively uniform 1,500-character public
message envelope rather than the prior 400-character limit. Every arm in
the threshold pilot uses this same instrument.
"""
from __future__ import annotations

import json

from paper3 import direct_ratification as base


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_action(raw, stage):
    """Require a single exact JSON action; do not coerce or repair it."""
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "duplicate JSON key")
            value[key] = item
        return value

    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    require(type(value) is dict and stage in base.STAGES, "action object/stage")
    if stage in ("draft", "final"):
        require(set(value) == {"policy", "message"} and
                value["policy"] in base.POLICIES and
                type(value["message"]) is str and
                len(value["message"]) <= 1500, "proposal action")
    elif stage == "response":
        require(set(value) == {"support", "preferred_policy", "message"} and
                type(value["support"]) is bool and
                value["preferred_policy"] in base.POLICIES and
                type(value["message"]) is str and
                len(value["message"]) <= 1500, "response action")
    else:
        require(set(value) == {"vote"} and type(value["vote"]) is bool,
                "ballot action")
    return value


def messages(profile, arm, actor, stage, events):
    base.validate(profile)
    require(arm in base.ARMS and actor in base.ACTORS and stage in base.STAGES,
            "decision context")
    record = dict(representative=actor, own_district=f"r{actor}",
                  agenda_holder=profile["proposer"], policies=base.POLICIES,
                  individual_citizen_preferences=profile["districts"],
                  exact_district_utility_sums=base.district_totals(profile),
                  events=events)
    return [dict(role="system", content=base.COMMON + "\n" + base.ARM_RULES[arm] +
                 "\nThe exact district utility sums in the record are controller-computed "
                 "from the individual rows. A district referendum still depends on "
                 "the number of citizens with strictly positive utility, not its sum."),
            dict(role="user", content=json.dumps(record, separators=(",", ":")) +
                 "\n" + base.task(stage, events))]


def episode(profile, arm, ask):
    """Run the complete seven-representative sequence with the new interface."""
    base.validate(profile)
    require(arm in base.ARMS, "arm")
    events = []
    index = 0

    def decision(actor, stage):
        nonlocal index
        raw = ask(actor, stage, messages(profile, arm, actor, stage, events), index)
        index += 1
        return parse_action(raw, stage)

    proposer = profile["proposer"]
    events.append(dict(type="draft", actor=proposer,
                       action=decision(proposer, "draft")))
    responses = [dict(actor=actor, action=decision(actor, "response"))
                 for actor in base.ACTORS]
    events.append(dict(type="responses", responses=responses))
    events.append(dict(type="final", actor=proposer,
                       action=decision(proposer, "final")))
    ballots = [decision(actor, "vote")["vote"] for actor in base.ACTORS]
    events.append(dict(type="vote", requested=ballots))
    require(index == 16, "decision count")
    return dict(events=events, outcome=base.score(profile, arm, events), calls=index)
