"""Unfrozen, theory-constructed discovery frame for a constituent-level B pilot.

Four archetypes are generated before any model response and crossed with every
institutional arm. They are mechanism-discovery opportunities, not draws from
a population and not confirmatory evidence. Actor/citizen positions and a
bounded set of constituent intensities vary by seed; the archetypes remain
deliberately constructed.
"""
from __future__ import annotations

import random

from paper3 import coalition_contracts as game
from paper3 import constituent_contract_bridge as bridge
from paper3 import constituent_mandates


FAMILIES = (
    ("exchange_majority_conflict_outsider_harm", 5, "harm", "A"),
    ("exchange_majority_aligned_outsider_harm", 4, "harm", "B"),
    ("majority_conflict_outsider_support_control", 5, "support", "A"),
    ("aligned_control", None, "support", "aligned"),
)
POLICIES = {"q": [0, 0], "A0": [1, 0], "A1": [2, 0],
            "B0": [0, 1], "B1": [0, 2]}
SPECIFICATION = dict(citizens_per_district=9, priority_budget=4,
                     coordinate_bound=5)
# (weak own-issue ideal, strong own-issue ideal, strong own-issue priority).
# Each tuple was checked offline before any agent output for the two exchange
# archetypes; selection is from this whole declared set, not a response-based
# search. The frame is still highly stylized and not a population sample.
TYPE_PARAMETERS = ((-1, 4, 3), (-1, 5, 2), (-2, 5, 3))


def frame(seed):
    """Build exactly four fixed-budget profiles, with roles rotated by seed."""
    if type(seed) is not int or seed < 0:
        raise ValueError("nonnegative integer frame seed required")
    rng = random.Random(seed)
    result = []
    for index, (family, weak_count, outsider, proposer_type) in enumerate(FAMILIES):
        types = (["aligned"] * 7 if weak_count is None else
                 ["A"] * 3 + ["B"] * 3 + ["X"])
        rng.shuffle(types)
        proposer = rng.choice([i for i, kind in enumerate(types)
                               if kind == proposer_type])
        districts = {}
        for actor, kind in enumerate(types):
            if kind == "A":
                weak_ideal, strong_ideal, strong_priority = rng.choice(TYPE_PARAMETERS)
                weak = [weak_ideal, 1]
                strong = [strong_ideal, -1]
                priority = [strong_priority, 4 - strong_priority]
                citizens = [(weak, [2, 2])] * weak_count + [
                    (strong, priority)] * (9 - weak_count)
            elif kind == "B":
                weak_ideal, strong_ideal, strong_priority = rng.choice(TYPE_PARAMETERS)
                weak = [1, weak_ideal]
                strong = [-1, strong_ideal]
                priority = [4 - strong_priority, strong_priority]
                citizens = [(weak, [2, 2])] * weak_count + [
                    (strong, priority)] * (9 - weak_count)
            elif kind == "X":
                ideal = rng.choice(([-1, -1], [-2, -1], [-1, -2])) if outsider == "harm" else [2, 2]
                citizens = [(ideal, [2, 2])] * 9
            else:
                citizens = [([1, 1], [2, 2])] * 9
            rng.shuffle(citizens)
            districts[f"r{actor}"] = [
                dict(id=f"c{index}-{actor}-{j}", ideal=list(ideal),
                     weights=list(weights))
                for j, (ideal, weights) in enumerate(citizens)]
        electorate = dict(policies={k: list(v) for k, v in POLICIES.items()},
                          districts=districts)
        prepared = bridge.prepare_equal_standing(
            electorate, f"constituent-b-{seed}-{index}", proposer,
            **SPECIFICATION)
        inventory = game.offer_inventory(prepared["contract_profile"])
        strict = [offer for offer in inventory if offer["member_strict_improvement"]]
        result.append(dict(family=family, seed=seed, actor_types=types,
                           prepared=prepared, strict_exchange_offers=len(strict),
                           strict_with_outsider_harm=sum(bool(
                               offer["outsiders_harmed_vs_independent"])
                               for offer in strict),
                           citizen_first_choices=constituent_mandates.preference_counts(
                               prepared["electorate_profile"])))
    return result


def schedule(seed, episode_seed_base):
    """Cross every archetype with every arm; no post-response case selection."""
    if type(episode_seed_base) is not int or episode_seed_base < 0:
        raise ValueError("nonnegative integer episode seed base required")
    profiles = frame(seed)
    assignments = [dict(profile_id=item["prepared"]["contract_profile"]["id"],
                        family=item["family"], arm=arm,
                        seed_base=episode_seed_base + 100 * index)
                   for index, item in enumerate(profiles) for arm in game.ARMS]
    random.Random(seed + 918273).shuffle(assignments)
    return assignments
