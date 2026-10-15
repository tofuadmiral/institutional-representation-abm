"""Unfrozen factual/interface gate candidate for constituent-level B.

Four district-objective calculations, five realized contract-rule checks and
three actual-stage validity controls. Passing this engineering prerequisite
would not establish a scientific institutional effect. Transport, provider,
native reasoning, complete billing and frozen-source checks belong to a
separately approved runner; this module performs no inference or spending.
"""
from __future__ import annotations

import json

from paper3 import coalition_contracts as game
from paper3 import constituent_b_design as design
from paper3 import constituent_b_institution as institution
from paper3 import constituent_contract_bridge as bridge


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def cases():
    """Use gate-only seed; discovery profiles must use a different seed."""
    profiles = design.frame(641000)
    result = []
    role_targets = ((0, "A"), (1, "B"), (0, "X"), (3, "aligned"))
    for index, (profile_index, kind) in enumerate(role_targets):
        item = profiles[profile_index]
        actor = item["actor_types"].index(kind)
        prepared = item["prepared"]
        passed = ["A0", "B0"] if index < 3 else ["A0"]
        scored = bridge.evaluate_passed(prepared, passed)
        district = scored["districts"][f"r{actor}"]
        context = dict(acting_for_district=f"r{actor}",
                       own_citizens=prepared["electorate_profile"]["districts"][f"r{actor}"],
                       policy_coordinates=prepared["electorate_profile"]["policies"],
                       district_summed_utilities=prepared["contract_profile"]["utilities"][actor],
                       fixed_enacted_projects=passed, status_quo="q")
        prompt = ("The projects are ALREADY enacted; do not choose an action. Each person's "
                  "utility is the reduction in their issue-weighted squared distance from status quo. "
                  "Count each citizen once. Return exactly district_total_utility (integer sum of "
                  "the enacted projects' row values), citizens_better_than_q (integer count), and "
                  "citizens_worse_than_q (integer count). A citizen with zero change is neither.")
        result.append(dict(name=f"mandate-{index:02d}", kind="fact",
                           messages=[dict(role="system", content=institution.common_rules(prepared)
                                          + "\n" + game.ARM_RULES["public_promise"]),
                                     dict(role="user", content=json.dumps(context, sort_keys=True)
                                          + "\n" + prompt)],
                           expected=dict(district_total_utility=district["total_relative_utility"],
                                         citizens_better_than_q=district["citizen_count"]
                                         - district["citizens_worse_than_q"]
                                         - sum(scored["citizens"][c["id"]]["relative_utility"] == 0
                                               for c in prepared["electorate_profile"]["districts"][f"r{actor}"]),
                                         citizens_worse_than_q=district["citizens_worse_than_q"])))

    rule_forms = (
        ("public_promise", False, False),
        ("member_enforcement", False, False),
        ("universal_clearance", True, False),
        ("universal_clearance", False, False),
        ("member_enforcement", False, True),
    )
    prepared = profiles[0]["prepared"]
    offer = dict(projects=dict(A="A0", B="B0"), first="A",
                 coalition=[0, 1, 3, 4], message="fixed gate offer")
    for index, (arm, outsider_refuses, second_vote) in enumerate(rule_forms):
        approvals = [True] * 7
        if outsider_refuses:
            approvals[6] = False
        events = [dict(type="final", actor=prepared["contract_profile"]["proposer"], action=offer),
                  dict(type="consent", approvals=approvals)]
        if second_vote:
            events.append(game.resolve_vote(events, arm, [True] * 7, "first_vote"))
        requested = [False] * 7
        stage = "second_vote" if second_vote else "first_vote"
        state = game.contract_state(events, arm)
        resolution = game.resolve_vote(events, arm, requested, stage)
        context = dict(fixed_record=events, fixed_requested_votes=requested,
                       vote_stage=stage, coalition=offer["coalition"])
        prompt = ("All consents and requested votes above are FIXED; do not choose an action. "
                  "Under the announced institution, return exactly agreement_active "
                  "(boolean: whether the final agreement activated after consent), "
                  "executed_yes_count (integer for this vote stage), and project_passed "
                  "(boolean for this vote stage).")
        result.append(dict(name=f"contract-{index:02d}", kind="fact",
                           messages=[dict(role="system", content=institution.common_rules(prepared)
                                          + "\n" + game.ARM_RULES[arm]),
                                     dict(role="user", content=json.dumps(context, sort_keys=True)
                                          + "\n" + prompt)],
                           expected=dict(agreement_active=state["active"],
                                         executed_yes_count=sum(resolution["executed"]),
                                         project_passed=resolution["passed"])))

    events = []
    controls = (("draft", prepared["contract_profile"]["proposer"], list(events)),)
    events.append(dict(type="draft", actor=prepared["contract_profile"]["proposer"],
                       action=offer))
    controls += (("response", 1, list(events)),)
    events.append(dict(type="final", actor=prepared["contract_profile"]["proposer"],
                       action=offer))
    events.append(dict(type="consent", approvals=[True] * 7))
    controls += (("first_vote", 0, list(events)),)
    for stage, actor, history in controls:
        result.append(dict(name=f"action-{stage}", kind="action", stage=stage,
                           messages=institution.messages(prepared, "member_enforcement",
                                                         actor, stage, history)))
    if len(result) != 12:
        raise ValueError("gate inventory changed")
    return result


def score(raw, case):
    """No output repair, coercion, or partial credit."""
    try:
        if case["kind"] == "action":
            value = game.parse_action(raw, case["stage"])
            return dict(status="completed", exact=True, reply=value)
        if case["kind"] != "fact":
            raise ValueError("unknown gate case")
        value = json.loads(raw, object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        expected = case["expected"]
        if (type(value) is not dict or set(value) != set(expected)
                or any(type(value[key]) is not type(expected[key]) for key in expected)):
            raise ValueError("wrong factual report shape or type")
        return dict(status="completed", exact=value == expected, reply=value)
    except (ValueError, KeyError, TypeError) as exc:
        return dict(status="failed", exact=False, error=str(exc))
