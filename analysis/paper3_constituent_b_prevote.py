"""Pre-vote proposal readout for the constituent-institution discovery.

These are full-delivery *proposal* metrics, not enacted outcomes. Keep them
separate from consent, requested ballots, executed ballots and citizen outcomes
of the actual game. This module was written while the frozen Qwen run was live,
before any complete episode or matched institutional outcome was available.
"""
from __future__ import annotations

from paper3 import coalition_contracts as game
from paper3 import constituent_contract_bridge as bridge


def _projects(offer):
    if not isinstance(offer, dict) or not isinstance(offer.get("projects"), dict):
        raise ValueError("offer projects required")
    projects = offer["projects"]
    if set(projects) != {"A", "B"}:
        raise ValueError("exactly one project per category required")
    if projects["A"] not in game.PROJECTS["A"] or projects["B"] not in game.PROJECTS["B"]:
        raise ValueError("offer project outside menu")
    return [projects["A"], projects["B"]]


def score_offer(prepared, offer):
    """Score the proposed pair as if both projects passed, for every citizen."""
    proposed = _projects(offer)
    outcome = bridge.evaluate_passed(prepared, proposed)
    districts = outcome["districts"]
    proposer = prepared["contract_profile"]["proposer"]
    return dict(
        projects=dict(offer["projects"]),
        first=offer["first"],
        coalition=sorted(offer["coalition"]),
        full_delivery_policy=outcome["policy_id"],
        total_citizen_relative_utility=outcome["overall"]["total_relative_utility"],
        citizens_worse_than_status_quo=outcome["overall"]["citizens_worse_than_q"],
        worst_district_relative_utility=min(
            item["total_relative_utility"] for item in districts.values()),
        proposer_district_relative_utility=districts[f"r{proposer}"]["total_relative_utility"],
        district_relative_utilities={key: value["total_relative_utility"]
                                     for key, value in districts.items()},
    )


def compare_offers(prepared, left_offer, right_offer):
    """Compare two offers before any consent or enforcement is applied.

    The comparison is descriptive for a fixed constituent profile. Its
    institution labels, if any, belong to the caller's frozen assignment.
    """
    left = score_offer(prepared, left_offer)
    right = score_offer(prepared, right_offer)
    paired = bridge.compare_passed(
        prepared, _projects(left_offer), _projects(right_offer))
    changes = [row["utility_change"] for row in paired["citizens"].values()]
    return dict(
        left=left, right=right,
        terms_changed=(left["projects"], left["first"], left["coalition"]) !=
                      (right["projects"], right["first"], right["coalition"]),
        full_delivery_policy_changed=left["full_delivery_policy"] !=
                                     right["full_delivery_policy"],
        total_citizen_utility_change=right["total_citizen_relative_utility"] -
                                     left["total_citizen_relative_utility"],
        citizens_gain=sum(value > 0 for value in changes),
        citizens_lose=sum(value < 0 for value in changes),
        citizens_tie=sum(value == 0 for value in changes),
        citizen_comparison=paired,
    )
