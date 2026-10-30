"""Deterministic citizen-level mandate metrics; no agent calls or rule design.

Each district may contain many synthetic citizens. A citizen has an ideal point
and positive issue-priority weights. Utility is the reduction in weighted
squared policy distance relative to status quo ``q``. This is an evaluation
layer, not an election, coalition, or experimental protocol. Summed utility is
one possible *utilitarian* mandate benchmark, not one-person-one-vote: citizens
with larger issue weights can have larger utility magnitudes and influence it
more. Electoral aggregation must be defined separately.
"""
from __future__ import annotations

from fractions import Fraction
from math import sqrt


def validate(profile):
    """Reject malformed or silently incomparable electorate descriptions."""
    if type(profile) is not dict:
        raise ValueError("profile must be an object")
    policies = profile.get("policies")
    districts = profile.get("districts")
    if (type(policies) is not dict or len(policies) < 2 or "q" not in policies
            or type(districts) is not dict or not districts):
        raise ValueError("policies including q and nonempty districts required")
    dimensions = None
    for policy_id, coordinates in policies.items():
        if (type(policy_id) is not str or not policy_id
                or type(coordinates) not in (list, tuple) or not coordinates
                or any(type(value) is not int for value in coordinates)):
            raise ValueError("invalid policy coordinates")
        dimensions = len(coordinates) if dimensions is None else dimensions
        if len(coordinates) != dimensions:
            raise ValueError("policy dimensions differ")
    seen = set()
    for district_id, citizens in districts.items():
        if (type(district_id) is not str or not district_id
                or type(citizens) is not list or not citizens):
            raise ValueError("invalid district")
        for citizen in citizens:
            if type(citizen) is not dict:
                raise ValueError("invalid citizen")
            citizen_id = citizen.get("id")
            ideal, weights = citizen.get("ideal"), citizen.get("weights")
            if (type(citizen_id) is not str or not citizen_id or citizen_id in seen
                    or type(ideal) not in (list, tuple)
                    or type(weights) not in (list, tuple)
                    or len(ideal) != dimensions or len(weights) != dimensions
                    or any(type(value) is not int for value in ideal)
                    or any(type(value) is not int or value <= 0 for value in weights)):
                raise ValueError("invalid citizen preference or repeated id")
            seen.add(citizen_id)
    return profile


def _weighted_squared(policy, citizen):
    return sum(weight * (coordinate - ideal) ** 2 for coordinate, ideal, weight
               in zip(policy, citizen["ideal"], citizen["weights"], strict=True))


def mandates(profile):
    """Return utilitarian district totals and possibly tied welfare optima."""
    validate(profile)
    policies = profile["policies"]
    baseline = policies["q"]
    result = {}
    for district_id, citizens in profile["districts"].items():
        totals = {
            policy_id: sum(_weighted_squared(baseline, citizen)
                           - _weighted_squared(coordinates, citizen)
                           for citizen in citizens)
            for policy_id, coordinates in policies.items()
        }
        best = max(totals.values())
        result[district_id] = dict(aggregation="sum_of_citizen_utilities",
                                   citizen_count=len(citizens),
                                   policy_total_utility=totals,
                                   best_policy_ids=[p for p, value in totals.items()
                                                    if value == best])
    return result


def preference_counts(profile):
    """Count equal-person ordinal preferences without choosing an election rule.

    Each citizen contributes once to each pairwise comparison, regardless of
    utility magnitude. A tied favorite is kept separate from strict first
    choices. Pairwise tallies are descriptive; no winner is declared.
    """
    validate(profile)
    policies = profile["policies"]
    policy_ids = list(policies)
    result = {}
    for district_id, citizens in profile["districts"].items():
        first = {policy_id: 0 for policy_id in policy_ids}
        tied_first = 0
        pairwise = [dict(first_policy_id=a, second_policy_id=b,
                         first_preferred=0, second_preferred=0, indifferent=0)
                    for i, a in enumerate(policy_ids) for b in policy_ids[i + 1:]]
        for citizen in citizens:
            losses = {policy_id: _weighted_squared(coordinates, citizen)
                      for policy_id, coordinates in policies.items()}
            best = [p for p, loss in losses.items() if loss == min(losses.values())]
            if len(best) == 1:
                first[best[0]] += 1
            else:
                tied_first += 1
            for comparison in pairwise:
                a = losses[comparison["first_policy_id"]]
                b = losses[comparison["second_policy_id"]]
                key = ("first_preferred" if a < b else
                       "second_preferred" if b < a else "indifferent")
                comparison[key] += 1
        result[district_id] = dict(citizen_count=len(citizens),
                                   strict_first_choice_counts=first,
                                   tied_first_choice_citizens=tied_first,
                                   pairwise=pairwise)
    return result


