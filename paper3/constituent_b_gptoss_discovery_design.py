"""Predeclared seven-profile, three-institution discovery schedule.

Two independent generator seeds yield seven distinct utility structures: two
instances of each conflict/control archetype and one aligned control. The
second aligned profile is omitted *before* inference because its district
utility table is exactly the first aligned profile's. These are constructed
opportunities, not draws from a target population.
"""
from __future__ import annotations

import json
import random

from paper3 import coalition_contracts as game
from paper3 import constituent_b_design as generator


FRAME_SEEDS = (665100, 665200)
EPISODE_SEED_BASE = 666000
ORDER_SEED = 667999
CALLS_PER_EPISODE = 30


def profiles():
    first, second = (generator.frame(seed) for seed in FRAME_SEEDS)
    result = [*first, *second[:3]]
    utilities = [json.dumps(item["prepared"]["contract_profile"]["utilities"],
                            sort_keys=True) for item in result]
    if len(result) != 7 or len(set(utilities)) != 7:
        raise ValueError("predeclared discovery utility structures changed")
    for index, item in enumerate(result):
        expected_exchange = index % 4 < 2 if index < 4 else (index - 4) < 2
        if bool(item["strict_exchange_offers"]) != expected_exchange:
            raise ValueError("discovery opportunity/control classification changed")
    return result


def assignments():
    prepared = profiles()
    phase_one, phase_two = [], []
    for index, item in enumerate(prepared):
        for arm in game.ARMS:
            value = dict(profile_id=item["prepared"]["contract_profile"]["id"],
                         family=item["family"], arm=arm,
                         seed_base=EPISODE_SEED_BASE + index * 100,
                         intended_calls=CALLS_PER_EPISODE,
                         phase=1 if index == 0 else 2)
            (phase_one if index == 0 else phase_two).append(value)
    rng = random.Random(ORDER_SEED)
    rng.shuffle(phase_one)
    rng.shuffle(phase_two)
    result = [*phase_one, *phase_two]
    return [dict(id=f"episode-{index:02d}", **item)
            for index, item in enumerate(result)]
