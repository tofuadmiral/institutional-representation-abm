"""Offline chamber-pivotal disclosure opportunities, not an experiment schedule.

The ordinary disclosure inventory makes compromise positive for all district
mandates. These draws instead give four to six representatives positive
compromise sums while every district's citizen majority approves compromise.
Thus a feasible policy still needs a nontrivial chamber coalition. None of
these tables has been exposed to a model or selected by a model response.
"""
from __future__ import annotations

from copy import deepcopy
import random

from paper3 import direct_ratification as base
from paper3 import ratification_disclosure_validation_design as prior


DESIGN_SEED = 2026092805
SUPPORT_TARGETS = ((4, 4), (5, 4), (6, 5), (4, 6), (5, 5), (6, 6))
ORDER_SEED = 2026092806
REQUEST_SEED_BASE = 975000
CALLS_PER_EPISODE = 16


def _policy_values(rng: random.Random, positive_sum: bool,
                   proposer_favorite: bool = False) -> list[int]:
    if proposer_favorite:
        yes = rng.randint(7, 9)
        values = [rng.randint(5, 7) for _ in range(yes)] + [
            -rng.randint(1, 2) for _ in range(9 - yes)]
    elif positive_sum:
        yes = rng.randint(5, 9)
        values = [rng.randint(3, 5) for _ in range(yes)] + [
            -rng.randint(1, 2) for _ in range(9 - yes)]
    else:
        yes = rng.randint(5, 7)
        values = [1] * yes + [-rng.randint(5, 7) for _ in range(9 - yes)]
    rng.shuffle(values)
    if (sum(values) > 0) is not (positive_sum or proposer_favorite):
        raise ValueError("constructed mandate sign")
    return values


def game_pair(game_id: int, seed: int = DESIGN_SEED) -> dict:
    if type(game_id) is not int or not 0 <= game_id < len(SUPPORT_TARGETS):
        raise ValueError("game id")
    if type(seed) is not int:
        raise ValueError("seed")
    rng = random.Random(seed + 104729 * game_id)
    favorite = rng.choice(("X", "Y"))
    other = "Y" if favorite == "X" else "X"
    proposer, outsider = rng.sample(list(base.ACTORS), 2)
    others = [actor for actor in base.ACTORS if actor not in (proposer, outsider)]
    favorite_target, compromise_target = SUPPORT_TARGETS[game_id]
    favorite_support = {proposer, outsider} | set(rng.sample(others, favorite_target - 2))
    compromise_support = {proposer, outsider} | set(rng.sample(others, compromise_target - 2))
    districts = {}
    for actor in base.ACTORS:
        if actor == outsider:
            compromise_values = [1] * 9
            favorite_values = prior._outsider_favorite(rng, 9 + rng.randint(1, 5), 5)
        elif actor == proposer:
            favorite_values = _policy_values(rng, True, proposer_favorite=True)
            compromise_values = _policy_values(rng, True)
            if sum(favorite_values) <= sum(compromise_values):
                raise ValueError("agenda holder mandate ordering")
        else:
            favorite_values = _policy_values(rng, actor in favorite_support)
            compromise_values = _policy_values(rng, actor in compromise_support)
        districts[f"r{actor}"] = [
            dict(id=f"disclosure-chamber-{game_id}-{actor}-{index}",
                 utility={favorite: favorite_values[index], other: 0,
                          "C": compromise_values[index]})
            for index in range(9)]
    approve = dict(id=f"disclosure-chamber-{game_id}-approve",
                   proposer=proposer, districts=districts)
    veto = deepcopy(approve)
    veto["id"] = f"disclosure-chamber-{game_id}-veto"
    total = sum(citizen["utility"][favorite]
                for citizen in districts[f"r{outsider}"])
    veto_values = prior._outsider_favorite(rng, total, 4)
    for citizen, value in zip(veto["districts"][f"r{outsider}"], veto_values):
        citizen["utility"][favorite] = value
    for profile in (approve, veto):
        base.validate(profile)
    totals = base.district_totals(approve)
    if totals != base.district_totals(veto):
        raise ValueError("paired aggregates differ")
    if (base.poll(approve, favorite)["approved"] is not True or
            base.poll(veto, favorite)["approved"] is not False or
            base.poll(veto, "C")["approved"] is not True or
            base.poll(approve, favorite)["yes_counts"][f"r{outsider}"] != 5 or
            base.poll(veto, favorite)["yes_counts"][f"r{outsider}"] != 4):
        raise ValueError("ratification opportunity")
    favorite_sums = {actor for actor in base.ACTORS
                     if totals[f"r{actor}"][favorite] > 0}
    compromise_sums = {actor for actor in base.ACTORS
                       if totals[f"r{actor}"]["C"] > 0}
    if (favorite_sums != favorite_support or
            compromise_sums != compromise_support or
            not totals[f"r{outsider}"][favorite] > totals[f"r{outsider}"]["C"]):
        raise ValueError("chamber or outsider mandate opportunity")
    welfare = {policy: sum(row[policy] for row in totals.values())
               for policy in base.POLICIES}
    return dict(game_id=game_id, favorite=favorite, proposer=proposer,
                outsider=outsider, favorite_support=sorted(favorite_support),
                compromise_support=sorted(compromise_support), welfare=welfare,
                approve=approve, veto=veto)


def inventory() -> list[dict]:
    return [game_pair(game_id) for game_id in range(len(SUPPORT_TARGETS))]


def profiles() -> list[dict]:
    rows = []
    for game in inventory():
        for distribution in ("approve", "veto"):
            rows.append(dict(profile=game[distribution], game_id=game["game_id"],
                             distribution=distribution, favorite=game["favorite"],
                             outsider=f'r{game["outsider"]}',
                             favorite_support=game["favorite_support"],
                             compromise_support=game["compromise_support"],
                             welfare=game["welfare"]))
    return rows


def assignments() -> list[dict]:
    """Candidate hard-game schedule; it does not itself authorize inference."""
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
    rng = random.Random(ORDER_SEED)
    rng.shuffle(rows)
    scheduled = [dict(id=f"chamber-disclosure-{index:02d}",
                      seed_base=REQUEST_SEED_BASE + index * 32, **row)
                 for index, row in enumerate(rows)]
    seeds = [row["seed_base"] + index for row in scheduled
             for index in range(CALLS_PER_EPISODE)]
    if len(scheduled) != 54 or len(set(seeds)) != 864:
        raise ValueError("chamber assignment inventory")
    return scheduled
