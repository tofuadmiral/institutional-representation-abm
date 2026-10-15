"""Fresh-table Qwen repeatability check, not a population replication.

Two exchange utility tables are held exactly fixed across three paired seed
blocks. Numeric profile IDs vary only to keep the archival assignment ledger
unambiguous. An aligned control is included once as an interface check.
"""
from __future__ import annotations

from copy import deepcopy
import random

from paper3 import coalition_contracts as game
from paper3 import constituent_b_design as generator


FRAME_SEED = 702400
EPISODE_SEED_BASE = 703000
ORDER_SEED = 704999
CALLS_PER_EPISODE = 30
BLOCKS = (0, 1, 2)


def profiles():
    frame = generator.frame(FRAME_SEED)
    if len(frame) != 4 or frame[0]["family"] != "exchange_majority_conflict_outsider_harm" or frame[1]["family"] != "exchange_majority_aligned_outsider_harm" or frame[3]["family"] != "aligned_control":
        raise ValueError("fresh repeatability frame changed")
    rows = []
    for family_index in (0, 1):
        if frame[family_index]["strict_with_outsider_harm"] <= 0:
            raise ValueError("exchange opportunity disappeared")
        for block in BLOCKS:
            row = deepcopy(frame[family_index])
            row["prepared"]["contract_profile"]["id"] += f"-block-{block}"
            row["repeatability_block"] = block
            rows.append(row)
    control = deepcopy(frame[3])
    control["prepared"]["contract_profile"]["id"] += "-control"
    control["repeatability_block"] = None
    rows.append(control)
    if len({row["prepared"]["contract_profile"]["id"] for row in rows}) != 7:
        raise ValueError("repeatability profile IDs overlap")
    return rows


def assignments():
    rows = []
    for index, item in enumerate(profiles()):
        for arm in game.ARMS:
            rows.append(dict(profile_id=item["prepared"]["contract_profile"]["id"],
                             family=item["family"], arm=arm,
                             repeatability_block=item["repeatability_block"],
                             seed_base=EPISODE_SEED_BASE + 100 * index,
                             intended_calls=CALLS_PER_EPISODE))
    random.Random(ORDER_SEED).shuffle(rows)
    return [dict(id=f"repeatability-episode-{index:02d}", **row)
            for index, row in enumerate(rows)]
