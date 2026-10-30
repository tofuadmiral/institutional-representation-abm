"""Prospective synthetic opportunities for route jurisdiction; no LLM output.

Four declared structural families, with three seeded profiles each. The first
profile of each family is a possible discovery pilot; the others are reserved,
not confirmatory until a separate frozen protocol and model approval exist.
These constructed opportunities are not a sample of real legislatures.
"""
from __future__ import annotations

import random

from paper3 import route_jurisdiction as game


FAMILIES = ("bypass", "aligned_floor", "gridlock", "outsider_harm")
DEFAULT_SEED = 491701


def _draw_rows(rng, family):
    r = rng.randint
    # Canonical 0 proposes, 1/2/3 sit on committee, and 6 reviews.
    common = [r(1, 2) for _ in range(7)]
    h = [r(9, 12), r(6, 9), r(6, 9), r(-8, -5), r(6, 9), r(6, 9), r(-11, -8)]
    c = [r(4, 6), r(2, 4), r(-4, -1), r(2, 4), r(-4, -1), r(-4, -1), r(2, 4)]
    if family == "aligned_floor":
        h[2] = r(-7, -4)
        h[6] = r(3, 5)
        # Five floor supporters, but only one of the three committee seats.
    elif family == "gridlock":
        c[6] = r(-6, -3)
        common = [r(1, 2), r(1, 2)] + [r(-4, -1) for _ in range(4)] + [r(3, 5)]
    elif family == "outsider_harm":
        h[0] = r(6, 8)
        c = [r(10, 12), r(3, 5), r(-9, -6), r(3, 5), r(-9, -6), r(-9, -6), r(1, 3)]
    elif family != "bypass":
        raise ValueError("unknown opportunity family")
    return h, c, common


def frame(seed=DEFAULT_SEED, profiles_per_family=3):
    if type(seed) is not int or type(profiles_per_family) is not int or profiles_per_family < 1:
        raise ValueError("invalid frame parameters")
    rng = random.Random(seed)
    result = []
    for family_index, family in enumerate(FAMILIES):
        for index in range(profiles_per_family):
            h, c, z = _draw_rows(rng, family)
            actor_labels = [f"r{i}" for i in range(7)]
            policy_labels = ["p0", "p1", "p2"]
            rng.shuffle(actor_labels)
            rng.shuffle(policy_labels)
            utilities = {}
            for position, actor in enumerate(actor_labels):
                utilities[actor] = {"q": 0, policy_labels[0]: h[position],
                                    policy_labels[1]: c[position], policy_labels[2]: z[position]}
            # Keep opportunity-family labels out of the agents' messages.
            p = game.make_profile(f"case-{family_index * profiles_per_family + index}-seed{seed}", utilities,
                                  proposer=actor_labels[0], reviewer=actor_labels[6],
                                  committee=actor_labels[1:4],
                                  floor_threshold=5, committee_threshold=2)
            p["family"] = family
            p["split"] = "discovery_candidate" if index == 0 else "reserved"
            p["structural_policy_ids"] = dict(H=policy_labels[0], C=policy_labels[1], Z=policy_labels[2])
            result.append(p)
    return result


def opportunity_readout(profile):
    """Exact arithmetic certificate, not an agent prediction or desired sign."""
    return {arm: game.exact_opportunities(profile, arm) for arm in game.ARMS}
