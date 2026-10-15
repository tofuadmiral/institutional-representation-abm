"""Offline bargaining opportunity for an outsider amendment-versus-veto study.

No model calls or outcomes are used to construct this frame. The two strata
separate the outsider representative's *summed* mandate from a 5/9 citizen
approval rule. This is a candidate discovery frame, not confirmatory evidence.
"""
from __future__ import annotations

import random

from paper3 import direct_ratification as base


DESIGN_SEED = 2026092811
# The insider favorite varies in majority size. Five districts value the
# compromise positively, but only four (aligned) or three (divergent)
# strictly prefer it to the insider favorite. The ideal has three backers.
SUPPORT_TARGETS = ((4, 5, 3), (5, 5, 3), (6, 5, 3), (4, 5, 3))
STRATA = ("mandate_aligned", "mandate_divergent")


def _values(rng: random.Random, *, positive_sum: bool,
            large: bool = False) -> list[int]:
    if positive_sum:
        yes = rng.randint(5, 7)
        high = (5, 7) if large else (3, 5)
        values = [rng.randint(*high) for _ in range(yes)] + [
            -rng.randint(1, 2) for _ in range(9 - yes)]
    else:
        yes = rng.randint(2, 4)
        values = [rng.randint(1, 2) for _ in range(yes)] + [
            -rng.randint(3, 5) for _ in range(9 - yes)]
    rng.shuffle(values)
    if (sum(values) > 0) is not positive_sum:
        raise ValueError("mandate sign construction failed")
    return values


def _outsider_values(rng: random.Random, stratum: str) -> tuple[list[int], list[int], list[int]]:
    # Both strata have precisely four citizens approving the insider favorite.
    # Only the representative's summed mandate changes sign/order.
    if stratum == "mandate_aligned":
        favorite = [rng.randint(1, 2) for _ in range(4)] + [
            -rng.randint(3, 4) for _ in range(5)]
        compromise = [rng.randint(2, 3) for _ in range(9)]
    elif stratum == "mandate_divergent":
        favorite = [rng.randint(7, 9) for _ in range(4)] + [
            -rng.randint(1, 2) for _ in range(5)]
        compromise = [rng.randint(1, 2) for _ in range(9)]
    else:
        raise ValueError("unknown stratum")
    rng.shuffle(favorite)
    rng.shuffle(compromise)
    ideal = [rng.randint(5, 7) for _ in range(9)]
    if not sum(ideal) > max(sum(favorite), sum(compromise)):
        raise ValueError("outsider ideal ordering failed")
    return favorite, compromise, ideal


