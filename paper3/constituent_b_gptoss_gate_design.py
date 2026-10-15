"""Fresh, offline gate contexts for a prospective gpt-oss tool interface.

These cases test arithmetic, contract rules, and legal actions. They do not
test an institutional treatment effect. The failed DeepSeek cases are not
reused or rescored. No network or budget access occurs here.
"""
from __future__ import annotations

import json

from paper3 import coalition_contracts as game
from paper3 import constituent_b_design as design
from paper3 import constituent_b_institution as institution
from paper3 import constituent_contract_bridge as bridge


FRAME_SEED = 661000


def cases():
    profiles = design.frame(FRAME_SEED)
    result = []
    roles = ((0, "A"), (1, "B"), (2, "X"), (3, "aligned"))
    for index, (profile_index, role) in enumerate(roles):
        item = profiles[profile_index]
        prepared = item["prepared"]
        actor = item["actor_types"].index(role)
        passed = ("A1", "B0") if index < 3 else ("B1",)
        observed = bridge.evaluate_passed(prepared, list(passed))
        citizen_ids = [citizen["id"] for citizen in
                       prepared["electorate_profile"]["districts"][f"r{actor}"]]
        changes = [observed["citizens"][citizen_id]["relative_utility"]
                   for citizen_id in citizen_ids]
        context = dict(
            acting_for_district=f"r{actor}",
            own_citizens=prepared["electorate_profile"]["districts"][f"r{actor}"],
            policy_coordinates=prepared["electorate_profile"]["policies"],
            district_summed_utilities=prepared["contract_profile"]["utilities"][actor],
            fixed_enacted_projects=list(passed), status_quo="q",
        )
        task = ("The projects are ALREADY enacted; do not choose an action. Each person's "
                "utility is the reduction in their issue-weighted squared distance from "
                "status quo. Count each citizen once. Report district_total_utility "
                "(integer sum of enacted-project row values), citizens_better_than_q "
                "(integer count), and citizens_worse_than_q (integer count). Zero change "
                "is neither better nor worse. Submit the report through the function.")
        result.append(dict(
            name=f"fresh-mandate-{index:02d}", kind="fact", fact_type="mandate",
            messages=[dict(role="system", content=institution.common_rules(prepared)
                           + "\n" + game.ARM_RULES["public_promise"]),
                      dict(role="user", content=json.dumps(context, sort_keys=True)
                           + "\n" + task)],
            expected=dict(district_total_utility=sum(changes),
                          citizens_better_than_q=sum(value > 0 for value in changes),
                          citizens_worse_than_q=sum(value < 0 for value in changes)),
        ))

    prepared = profiles[0]["prepared"]
    proposer = prepared["contract_profile"]["proposer"]
    coalition = [0, 2, 4, 6]
    offer = dict(projects=dict(A="A1", B="B0"), first="B",
                 coalition=coalition, message="fixed fresh-gate offer")
    rule_forms = (
        ("public_promise", False, False),
        ("member_enforcement", False, False),
        ("universal_clearance", True, False),
        ("universal_clearance", False, False),
        ("member_enforcement", False, True),
    )
    for index, (arm, outsider_refuses, second_vote) in enumerate(rule_forms):
        approvals = [True] * 7
        if outsider_refuses:
            approvals[1] = False
        events = [dict(type="final", actor=proposer, action=offer),
                  dict(type="consent", approvals=approvals)]
        if second_vote:
            events.append(game.resolve_vote(events, arm, [True] * 7,
                                            "first_vote"))
        stage = "second_vote" if second_vote else "first_vote"
        requested = [False] * 7
        state = game.contract_state(events, arm)
        resolution = game.resolve_vote(events, arm, requested, stage)
        context = dict(fixed_record=events, fixed_requested_votes=requested,
                       vote_stage=stage, coalition=coalition)
        task = ("All consents and requested votes above are FIXED; do not choose an "
                "action. Under the announced institution, report agreement_active "
                "(boolean after consent), executed_yes_count (integer for this vote "
                "stage), and project_passed (boolean for this vote stage). Submit "
                "the report through the function.")
        result.append(dict(
            name=f"fresh-contract-{index:02d}", kind="fact", fact_type="contract",
            messages=[dict(role="system", content=institution.common_rules(prepared)
                           + "\n" + game.ARM_RULES[arm]),
                      dict(role="user", content=json.dumps(context, sort_keys=True)
                           + "\n" + task)],
            expected=dict(agreement_active=state["active"],
                          executed_yes_count=sum(resolution["executed"]),
                          project_passed=resolution["passed"]),
        ))

    events = []
    controls = [("draft", proposer, list(events))]
    events.append(dict(type="draft", actor=proposer, action=offer))
    controls.append(("response", (proposer + 1) % 7, list(events)))
    events.append(dict(type="final", actor=proposer, action=offer))
    events.append(dict(type="consent", approvals=[True] * 7))
    controls.append(("first_vote", 2, list(events)))
    for stage, actor, history in controls:
        result.append(dict(name=f"fresh-action-{stage}", kind="action", stage=stage,
                           messages=institution.messages(prepared, "member_enforcement",
                                                         actor, stage, history)))
    if len(result) != 12 or len({row["name"] for row in result}) != 12:
        raise ValueError("fresh gate inventory changed")
    return result
