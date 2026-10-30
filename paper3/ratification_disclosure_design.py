"""Prospective selected-case disclosure institution schedule.

Outsider aggregate utility is held fixed across 5/9 and 4/9 citizen-vote
variants, but the outsider representative's aggregate mandate now prefers
the chamber favorite to compromise. Information access is a treatment:
public rows, private voluntary responses, or private responses followed by
a controller-certified yes-count bulletin before the final proposal.
"""
from __future__ import annotations

from copy import deepcopy
import random

from paper3 import direct_ratification as base


FRAME_SEED = 913027
ORDER_SEED = 913999
SEED_BASE = 914000
INFORMATION = ("public", "private", "certified")
CALLS_PER_EPISODE = 16


def game_pair(game_id, seed=FRAME_SEED):
    if type(game_id) is not int or game_id not in (0, 1) or type(seed) is not int:
        raise ValueError("game/seed")
    rng = random.Random(seed + 1000 * game_id)
    favorite = "X" if game_id == 0 else "Y"
    roles = ["favorite"] * (6 if game_id == 0 else 4)
    roles += ["compromise"] * (0 if game_id == 0 else 2)
    roles += ["outsider"]
    rng.shuffle(roles)
    proposer = roles.index("favorite")
    outsider = roles.index("outsider")
    positions = list(range(9))
    rng.shuffle(positions)
    districts = {}
    for actor, role in enumerate(roles):
        citizens = []
        for index in range(9):
            utility = {"X": 0, "Y": 0, "C": 0}
            if role == "favorite":
                utility[favorite], utility["C"] = 3, 2
            elif role == "compromise":
                utility[favorite], utility["C"] = 1, 2
            else:
                utility[favorite] = 4 if index in positions[:5] else -2
                utility["C"] = 1
            citizens.append(dict(id=f"disclosure-{game_id}-{actor}-{index}",
                                 utility=utility))
        districts[f"r{actor}"] = citizens
    approve = dict(id=f"disclosure-{game_id}-approve", proposer=proposer,
                   districts=districts)
    veto = deepcopy(approve)
    veto["id"] = f"disclosure-{game_id}-veto"
    for index, citizen in enumerate(veto["districts"][f"r{outsider}"]):
        citizen["utility"][favorite] = 8 if index in positions[:4] else -4
    for profile in (approve, veto):
        base.validate(profile)
    totals = base.district_totals(approve)
    if totals != base.district_totals(veto):
        raise ValueError("aggregate mandate changed")
    if totals[f"r{outsider}"][favorite] != 12 or totals[f"r{outsider}"]["C"] != 9:
        raise ValueError("outsider aggregate opportunity changed")
    if (base.poll(approve, favorite)["yes_counts"][f"r{outsider}"] != 5 or
            base.poll(veto, favorite)["yes_counts"][f"r{outsider}"] != 4 or
            not base.poll(approve, favorite)["approved"] or
            base.poll(veto, favorite)["approved"] or
            not base.poll(veto, "C")["approved"]):
        raise ValueError("referendum opportunity changed")
    welfare = {policy: sum(row[policy] for row in totals.values())
               for policy in base.POLICIES}
    if welfare[favorite] != (174 if game_id == 0 else 138) or welfare["C"] != 117:
        raise ValueError("welfare opportunity changed")
    return dict(game_id=game_id, favorite=favorite,
                proposer=proposer, outsider=outsider, welfare=welfare,
                approve=approve, veto=veto)


def profiles():
    rows = []
    for game_id in (0, 1):
        pair = game_pair(game_id)
        for distribution in ("approve", "veto"):
            rows.append(dict(profile=pair[distribution], game_id=game_id,
                             family=f"disclosure_{distribution}",
                             distribution=distribution,
                             favorite=pair["favorite"],
                             outsider=f"r{pair['outsider']}",
                             welfare=pair["welfare"]))
    return rows


def assignments():
    rows = []
    for index, item in enumerate(profiles()):
        for information in INFORMATION:
            for arm in base.ARMS:
                rows.append(dict(profile_id=item["profile"]["id"],
                                 game_id=item["game_id"],
                                 distribution=item["distribution"],
                                 information=information, arm=arm,
                                 seed_base=SEED_BASE + index * 200 +
                                 INFORMATION.index(information) * 40 +
                                 base.ARMS.index(arm) * 20,
                                 intended_calls=CALLS_PER_EPISODE))
    random.Random(ORDER_SEED).shuffle(rows)
    seeds = [a["seed_base"] + i for a in rows for i in range(CALLS_PER_EPISODE)]
    if len(rows) != 24 or len(set(seeds)) != 384:
        raise ValueError("assignment/seed inventory")
    return [dict(id=f"disclosure-pilot-{index:02d}", **row)
            for index, row in enumerate(rows)]
