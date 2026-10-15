"""Prospective seven-profile constituent B schedule on the proven Qwen route.

Fresh constructed profiles are chosen before Qwen inference. They remain
mechanism-discovery cases, not a sample from a population of legislatures.
"""
from __future__ import annotations

import json
import random

from paper3 import coalition_contracts as game
from paper3 import constituent_b_design as generator


FRAME_SEEDS = (672100, 672200)
EPISODE_SEED_BASE = 673000
ORDER_SEED = 674999
CALLS_PER_EPISODE = 30


def profiles():
    first, second = (generator.frame(seed) for seed in FRAME_SEEDS)
    candidates = [*first, *second[:3]]
    utilities = [json.dumps(row["prepared"]["contract_profile"]["utilities"],
                            sort_keys=True) for row in candidates]
    if len(candidates) != 7 or len(set(utilities)) != 7:
        raise ValueError("fresh Qwen constituent utility inventory changed")
    return candidates


def assignments():
    rows = []
    for index, item in enumerate(profiles()):
        for arm in game.ARMS:
            rows.append(dict(profile_id=item["prepared"]["contract_profile"]["id"],
                             family=item["family"], arm=arm,
                             seed_base=EPISODE_SEED_BASE + index * 100,
                             intended_calls=CALLS_PER_EPISODE))
    random.Random(ORDER_SEED).shuffle(rows)
    return [dict(id=f"episode-{index:02d}", **row)
            for index, row in enumerate(rows)]
