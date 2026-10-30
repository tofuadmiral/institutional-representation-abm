"""Conditional, untouched same-generator constituent-B replication schedule.

These profiles were nominated by an offline opportunity/overlap audit before
the Qwen discovery allocation completed an episode. This module does not
authorize or launch a model run. Its fixed schedule is usable only if the
discovery audit warrants a separately frozen replication protocol.
"""
from __future__ import annotations

import json
import random

from paper3 import coalition_contracts as game
from paper3 import constituent_b_design as generator


FRAME_SEEDS = (692100, 692200, 692300)
EPISODE_SEED_BASE = 695000
ORDER_SEED = 696999
CALLS_PER_EPISODE = 30


def profiles():
    """Return three non-aligned families from each prespecified frame."""
    rows = [row for seed in FRAME_SEEDS for row in generator.frame(seed)[:3]]
    if len(rows) != 9:
        raise ValueError("replication profile inventory changed")
    utilities = [json.dumps(row["prepared"]["contract_profile"]["utilities"],
                            sort_keys=True) for row in rows]
    if len(set(utilities)) != 9:
        raise ValueError("replication profiles are not utility-distinct")
    if any(row["strict_with_outsider_harm"] <= 0 for row in rows
           if row["family"] != "majority_conflict_outsider_support_control"):
        raise ValueError("exchange opportunity missing")
    if any(row["strict_with_outsider_harm"] != 0 for row in rows
           if row["family"] == "majority_conflict_outsider_support_control"):
        raise ValueError("control gained strict outsider-harm opportunity")
    return rows


def assignments():
    """Cross all nine profiles with all three rules, paired by request seed."""
    rows = []
    for index, item in enumerate(profiles()):
        for arm in game.ARMS:
            rows.append(dict(profile_id=item["prepared"]["contract_profile"]["id"],
                             family=item["family"], arm=arm,
                             seed_base=EPISODE_SEED_BASE + 100 * index,
                             intended_calls=CALLS_PER_EPISODE))
    random.Random(ORDER_SEED).shuffle(rows)
    return [dict(id=f"replication-episode-{index:02d}", **row)
            for index, row in enumerate(rows)]
