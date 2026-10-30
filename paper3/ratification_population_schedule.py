"""Unfrozen candidate schedule for a fresh, paired ratification population.

The first nine payoff games are discovery; fifteen others are untouched
validation reserves. No model call is authorized merely by this module.
"""
from __future__ import annotations

import random

from paper3 import direct_ratification as game
from paper3 import ratification_population_design as population


ORDER_SEED = 2026092823
SEED_BASE = 1300000
CALLS_PER_EPISODE = 16
DISCOVERY_IDS = tuple(range(9))
VALIDATION_IDS = tuple(range(9, population.GAME_COUNT))
STAGES = ("discovery", "validation")


def game_ids(stage):
    if stage == "discovery":
        return DISCOVERY_IDS
    if stage == "validation":
        return VALIDATION_IDS
    raise ValueError("unknown stage")


def assignments(stage):
    ids = game_ids(stage)
    rows = []
    for game_id in ids:
        item = population.game_pair(game_id)
        for distribution in ("veto", "approve"):
            for arm in game.ARMS:
                rows.append(dict(stage=stage, game_id=game_id,
                                 profile_id=item[distribution]["id"],
                                 distribution=distribution, arm=arm,
                                 favorite=item["favorite"],
                                 alternative_a=item["alternative_a"],
                                 alternative_b=item["alternative_b"],
                                 intended_calls=CALLS_PER_EPISODE))
    random.Random(ORDER_SEED + (0 if stage == "discovery" else 1)).shuffle(rows)
    scheduled = []
    for index, row in enumerate(rows):
        # A separate range for validation prevents overlap despite shuffled order.
        offset = 0 if stage == "discovery" else 10000
        scheduled.append(dict(id=f"ratification-population-{stage}-{index:02d}",
                              seed_base=SEED_BASE + offset + 32 * index,
                              **row))
    seeds = [row["seed_base"] + i for row in scheduled
             for i in range(CALLS_PER_EPISODE)]
    if len(seeds) != 4 * len(ids) * CALLS_PER_EPISODE or \
            len(set(seeds)) != len(seeds):
        raise ValueError("assignment or seed inventory")
    return scheduled


def profiles(stage):
    return {item[distribution]["id"]: item[distribution]
            for game_id in game_ids(stage)
            for item in (population.game_pair(game_id),)
            for distribution in ("veto", "approve")}
