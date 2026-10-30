"""Offline candidate: named policy cards, not a strategic recommendation.

Losslessly reorganizes the same citizen utilities and current scoreboards.
District sums are deterministic arithmetic assistance, available for every
policy/term/district in every arm. This is a changed representation, not a
randomized comparison with the closed tensor gates. No calls or allocation.
"""
from copy import deepcopy
import json

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_interface as original
from paper3 import retrospective_labeled_interface as labeled

SYSTEM = original.SYSTEM + """
Payoffs are named cards, not a positional policy-column matrix.
payoff_cards[term_t][district_d][policy_p] describes ONE policy p for ONE
district d in ONE term t. citizen_utilities[c] is citizen c's utility for
THAT policy, with citizen IDs 0 through 8 in order. district_sum is their
verified sum, not an office score. Use the exact policy key, not a neighboring
card. Policy IDs in actions/history remain integers 0 through the menu end.
assessment_cards[district_d][policy_p] contains both disclosed assessments
for the CURRENT term. Citizen approval is not a representative policy ballot.
Your ballot is ONE of seven: four yes votes enact the final policy, otherwise
policy 0. Keep hypothetical peer ballots and future outcomes fixed when given.
No card supplies a recommended policy, vote or complete incumbent score.
"""


def payoff_cards(game):
    institution.validate(game)
    width = len(game.utilities[0][0][0])
    return {f"term_{t}": {f"district_{d}": {
        f"policy_{p}": dict(citizen_utilities=[row[p] for row in district],
                            district_sum=sum(row[p] for row in district))
        for p in range(width)} for d, district in enumerate(table)}
        for t, table in enumerate(game.utilities)}


def restore_utilities(cards, width):
    """Strict complete roundtrip, rejecting changed/missing/extra coordinates."""
    institution.require(type(width) is int and 2 <= width <= 8, "finite menu")
    institution.require(type(cards) is dict and set(cards) == {"term_0", "term_1"},
                        "exact term keys")
    result = []
    for t in range(2):
        districts = cards[f"term_{t}"]
        institution.require(type(districts) is dict and set(districts) ==
                            {f"district_{d}" for d in range(7)}, "exact district keys")
        table = []
        for d in range(7):
            policies = districts[f"district_{d}"]
            institution.require(type(policies) is dict and set(policies) ==
                                {f"policy_{p}" for p in range(width)}, "exact policy keys")
            for p in range(width):
                card = policies[f"policy_{p}"]
                institution.require(type(card) is dict and set(card) ==
                                    {"citizen_utilities", "district_sum"}, "exact card fields")
                values = card["citizen_utilities"]
                institution.require(type(values) is list and len(values) == 9 and
                    all(type(v) is int and -10 <= v <= 10 for v in values), "nine citizen values")
                institution.require(type(card["district_sum"]) is int and
                    card["district_sum"] == sum(values), "verified district sum")
            table.append(tuple(tuple(policies[f"policy_{p}"]["citizen_utilities"][c]
                                     for p in range(width)) for c in range(9)))
        result.append(tuple(table))
    return tuple(result)


def clarify(messages_value, game):
    institution.validate(game)
    institution.require(type(messages_value) is list and len(messages_value) == 2 and
        messages_value[0] == dict(role="system", content=original.SYSTEM) and
        messages_value[1]["role"] == "user", "unaltered base messages required")
    result = deepcopy(messages_value)
    value = json.loads(result[1]["content"])
    institution.require(value["utilities"] == json.loads(json.dumps(game.utilities)),
                        "unchanged source utilities required")
    cards = payoff_cards(game)
    institution.require(restore_utilities(cards, len(game.utilities[0][0][0])) == game.utilities,
                        "lossless complete payoff representation")
    original_assessments = value.pop("menu_assessments")
    expected = [[dict(citizen_ballots=[v >= 0 for v in cards[f"term_{value['term']}"]
                        [f"district_{d}"][f"policy_{p}"]["citizen_utilities"]],
                     majority_passed=sum(v >= 0 for v in cards[f"term_{value['term']}"]
                        [f"district_{d}"][f"policy_{p}"]["citizen_utilities"]) >= 5,
                     district_sum=cards[f"term_{value['term']}"][f"district_{d}"]
                        [f"policy_{p}"]["district_sum"],
                     sum_passed=cards[f"term_{value['term']}"][f"district_{d}"]
                        [f"policy_{p}"]["district_sum"] >= 0)
                 for p in range(len(game.utilities[0][0][0]))] for d in range(7)]
    institution.require(original_assessments == expected, "exact disclosed current scoreboards")
    value.pop("utilities")
    value["payoff_cards"] = cards
    value["assessment_cards"] = {f"district_{d}": {f"policy_{p}": assessment
        for p, assessment in enumerate(row)} for d, row in enumerate(original_assessments)}
    value["data_layout"] = dict(
        payoff_keys=["term_t", "district_d", "policy_p"],
        term_ids=[0, 1], district_ids=list(range(7)), citizen_ids=list(range(9)),
        policy_ids=list(range(len(game.utilities[0][0][0]))),
        citizen_utilities_axis="citizen", assessment_cards_term=value["term"],
        citizen_ballots_axis="citizen", representative_ballots_axis="district",
        status_quo_policy=0, policy_passage_yes_threshold=4,
        district_sums="deterministic arithmetic readouts, not office scores")
    result[0]["content"] = SYSTEM
    result[1]["content"] = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return result


def messages(game, arm, actor, identity, term, stage, context):
    return clarify(original.messages(game, arm, actor, identity, term, stage, context), game)


structured = labeled.structured
decode = original.decode
