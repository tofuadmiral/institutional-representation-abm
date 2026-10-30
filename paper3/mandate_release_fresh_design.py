"""Untouched, two-topology candidates for a *future* branching pilot.

This is an offline inventory, not a frozen experiment or population sample.
It is deliberately separate from the archived v1 cases and current v2
engineering gate. No model output is used in accepting a numeric profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import random

from paper3 import mandate_release_design as earlier
from paper3 import mandate_release_rival_opportunity as opportunity


@dataclass(frozen=True)
class Case:
    case_id: str
    family: str
    stratum: str
    seed: int
    draw_index: int
    display_roles: tuple[int, ...]
    display_projects: tuple[str, str]
    game: opportunity.RivalWitness


# Chosen before any scientific call on these games. The macro-parameters vary
# shock prior, opt-out payoff, and shock loss without selecting on model output.
# Each case branches into both realizations within each announced rule.
SPECS = (
    ("overlap3", "pivotal", 992101, Fraction(11, 50), -2, 4),
    ("overlap2", "pivotal", 992103, Fraction(1, 4), 2, 0),
    ("overlap3", "pivotal", 992107, Fraction(3, 10), 1, 6),
    ("overlap2", "pivotal", 992111, Fraction(11, 50), 0, 2),
    ("overlap3", "pivotal", 992113, Fraction(1, 4), -1, 6),
    ("overlap2", "pivotal", 992119, Fraction(3, 10), 2, 4),
    ("overlap3", "pivotal", 992123, Fraction(11, 50), 2, 2),
    ("overlap2", "pivotal", 992129, Fraction(1, 4), -2, 6),
    ("overlap3", "nonpivotal", 992137, Fraction(1, 4), 0, 2),
    ("overlap2", "nonpivotal", 992141, Fraction(1, 4), 0, 2),
)


def _base(family: str, probability: Fraction, opt_out_shift: int,
          shock_extra: int) -> opportunity.RivalWitness:
    game = opportunity.witness(shock_probability=probability)
    if family not in ("overlap2", "overlap3"):
        raise ValueError("unknown overlap family")
    if opt_out_shift not in range(-2, 3) or shock_extra not in (0, 2, 4, 6):
        raise ValueError("unknown payoff variation")

    def adjust(table: opportunity.Table, shocked: bool) -> opportunity.Table:
        districts = [[list(row) for row in district] for district in table]
        if family == "overlap2":
            for row in districts[2]:
                row[2] -= 1
        # Hold the initial Y1 bundle constant while varying the value of
        # retaining X alone after constituent release.
        citizens = (range(opt_out_shift) if opt_out_shift > 0
                    else range(9 + opt_out_shift, 9))
        step = 1 if opt_out_shift > 0 else -1
        for citizen in citizens:
            districts[3][citizen][0] += step
            districts[3][citizen][1] -= step
        if shocked:
            for citizen in range(shock_extra):
                districts[3][citizen][1] -= 1
        return tuple(tuple(tuple(row) for row in district)
                     for district in districts)

    changed = opportunity.RivalWitness(
        before=adjust(game.before, False), after=adjust(game.after, True),
        shock_probability=probability,
    )
    opportunity.validate(changed)
    return changed


def _certificate(game: opportunity.RivalWitness, family: str,
                 stratum: str) -> bool:
    y1 = set(opportunity.acceptable_coalitions(game, "Y1"))
    y2 = set(opportunity.acceptable_coalitions(game, "Y2"))
    if (0, 1, 2, 3) not in y1:
        return False
    # In both families actor 3 remains the exposed Y1 signer, not a hidden
    # substitute for the competing Y2 agreement.
    if opportunity.bundle_total(game.before, 3, "Y2") > 0:
        return False
    if family == "overlap3":
        if not {(0, 1, 2, 4), (0, 1, 2, 5)}.issubset(y2):
            return False
    elif family == "overlap2":
        if (0, 1, 4, 5) not in y2 or (0, 1, 2, 4) in y2:
            return False
    else:
        raise ValueError("unknown family")
    if any(sum(opportunity.district_total(game.before, actor, project) > 0
               for actor in opportunity.ACTORS) >= 4
           for project in opportunity.INDEX):
        return False
    if sum(row[1] < 0 for row in game.after[3]) < 5:
        return False
    coalition = (0, 1, 2, 3)
    locked = opportunity.scripted_outcome(game, "Y1", coalition,
                                          shocked=True, release_right=False)
    released = opportunity.scripted_outcome(game, "Y1", coalition,
                                            shocked=True, release_right=True)
    unshocked = opportunity.scripted_outcome(game, "Y1", coalition,
                                             shocked=False, release_right=False)
    if not locked.first_passed or not locked.second_passed:
        return False
    if opportunity.scripted_outcome(game, "Y1", coalition, shocked=False,
                                    release_right=True) != unshocked:
        return False
    if stratum == "pivotal" and released.second_passed:
        return False
    if stratum == "nonpivotal" and not released.second_passed:
        return False
    if stratum not in ("pivotal", "nonpivotal"):
        raise ValueError("unknown stratum")
    p = game.shock_probability
    locked_expected = ((1 - p) * unshocked.district_utilities[3]
                       + p * locked.district_utilities[3])
    release_expected = ((1 - p) * unshocked.district_utilities[3]
                        + p * released.district_utilities[3])
    if stratum == "pivotal" and not locked_expected < 0 < release_expected:
        return False
    if stratum == "nonpivotal" and locked_expected != release_expected:
        return False
    if (opportunity.bundle_total(game.before, 0, "Y1")
            <= opportunity.bundle_total(game.before, 0, "Y2")):
        return False
    if any(opportunity.bundle_total(game.before, actor, "Y1")
           <= opportunity.bundle_total(game.before, actor, "Y2")
           or sum(row[2] > row[1] for row in game.before[actor]) != 5
           for actor in (0, 1)):
        return False
    return True


def cases() -> tuple[Case, ...]:
    result = []
    for index, (family, stratum, seed, probability, opt_out_shift,
                shock_extra) in enumerate(SPECS):
        rng = random.Random(seed)
        base = _base(family, probability, opt_out_shift, shock_extra)
        for draw_index in range(1, 20_001):
            game = earlier._perturb(base, rng, stratum == "nonpivotal")
            if _certificate(game, family, stratum):
                result.append(Case(
                    case_id=f"release-fresh-{index:02d}", family=family,
                    stratum=stratum, seed=seed, draw_index=draw_index,
                    display_roles=tuple((actor + index + 1) % 7
                                        for actor in opportunity.ACTORS),
                    display_projects=(("Cedar", "River") if index % 2 == 0
                                      else ("River", "Cedar")),
                    game=game,
                ))
                break
        else:
            raise ValueError(f"no opportunity for {family}/{stratum}/{seed}")
    return tuple(result)
