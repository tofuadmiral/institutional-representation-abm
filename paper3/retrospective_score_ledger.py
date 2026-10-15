"""OFFLINE prospective score disclosure; no inference or launch authority.

All legal enacted-policy consequences, never a recommended action. Current
and future enacted policies are conditional, not predictions of sealed votes.
The economic controller, office value, entrusted horizon and schemas are intact.
Never attach this adapter to, repair or reinterpret any previously frozen run.
"""
from copy import deepcopy
from dataclasses import asdict
import json

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_serialization_contract as contract
from paper3 import retrospective_keyed_interface as keyed

VERSION = "conditional_score_ledger_offline_v1"
NOTICE = """
score_ledger is deterministic bookkeeping, not a recommended policy or ballot.
Every policy key denotes an ENACTED outcome, including policy_0 after rejection.
Your own yes/no ballot does not alone determine enactment. In term_0, future
enacted policy remains unknown: the future score table is conditional on both
enacted outcomes, not a forecast, promise, or fixed future payoff. Do not omit
future district utility after an incumbent is removed. Removal affects only
who acts and the incumbent's office bonus, not its entrusted welfare horizon.
In term_1, past utility and retention are resolved, but current enactment is
still conditional. Original-incumbent and successor scores are separate role
scores, not a pool to divide. There is no third-term bonus. All actions remain
yours; no vote or policy is inferred from this ledger.
"""
SYSTEM = contract.SYSTEM + NOTICE


def _json(value):
    return json.loads(json.dumps(value))


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def readout(game, arm, term, history, occupants):
    """Exact conditional scores from utilities and validated public history."""
    institution.validate(game)
    binding, majority = institution.rules(arm)
    institution.require(type(term) is int and term in (0, 1), "term index")
    institution.require(type(history) is list and len(history) == term,
                        "public history length")
    prior = None
    expected_occupants = tuple(map(institution.incumbent, institution.ACTORS))
    if term == 1:
        saved = history[0]
        institution.require(type(saved) is dict, "predecessor object")
        prior = institution.resolve_term(game, arm, 0,
            institution.parse_offer(game, saved["draft"]),
            tuple(institution.parse_response(game, item) for item in saved["responses"]),
            institution.parse_offer(game, saved["final"]), tuple(saved["requested"]))
        institution.require(_canonical(asdict(prior)) == _canonical(saved),
                            "exact replayed public predecessor")
        expected_occupants = prior.next_occupants
    institution.require(_json(occupants) == _json(expected_occupants),
                        "exact actual officeholders")
    width = len(game.utilities[0][0][0])
    sums = [[tuple(sum(row[p] for row in district) for p in range(width))
             for district in table] for table in game.utilities]
    districts = {}
    for actor in institution.ACTORS:
        past = 0 if prior is None else prior.assessments[actor].district_sum
        retained = None if prior is None else prior.tenure_retained[actor]
        policies = {}
        for p in range(width):
            current = sums[term][actor][p]
            if term == 0:
                assessment = institution.assess(tuple(row[p] for row in game.utilities[0][actor]))
                keep = not binding or (assessment.majority_passed if majority else assessment.sum_passed)
                bonus = game.office_value if keep else 0
                policies[f"policy_{p}"] = dict(
                    current_district_utility=current,
                    incumbent_retained_if_enacted=keep,
                    office_bonus_if_enacted=bonus,
                    next_identity_if_enacted=(institution.incumbent(actor) if keep
                                              else institution.successor(actor)),
                    original_incumbent_score_by_future_enacted_policy={
                        f"policy_{q}": current + sums[1][actor][q] + bonus
                        for q in range(width)})
            else:
                bonus = game.office_value if retained else 0
                original = past + current + bonus
                successor = current if not retained else None
                policies[f"policy_{p}"] = dict(
                    current_district_utility=current,
                    original_incumbent_score_if_enacted=original,
                    successor_score_if_enacted=successor,
                    acting_identity_score_if_enacted=original if retained else successor)
        districts[f"district_{actor}"] = dict(
            original_incumbent_identity=institution.incumbent(actor),
            acting_identity=expected_occupants[actor],
            accrued_district_utility=past,
            original_incumbent_retained=retained,
            resolved_office_bonus=(None if retained is None else game.office_value if retained else 0),
            future_utility_still_credited_after_removal=True,
            conditional_enacted_policies=policies)
    return dict(version=VERSION, current_term=term, policy_ids=list(range(width)),
        passage_requires_four_yes=True, rejection_enacts_policy=0,
        future_enactment_resolved=False if term == 0 else None,
        current_enactment_resolved=False, third_term_bonus=0,
        role_scores_are_not_a_shared_budget=True, districts=districts)


def messages(game, arm, actor, identity, term, stage, context):
    """Add common arithmetic readouts; preserve every original disclosure."""
    result = deepcopy(contract.messages(game, arm, actor, identity, term, stage, context))
    value = json.loads(result[1]["content"])
    institution.require("score_ledger" not in value, "duplicate ledger")
    value["score_ledger"] = readout(game, arm, term, value["history"], value["occupants"])
    result[0]["content"] = SYSTEM
    result[1]["content"] = json.dumps(value, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False)
    return result


def structured(messages_value, game, stage):
    institution.require(type(messages_value) is list and len(messages_value) == 2
        and messages_value[0] == dict(role="system", content=SYSTEM)
        and messages_value[1].get("role") == "user",
        "score-ledger messages required")
    value = contract._object(messages_value[1]["content"])
    institution.require(value["stage"] == stage, "action stage changed")
    institution.require(keyed.restore_utilities(value["payoff_cards"], len(game.utilities[0][0][0]))
        == game.utilities, "payoff cards changed")
    verify_readout(game, value["arm"], value["term"], value["history"],
                   value["occupants"], value["score_ledger"])
    # Same exact AUTO tool and typed action schema as the preserved interface.
    return keyed.structured(messages_value, game, stage)


def verify_readout(game, arm, term, history, occupants, saved):
    institution.require(type(saved) is dict and _canonical(saved) ==
                        _canonical(readout(game, arm, term, history, occupants)),
                        "conditional score ledger changed")
    return deepcopy(saved)
