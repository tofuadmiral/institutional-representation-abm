"""Translate separable citizen preferences into the existing two-project B game.

This is an offline measurement adapter, not a treatment or a model protocol.
The representative's utility row is the *sum* of district citizens' utilities;
that cardinal aggregation is explicit and is not an election or majority rule.
All nine possible project outcomes remain available for citizen-level scoring.
"""
from __future__ import annotations

from copy import deepcopy

from paper3 import coalition_contracts, constituent_mandates


POLICY_IDS = frozenset(("q", "A0", "A1", "B0", "B1"))
DISTRICT_IDS = frozenset(f"r{i}" for i in coalition_contracts.ACTORS)


def validate_equal_standing(profile, *, citizens_per_district, priority_budget,
                            coordinate_bound):
    """Check a common citizen scale for a prospective district mandate.

    These are design constraints, not a social-choice theorem: equal priority
    budgets do not make utility differences interpersonally objective, nor do
    they ensure a majority agrees with the cardinal welfare optimum.
    """
    constituent_mandates.validate(profile)
    for value, name in ((citizens_per_district, "citizens per district"),
                        (priority_budget, "priority budget"),
                        (coordinate_bound, "coordinate bound")):
        if type(value) is not int or value <= 0:
            raise ValueError(f"positive integer {name} required")
    if set(profile["districts"]) != DISTRICT_IDS:
        raise ValueError("exactly seven named districts required")
    coordinates = list(profile["policies"].values())
    for district_id, citizens in profile["districts"].items():
        if len(citizens) != citizens_per_district:
            raise ValueError(f"unequal citizen count in {district_id}")
        for citizen in citizens:
            if sum(citizen["weights"]) != priority_budget:
                raise ValueError("citizen priority budgets differ")
            coordinates.append(citizen["ideal"])
    if any(abs(value) > coordinate_bound for point in coordinates for value in point):
        raise ValueError("policy or citizen ideal outside common coordinate bound")
    return dict(citizens_per_district=citizens_per_district,
                priority_budget=priority_budget, coordinate_bound=coordinate_bound,
                citizen_count=citizens_per_district * len(DISTRICT_IDS))


def prepare_equal_standing(profile, profile_id, proposer, *, citizens_per_district,
                           priority_budget, coordinate_bound):
    """Prepare a B game with an equal-person cardinal district objective.

    The contract engine uses exact integer *sums*; with the same district size,
    maximizing that sum is identical to maximizing the district mean.
    """
    specification = validate_equal_standing(
        profile, citizens_per_district=citizens_per_district,
        priority_budget=priority_budget, coordinate_bound=coordinate_bound)
    result = prepare(profile, profile_id, proposer,
                     aggregation="sum_of_citizen_utilities")
    result["equal_standing_specification"] = specification
    return result


def prepare(profile, profile_id, proposer, *, aggregation):
    """Return a legacy B profile plus a full citizen-level outcome menu.

    ``aggregation`` must be explicitly ``sum_of_citizen_utilities``. Project A
    may alter only issue 0 and project B only issue 1; this guarantees that a
    package's citizen utility equals the sum of its constituent project
    utilities. Reject other shapes rather than silently changing the game.
    """
    constituent_mandates.validate(profile)
    if aggregation != "sum_of_citizen_utilities":
        raise ValueError("explicit sum-of-citizen-utilities aggregation required")
    if type(profile_id) is not str or not profile_id:
        raise ValueError("profile id required")
    if type(proposer) is not int or proposer not in coalition_contracts.ACTORS:
        raise ValueError("invalid proposer")
    if set(profile["policies"]) != POLICY_IDS or set(profile["districts"]) != DISTRICT_IDS:
        raise ValueError("two-project policy menu and r0-r6 districts required")
    policies = profile["policies"]
    q = policies["q"]
    if len(q) != 2:
        raise ValueError("two issue dimensions required")
    for policy_id in coalition_contracts.PROJECTS["A"]:
        if policies[policy_id][1] != q[1]:
            raise ValueError("A project must alter only issue 0")
    for policy_id in coalition_contracts.PROJECTS["B"]:
        if policies[policy_id][0] != q[0]:
            raise ValueError("B project must alter only issue 1")

    expanded = {"q": list(q)}
    expanded.update({key: list(coords) for key, coords in policies.items() if key != "q"})
    for a in coalition_contracts.PROJECTS["A"]:
        for b in coalition_contracts.PROJECTS["B"]:
            expanded[f"{a}+{b}"] = [policies[a][0], policies[b][1]]
    electorate = {"policies": expanded, "districts": deepcopy(profile["districts"])}
    district_totals = constituent_mandates.mandates(electorate)
    rows = [{project: district_totals[f"r{i}"]["policy_total_utility"][project]
             for project in ("A0", "A1", "B0", "B1")}
            for i in coalition_contracts.ACTORS]
    contract_profile = {"id": profile_id, "proposer": proposer, "utilities": rows}
    coalition_contracts.validate_profile(contract_profile)

    # Check the defining separability invariant for every citizen and package.
    for district in profile["districts"].values():
        for citizen in district:
            q_loss = constituent_mandates._weighted_squared(q, citizen)
            for a in coalition_contracts.PROJECTS["A"]:
                for b in coalition_contracts.PROJECTS["B"]:
                    package = expanded[f"{a}+{b}"]
                    package_utility = q_loss - constituent_mandates._weighted_squared(package, citizen)
                    parts = sum(q_loss - constituent_mandates._weighted_squared(policies[p], citizen)
                                for p in (a, b))
                    if package_utility != parts:
                        raise ValueError("nonadditive citizen utility")
    return {"contract_profile": contract_profile, "electorate_profile": electorate,
            "aggregation": aggregation}


def evaluate_passed(prepared, passed):
    """Score an actual B outcome against every citizen's complete outcome menu."""
    if type(passed) not in (list, tuple) or len(passed) > 2:
        raise ValueError("passed must be zero, one or two project ids")
    if any(type(p) is not str or p not in POLICY_IDS - {"q"} for p in passed):
        raise ValueError("invalid project id")
    if len(set(passed)) != len(passed) or sum(p.startswith("A") for p in passed) > 1 or sum(
            p.startswith("B") for p in passed) > 1:
        raise ValueError("at most one distinct project per category")
    policy_id = "q" if not passed else "+".join(sorted(passed))
    result = constituent_mandates.evaluate(prepared["electorate_profile"], policy_id)
    expected = coalition_contracts.utility_vector(prepared["contract_profile"], passed)
    observed = [result["districts"][f"r{i}"]["total_relative_utility"]
                for i in coalition_contracts.ACTORS]
    if observed != expected:
        raise ValueError("district/citizen utility conservation failed")
    return result


def compare_passed(prepared, from_passed, to_passed):
    """Descriptively compare two valid B outcomes for every citizen."""
    before = evaluate_passed(prepared, from_passed)
    after = evaluate_passed(prepared, to_passed)
    comparison = constituent_mandates.compare(
        prepared["electorate_profile"], before["policy_id"], after["policy_id"])
    before_vector = coalition_contracts.utility_vector(prepared["contract_profile"], from_passed)
    after_vector = coalition_contracts.utility_vector(prepared["contract_profile"], to_passed)
    expected = [after_vector[i] - before_vector[i] for i in coalition_contracts.ACTORS]
    observed = [comparison["districts"][f"r{i}"]["total_utility_change"]
                for i in coalition_contracts.ACTORS]
    if observed != expected:
        raise ValueError("paired district/citizen utility conservation failed")
    return comparison
