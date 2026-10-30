"""Untouched, independently drawn ratification games for possible validation.

This is an offline opportunity inventory, not a run schedule or evidence.
Every game is generated without conditioning on any model outcome. The paired
outsider districts differ in the number of citizens who would approve the
chamber favorite, while their exact policy-utility sums remain unchanged.
"""
from __future__ import annotations

from copy import deepcopy
import random

from paper3 import direct_ratification as base


DESIGN_SEED = 2026092803
FAVORITE_SEATS = (4, 5, 6, 4, 5, 6)
ORDER_SEED = 2026092804
REQUEST_SEED_BASE = 970000
CALLS_PER_EPISODE = 16


def _partition(rng: random.Random, total: int, count: int) -> list[int]:
    """Draw a bounded positive integer allocation with the requested sum."""
    if not count <= total <= 10 * count:
        raise ValueError("bounded positive composition")
    values = [1] * count
    remaining = total - count
    while remaining:
        index = rng.choice([i for i, value in enumerate(values) if value < 10])
        values[index] += 1
        remaining -= 1
    rng.shuffle(values)
    return values


def _district(rng: random.Random, favorite: str, role: str) -> list[dict]:
    if role == "favorite":
        compromise = [rng.randint(1, 3) for _ in range(9)]
        preferred = _partition(rng, sum(compromise) + rng.randint(2, 12), 9)
    elif role == "compromise":
        preferred = [rng.randint(1, 3) for _ in range(9)]
        compromise = _partition(rng, sum(preferred) + rng.randint(2, 18), 9)
    else:
        raise ValueError("district role")
    return [{"utility": {favorite: preferred[i],
                         "Y" if favorite == "X" else "X": 0,
                         "C": compromise[i]}}
            for i in range(9)]


def _outsider_favorite(rng: random.Random, total: int, yes: int) -> list[int]:
    if yes not in (4, 5):
        raise ValueError("outsider approval count")
    negatives = [-rng.randint(1, 2) for _ in range(9 - yes)]
    positives = _partition(rng, total - sum(negatives), yes)
    values = positives + negatives
    rng.shuffle(values)
    return values


def game_pair(game_id: int, seed: int = DESIGN_SEED) -> dict:
    """Return one draw and its matched 5/9 and 4/9 outsider variants."""
    if type(game_id) is not int or not 0 <= game_id < len(FAVORITE_SEATS):
        raise ValueError("game id")
    if type(seed) is not int:
        raise ValueError("seed")
    rng = random.Random(seed + 104729 * game_id)
    favorite = rng.choice(("X", "Y"))
    roles = (["favorite"] * FAVORITE_SEATS[game_id] +
             ["compromise"] * (6 - FAVORITE_SEATS[game_id]) + ["outsider"])
    rng.shuffle(roles)
    favorite_actors = [actor for actor, role in enumerate(roles)
                       if role == "favorite"]
    proposer = rng.choice(favorite_actors)
    outsider = roles.index("outsider")
    districts = {}
    for actor, role in enumerate(roles):
        if role == "outsider":
            compromise = [rng.randint(1, 2) for _ in range(9)]
            favorite_total = sum(compromise) + rng.randint(1, 5)
            favorite_values = _outsider_favorite(rng, favorite_total, 5)
            citizens = [{"utility": {favorite: favorite_values[i],
                                     "Y" if favorite == "X" else "X": 0,
                                     "C": compromise[i]}}
                        for i in range(9)]
        else:
            citizens = _district(rng, favorite, role)
        for index, citizen in enumerate(citizens):
            citizen["id"] = f"disclosure-validation-{game_id}-{actor}-{index}"
        districts[f"r{actor}"] = citizens
    approve = dict(id=f"disclosure-validation-{game_id}-approve",
                   proposer=proposer, districts=districts)
    veto = deepcopy(approve)
    veto["id"] = f"disclosure-validation-{game_id}-veto"
    total = sum(c["utility"][favorite] for c in districts[f"r{outsider}"])
    veto_values = _outsider_favorite(rng, total, 4)
    for citizen, value in zip(veto["districts"][f"r{outsider}"], veto_values):
        citizen["utility"][favorite] = value
    for profile in (approve, veto):
        base.validate(profile)
    totals = base.district_totals(approve)
    if totals != base.district_totals(veto):
        raise ValueError("paired aggregates differ")
    if not totals[f"r{outsider}"][favorite] > totals[f"r{outsider}"]["C"]:
        raise ValueError("outsider mandate opportunity")
    if (base.poll(approve, favorite)["yes_counts"][f"r{outsider}"] != 5 or
            base.poll(veto, favorite)["yes_counts"][f"r{outsider}"] != 4 or
            not base.poll(approve, favorite)["approved"] or
            base.poll(veto, favorite)["approved"] or
            not base.poll(veto, "C")["approved"]):
        raise ValueError("ratification opportunity")
    welfare = {policy: sum(row[policy] for row in totals.values())
               for policy in base.POLICIES}
    return dict(game_id=game_id, favorite=favorite, proposer=proposer,
                outsider=outsider, roles=roles, welfare=welfare,
                approve=approve, veto=veto)


def inventory() -> list[dict]:
    return [game_pair(game_id) for game_id in range(len(FAVORITE_SEATS))]


def profiles() -> list[dict]:
    rows = []
    for game in inventory():
        for distribution in ("approve", "veto"):
            rows.append(dict(profile=game[distribution], game_id=game["game_id"],
                             distribution=distribution, favorite=game["favorite"],
                             outsider=f'r{game["outsider"]}',
                             welfare=game["welfare"]))
    return rows


def assignments() -> list[dict]:
    """Untouched candidate schedule; returning it does not approve a paid run."""
    rows = []
    for item in profiles():
        treatments = [(information, arm)
                      for information in ("private", "certified")
                      for arm in base.ARMS]
        if item["distribution"] == "veto":
            treatments.append(("public", "binding_ratification"))
        for information, arm in treatments:
            rows.append(dict(profile_id=item["profile"]["id"],
                             game_id=item["game_id"],
                             distribution=item["distribution"],
                             information=information, arm=arm,
                             intended_calls=CALLS_PER_EPISODE))
    random.Random(ORDER_SEED).shuffle(rows)
    scheduled = [dict(id=f"disclosure-validation-{index:02d}",
                      seed_base=REQUEST_SEED_BASE + index * 32, **row)
                 for index, row in enumerate(rows)]
    seeds = [row["seed_base"] + index for row in scheduled
             for index in range(CALLS_PER_EPISODE)]
    if len(scheduled) != 54 or len(set(seeds)) != 864:
        raise ValueError("validation assignment inventory")
    return scheduled
