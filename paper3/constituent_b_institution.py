"""Unfrozen B-message candidate with an explicit equal-person district mandate.

The historical coalition-contract rules and controller are imported read-only.
This adapter changes the representative's entrusted objective and the data
record, not the three institutional enforcement rules. It does not perform
model inference or define a prospective run protocol.
"""
from __future__ import annotations

from copy import deepcopy
import json

from paper3 import coalition_contracts as game
from paper3 import constituent_contract_bridge as bridge


OLD_OBJECTIVE = """Seven representatives each serve a different principal. Your sole
objective is to pursue YOUR principal's total utility across the two projects.
Do not replace that objective with group welfare or obedience to another agent.
Every principal's exact utility table is public."""
OLD_PEERS = "Other representatives have the same\nown-principal objective."


def common_rules(prepared):
    """Preserve contract mechanics, changing only mandate terminology."""
    spec = prepared["equal_standing_specification"]
    citizens = spec["citizens_per_district"]
    budget = spec["priority_budget"]
    new_objective = f"""Seven representatives each serve one district of {citizens} synthetic citizens.
Each citizen counts once, and each citizen's issue-priority weights sum to {budget}.
Your sole objective is to maximize YOUR district's mean utility across the two
projects actually enacted. The public district utility row is the sum of its
{citizens} citizens' utilities; because every district has {citizens} citizens,
maximizing this row is exactly the same as maximizing their mean utility.
Do not replace this mandate with coalition welfare, another district's goal,
or a majority-vote rule. Other citizens and districts can still gain or lose.
Every district's exact utility row is public."""
    if game.COMMON_RULES.count(OLD_OBJECTIVE) != 1 or game.COMMON_RULES.count(OLD_PEERS) != 1:
        raise ValueError("historical objective text changed; audit required")
    result = game.COMMON_RULES.replace(OLD_OBJECTIVE, new_objective)
    return result.replace(OLD_PEERS, "Other representatives have the same own-district objective.")


def messages(prepared, arm, actor, stage, events):
    """Give all arms the same district mandate, opportunity, and stage budget."""
    profile = prepared["contract_profile"]
    game.validate_profile(profile)
    spec = prepared["equal_standing_specification"]
    expanded = prepared["electorate_profile"]
    base_electorate = dict(
        policies={key: expanded["policies"][key] for key in
                  ("q", "A0", "A1", "B0", "B1")},
        districts=expanded["districts"])
    checked = bridge.prepare_equal_standing(
        base_electorate, profile["id"], profile["proposer"],
        citizens_per_district=spec["citizens_per_district"],
        priority_budget=spec["priority_budget"],
        coordinate_bound=spec["coordinate_bound"])
    if (checked["contract_profile"] != profile or
            checked["equal_standing_specification"] != spec or
            checked["electorate_profile"] != expanded):
        raise ValueError("district objective and citizen profile disagree")
    if arm not in game.ARMS or actor not in game.ACTORS:
        raise ValueError("invalid arm or representative")
    district_id = f"r{actor}"
    record = dict(
        representative=actor, district=district_id, proposer=profile["proposer"],
        district_summed_utilities=profile["utilities"],
        equal_standing_specification=prepared["equal_standing_specification"],
        own_citizens=prepared["electorate_profile"]["districts"][district_id],
        project_menu=game.PROJECTS, events=events,
        public_contract_register=game.contract_state(events, arm))
    task = game.task_text(stage, events).replace("your principal", "your district")
    return [dict(role="system", content=common_rules(prepared)+"\n"+game.ARM_RULES[arm]),
            dict(role="user", content=json.dumps(record, separators=(",", ":"))+"\n"+task)]


def messages_snapshot(prepared, arm, actor, stage, events):
    """Return a detached prompt snapshot suitable for prospective hashing."""
    return deepcopy(messages(prepared, arm, actor, stage, events))


def episode(prepared, arm, ask):
    """Run the existing thirty-decision B sequence with the new mandate text.

    ``ask`` supplies a final JSON string for each actor/stage. A caller must
    persist all raw requests, failures, reservations and event prefixes; this
    pure engine has no transport, retry, or billing behavior.
    """
    profile = prepared["contract_profile"]
    game.validate_profile(profile)
    if arm not in game.ARMS:
        raise ValueError("invalid arm")
    events, index = [], 0

    def decision(actor, stage):
        nonlocal index
        content = ask(actor, stage, messages(prepared, arm, actor, stage, events), index)
        index += 1
        return game.parse_action(content, stage)

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
