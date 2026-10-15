"""Prospective paired-block discovery schedule; distinct from the gate.

Four theory-selected role/control cases, two arms and two request-seed blocks.
Each block of a case reuses the identical citizen table and agent-visible
prompt; only request seeds and archival ID differ. The two outsider-harm role
cases share one table. This is deliberately a noise-aware discovery pilot,
not a population sample or independent role-by-payoff replication.
"""
from __future__ import annotations

from copy import deepcopy
import random

from paper3 import direct_ratification as game
from paper3 import direct_ratification_design as base


FRAME_SEED = 905001
SEED_BASE = 908000
ORDER_SEED = 908999
BLOCKS = (0, 1)
CALLS_PER_EPISODE = 16


def profiles():
    rows = []
    for item in base.preflight(FRAME_SEED):
        for block in BLOCKS:
            row = deepcopy(item)
            row["block"] = block
            row["profile"]["id"] += f"-block-{block}"
            rows.append(row)
    if len(rows) != 8 or len({x["profile"]["id"] for x in rows}) != 8:
        raise ValueError("profile inventory")
    for first, second in zip(rows[::2], rows[1::2]):
        if (first["family"] != second["family"] or
                first["profile"]["districts"] != second["profile"]["districts"] or
                first["profile"]["proposer"] != second["profile"]["proposer"]):
            raise ValueError("repeated block changed prompt content")
    return rows


def assignments():
    rows = []
    for index, item in enumerate(profiles()):
        for arm in game.ARMS:
            rows.append(dict(profile_id=item["profile"]["id"],
                             family=item["family"], block=item["block"],
                             arm=arm, seed_base=SEED_BASE + index * 100 +
                             game.ARMS.index(arm) * 20,
                             intended_calls=CALLS_PER_EPISODE))
    random.Random(ORDER_SEED).shuffle(rows)
    if len(rows) != 16:
        raise ValueError("assignment inventory")
    seeds = [a["seed_base"] + i for a in rows for i in range(CALLS_PER_EPISODE)]
    if len(set(seeds)) != len(seeds):
        raise ValueError("request seed overlap")
    return [dict(id=f"ratification-pilot-{index:02d}", **row)
            for index, row in enumerate(rows)]