def evaluate(profile, policy_id):
    """Score a final policy for every citizen, district, and the whole polity."""
    validate(profile)
    policies = profile["policies"]
    if policy_id not in policies:
        raise ValueError("unknown final policy")
    mandate = mandates(profile)
    chosen = policies[policy_id]
    baseline = policies["q"]
    citizens_out = {}
    districts_out = {}
    all_regrets = []
    total_utility = 0
    worse_than_q = 0
    for district_id, citizens in profile["districts"].items():
        district_utility = 0
        district_worse = 0
        for citizen in citizens:
            losses = {p: _weighted_squared(coords, citizen)
                      for p, coords in policies.items()}
            utility = losses["q"] - losses[policy_id]
            regret = losses[policy_id] - min(losses.values())
            citizen_worse = utility < 0
            unweighted_sq = sum((coordinate - ideal) ** 2 for coordinate, ideal
                                in zip(chosen, citizen["ideal"], strict=True))
            citizens_out[citizen["id"]] = dict(
                district=district_id, relative_utility=utility,
                weighted_squared_distance=losses[policy_id],
                weighted_l2=sqrt(losses[policy_id]),
                unweighted_l2=sqrt(unweighted_sq),
                own_best_policy_ids=[p for p, value in losses.items()
                                     if value == min(losses.values())],
                own_regret=regret, worse_than_q=citizen_worse)
            district_utility += utility
            district_worse += citizen_worse
            all_regrets.append(regret)
        best_district = max(mandate[district_id]["policy_total_utility"].values())
        districts_out[district_id] = dict(
            citizen_count=len(citizens), total_relative_utility=district_utility,
            mandate_best_policy_ids=mandate[district_id]["best_policy_ids"],
            mandate_regret=best_district - district_utility,
            citizens_worse_than_q=district_worse)
        total_utility += district_utility
        worse_than_q += district_worse
    return dict(policy_id=policy_id, citizens=citizens_out,
                districts=districts_out,
                overall=dict(citizen_count=len(all_regrets),
                             total_relative_utility=total_utility,
                             mean_individual_regret_exact=str(Fraction(
                                 sum(all_regrets), len(all_regrets))),
                             worst_individual_regret=max(all_regrets),
                             citizens_worse_than_q=worse_than_q))


def compare(profile, from_policy_id, to_policy_id):
    """Report every citizen's change between two realized policies.

    Positive ``utility_change`` means the citizen prefers the *to* outcome;
    this is not an election rule or a causal effect estimate. The caller must
    provide an experimentally valid pair of outcomes before interpreting it
    as an institutional comparison.
    """
    before = evaluate(profile, from_policy_id)
    after = evaluate(profile, to_policy_id)
    citizens_out = {}
    districts_out = {}
    all_changes = []
    for district_id, citizens in profile["districts"].items():
        changes = []
        for citizen in citizens:
            citizen_id = citizen["id"]
            first = before["citizens"][citizen_id]
            second = after["citizens"][citizen_id]
            delta = second["relative_utility"] - first["relative_utility"]
            citizens_out[citizen_id] = dict(
                district=district_id, utility_change=delta,
                regret_change=second["own_regret"] - first["own_regret"])
            changes.append(delta)
            all_changes.append(delta)
        districts_out[district_id] = dict(
            citizen_count=len(changes), total_utility_change=sum(changes),
            citizens_better=sum(value > 0 for value in changes),
            citizens_worse=sum(value < 0 for value in changes),
            citizens_unchanged=sum(value == 0 for value in changes))
    return dict(from_policy_id=from_policy_id, to_policy_id=to_policy_id,
                citizens=citizens_out, districts=districts_out,
                overall=dict(citizen_count=len(all_changes),
                             total_utility_change=sum(all_changes),
                             mean_utility_change_exact=str(Fraction(
                                 sum(all_changes), len(all_changes))),
                             citizens_better=sum(value > 0 for value in all_changes),
                             citizens_worse=sum(value < 0 for value in all_changes),
                             citizens_unchanged=sum(value == 0 for value in all_changes)))
