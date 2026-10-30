"""Two prospective, distribution-matched threshold games.

Each game crosses a 5/9 versus 4/9 outsider referendum while holding its
district policy sums and all other citizen rows fixed. All arms and request
blocks are assigned before model output. These are theory-selected cases,
not a random sample of policies, elections or constituents.
"""
from __future__ import annotations

from copy import deepcopy
import random

from paper3 import direct_ratification as base


FRAME_SEED = 910027
ORDER_SEED = 910999
SEED_BASE = 911000
BLOCKS = (0, 1)
CALLS_PER_EPISODE = 16


def game_pair(game_id, seed=FRAME_SEED):
    if game_id not in (0, 1) or type(seed) is not int:
        raise ValueError("game/seed")
    rng = random.Random(seed + game_id * 1000)
    favorite = "X" if game_id == 0 else "Y"
    other = "Y" if favorite == "X" else "X"
    roles = ["favorite"] * (6 if game_id == 0 else 4)
    roles += ["compromise"] * (0 if game_id == 0 else 2)
    roles += ["outsider"]
    rng.shuffle(roles)
    proposer = roles.index("favorite")
    outsider = roles.index("outsider")
    outsider_order = list(range(9))
    rng.shuffle(outsider_order)
    districts = {}
    for actor, role in enumerate(roles):
        rows = []
        for index in range(9):
            utility = {"X": 0, "Y": 0, "C": 0}
            if role == "favorite":
                utility[favorite], utility["C"] = 3, 2
            elif role == "compromise":
                utility[favorite], utility["C"] = 1, 2
            else:
                utility[favorite], utility["C"] = (
                    (2 if index in outsider_order[:5] else -2), 1)
            rows.append(dict(id=f"threshold-{game_id}-{actor}-{index}",
                             utility=utility))
        districts[f"r{actor}"] = rows
    approve = dict(id=f"threshold-{game_id}-approve", proposer=proposer,
                   districts=districts)
    veto = deepcopy(approve)
    veto["id"] = f"threshold-{game_id}-veto"
    for index, citizen in enumerate(veto["districts"][f"r{outsider}"]):
        citizen["utility"][favorite] = (
            3 if index in outsider_order[:4] else -2)
    for profile in (approve, veto):
        base.validate(profile)
    totals = base.district_totals(approve)
    if totals != base.district_totals(veto):
        raise ValueError("aggregate mandate changed across distribution")
    if (base.poll(approve, favorite)["yes_counts"][f"r{outsider}"] != 5 or
            base.poll(veto, favorite)["yes_counts"][f"r{outsider}"] != 4 or
            not base.poll(approve, favorite)["approved"] or
            base.poll(veto, favorite)["approved"] or
            not base.poll(veto, "C")["approved"]):
        raise ValueError("threshold opportunity changed")
    welfare = {p: sum(row[p] for row in totals.values())
               for p in base.POLICIES}
    expected_favorite = 164 if game_id == 0 else 128
    if welfare[favorite] != expected_favorite or welfare["C"] != 117:
        raise ValueError("welfare opportunity changed")
    return dict(game_id=game_id, favorite=favorite, other=other,
                proposer=proposer, outsider=outsider, welfare=welfare,
                approve=approve, veto=veto)


def profiles():
    result = []
    for game_id in (0, 1):
        pair = game_pair(game_id)
        for distribution in ("approve", "veto"):
            for block in BLOCKS:
                profile = deepcopy(pair[distribution])
                profile["id"] += f"-block-{block}"
                result.append(dict(profile=profile, game_id=game_id,
                                   favorite=pair["favorite"],
                                   family=f"threshold_{distribution}",
                                   distribution=distribution, block=block,
                                   welfare=pair["welfare"],
                                   outsider=f"r{pair['outsider']}"))
    return result


def assignments():
    rows = []
    for index, item in enumerate(profiles()):
        for arm in base.ARMS:
            rows.append(dict(profile_id=item["profile"]["id"],
                             game_id=item["game_id"],
                             distribution=item["distribution"],
                             block=item["block"], arm=arm,
                             seed_base=SEED_BASE + index * 100 +
                             base.ARMS.index(arm) * 20,
                             intended_calls=CALLS_PER_EPISODE))
    random.Random(ORDER_SEED).shuffle(rows)
    seeds = [a["seed_base"] + i for a in rows for i in range(CALLS_PER_EPISODE)]
    if len(rows) != 16 or len(set(seeds)) != 256:
        raise ValueError("assignment/seed inventory")
    return [dict(id=f"threshold-pilot-{index:02d}", **row)
            for index, row in enumerate(rows)]
