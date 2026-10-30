"""Fixed candidate discovery schedule for outsider amendment institutions.

Only games 0 and 1 of each stratum are in this pilot. Games 2 and 3 are
unqueried reserves, not automatically confirmatory or authorized by a lead.
"""
from __future__ import annotations

import random

from paper3 import amendment_institution as institution
from paper3 import amendment_opportunity as opportunity


ORDER_SEED = 2026092813
SEED_BASE = 991000
CALLS_PER_EPISODE = 17
SEED_BLOCKS = (0, 1)
GAMES = (0, 1)


def profiles():
    return [opportunity.draw(game, stratum)
            for stratum in opportunity.STRATA for game in GAMES]


def assignments():
    rows = [dict(profile_id=item["profile"]["id"],
                 stratum=item["stratum"], game_id=item["game_id"],
                 favorite=item["favorite"], outsider_ideal=item["outsider_ideal"],
                 seed_block=block, arm=arm, intended_calls=CALLS_PER_EPISODE)
            for item in profiles() for block in SEED_BLOCKS
            for arm in institution.ARMS]
    random.Random(ORDER_SEED).shuffle(rows)
    scheduled = [dict(id=f"amendment-pilot-{index:02d}",
                      seed_base=SEED_BASE + 32 * index, **row)
                 for index, row in enumerate(rows)]
    seeds = [row["seed_base"] + i for row in scheduled
             for i in range(CALLS_PER_EPISODE)]
    if len(scheduled) != 24 or len(set(seeds)) != 408:
        raise ValueError("assignment inventory")
    return scheduled