def draw(game_id: int, stratum: str, seed: int = DESIGN_SEED) -> dict:
    """Draw a seven-district game with two viable chamber policies.

    The fixed role/support frame is chosen for ex-ante strategic opportunity,
    never by querying or selecting on an LLM's observed actions.
    """
    if type(game_id) is not int or not 0 <= game_id < len(SUPPORT_TARGETS):
        raise ValueError("game id")
    if stratum not in STRATA or type(seed) is not int:
        raise ValueError("stratum or seed")
    rng = random.Random(seed + 104729 * game_id + 7919 * STRATA.index(stratum))
    favorite = rng.choice(("X", "Y"))
    other = "Y" if favorite == "X" else "X"
    proposer, outsider = rng.sample(list(base.ACTORS), 2)
    others = [a for a in base.ACTORS if a not in (proposer, outsider)]
    favorite_target, compromise_target, ideal_target = SUPPORT_TARGETS[game_id]
    favorite_support = {proposer} | ({outsider} if stratum == "mandate_divergent" else set())
    favorite_support |= set(rng.sample(others, favorite_target - len(favorite_support)))
    compromise_support = {proposer, outsider} | set(
        rng.sample(others, compromise_target - 2))
    ideal_support = {outsider} | set(rng.sample(others, ideal_target - 1))
    districts = {}
    for actor in base.ACTORS:
        if actor == outsider:
            favorite_values, compromise_values, ideal_values = _outsider_values(rng, stratum)
        elif actor == proposer:
            favorite_values = _values(rng, positive_sum=True, large=True)
            compromise_values = [rng.randint(1, 2) for _ in range(9)]
            ideal_values = [-rng.randint(6, 8) for _ in range(9)]
        else:
            favorite_values = _values(rng, positive_sum=actor in favorite_support)
            compromise_values = ([rng.randint(6, 8) for _ in range(9)]
                                 if actor in compromise_support else
                                 [-rng.randint(6, 8) for _ in range(9)])
            ideal_values = ([rng.randint(6, 8) for _ in range(9)]
                            if actor in ideal_support else
                            [-rng.randint(6, 8) for _ in range(9)])
        districts[f"r{actor}"] = [
            dict(id=f"amendment-{stratum}-{game_id}-{actor}-{i}",
                 utility={favorite: favorite_values[i], other: ideal_values[i],
                          "C": compromise_values[i]})
            for i in range(9)]
    profile = dict(id=f"amendment-{stratum}-{game_id}-seed{seed}",
                   proposer=proposer, districts=districts)
    base.validate(profile)
    totals = base.district_totals(profile)
    actual_favorite = {a for a in base.ACTORS if totals[f"r{a}"][favorite] > 0}
    actual_compromise = {a for a in base.ACTORS if totals[f"r{a}"]["C"] > 0}
    actual_ideal = {a for a in base.ACTORS if totals[f"r{a}"][other] > 0}
    if (actual_favorite != favorite_support or actual_compromise != compromise_support
            or actual_ideal != ideal_support):
        raise ValueError("chamber support construction failed")
    strategic_compromise = {a for a in base.ACTORS
                            if totals[f"r{a}"]["C"] > totals[f"r{a}"][favorite]}
    strategic_ideal = {a for a in base.ACTORS
                       if totals[f"r{a}"][other] > totals[f"r{a}"][favorite]}
    expected_compromise = 4 if stratum == "mandate_aligned" else 3
    if len(strategic_compromise) != expected_compromise or len(strategic_ideal) != 3:
        raise ValueError(f"strategic opposition frame failed: C={sorted(strategic_compromise)}, "
                         f"I={sorted(strategic_ideal)}, expected_C={expected_compromise}")
    outsider_row = totals[f"r{outsider}"]
    if (base.poll(profile, favorite)["yes_counts"][f"r{outsider}"] != 4
            or base.poll(profile, "C")["yes_counts"][f"r{outsider}"] != 9
            or not outsider_row["C"] > 0):
        raise ValueError("outsider citizen opportunity failed")
    if not outsider_row[other] > max(outsider_row["C"], outsider_row[favorite]):
        raise ValueError("outsider ideal ordering failed")
    if stratum == "mandate_aligned" and not outsider_row["C"] > outsider_row[favorite]:
        raise ValueError("aligned outsider mandate failed")
    if stratum == "mandate_divergent" and not outsider_row[favorite] > outsider_row["C"]:
        raise ValueError("divergent outsider mandate failed")
    if not totals[f"r{proposer}"][favorite] > totals[f"r{proposer}"]["C"]:
        raise ValueError("agenda mandate ordering failed")
    return dict(profile=profile, game_id=game_id, stratum=stratum,
                favorite=favorite, outsider_ideal=other, outsider=outsider,
                favorite_support=sorted(favorite_support),
                compromise_support=sorted(compromise_support),
                outsider_ideal_support=sorted(ideal_support),
                compromise_over_favorite=sorted(strategic_compromise),
                ideal_over_favorite=sorted(strategic_ideal),
                district_totals=totals)


def frame(seed: int = DESIGN_SEED) -> list[dict]:
    return [draw(game_id, stratum, seed)
            for stratum in STRATA for game_id in range(len(SUPPORT_TARGETS))]
