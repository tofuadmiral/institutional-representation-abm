"""Offline rival-package opportunity for constituent release after a mandate shock.

All outputs are scripted structural comparators, not model observations. In
particular, a possible coalition is not evidence that agents form it, and a
positive expected payoff is not evidence that an agent calculates it.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

Citizen = tuple[int, int, int]  # X, Y1, Y2
Table = tuple[tuple[Citizen, ...], ...]
Coalition = tuple[int, ...]

ACTORS = tuple(range(7))
SECOND_PROJECTS = ("Y1", "Y2")
INDEX = {"X": 0, "Y1": 1, "Y2": 2}
SHOCKED_ACTOR = 3


@dataclass(frozen=True)
class RivalWitness:
    before: Table
    after: Table
    shock_probability: Fraction


@dataclass(frozen=True)
class RivalScriptedOutcome:
    first_passed: bool
    second_passed: bool
    released_members: tuple[int, ...]
    district_utilities: tuple[int, ...]
    citizen_utilities: tuple[tuple[int, ...], ...]


def _district(x: tuple[int, ...], bundle_y1: tuple[int, ...],
              bundle_y2: tuple[int, ...]) -> tuple[Citizen, ...]:
    if not len(x) == len(bundle_y1) == len(bundle_y2) == 9:
        raise ValueError("nine citizens are required")
    return tuple((x_value, y1_total - x_value, y2_total - x_value)
                 for x_value, y1_total, y2_total
                 in zip(x, bundle_y1, bundle_y2, strict=True))


def witness(*, shock_probability: Fraction = Fraction(1, 4)) -> RivalWitness:
    """One deliberately constructed, non-dominating two-package example."""
    a = _district(
        (2, 2, 2, 2, 0, 0, 0, 0, 0),
        (1, 1, 1, 1, 1, 1, -1, -1, 0),
        (1, 1, 1, 1, 1, 1, -1, -1, -1),
    )
    b3 = _district(
        (-1, -1, -1, -1, -1, 0, 0, 0, 0),
        (1, 1, 1, 1, 1, 1, -1, -1, -1),
        (1, 1, 1, 1, -1, -1, -1, -1, -1),
    )
    b45 = _district(
        (-1, -1, -1, -1, -1, 0, 0, 0, 0),
        (-2, -1, -1, -1, -1, 0, 0, 0, 0),
        (1, 1, 1, 1, 1, 1, -1, -1, -1),
    )
    outsider = tuple((-1, -1, -1) for _ in range(6)) + tuple(
        (0, 0, 0) for _ in range(3))
    before = (a, a, a, b3, b45, b45, outsider)
    shocked_b3 = _district(
        (-1, -1, -1, -1, -1, 0, 0, 0, 0),
        (-2, -2, -2, -2, -2, -2, 0, 0, 0),
        (1, 1, 1, 1, -1, -1, -1, -1, -1),
    )
    after = (a, a, a, shocked_b3, b45, b45, outsider)
    game = RivalWitness(before=before, after=after,
                        shock_probability=shock_probability)
    validate(game)
    return game


def validate(game: RivalWitness) -> None:
    if not 0 <= game.shock_probability <= 1:
        raise ValueError("probability must be in [0, 1]")
    for table in (game.before, game.after):
        if len(table) != 7 or any(len(district) != 9 for district in table):
            raise ValueError("seven districts of nine citizens required")
        if any(len(row) != 3 or any(type(value) is not int or not -10 <= value <= 10
                                    for value in row)
               for district in table for row in district):
            raise ValueError("citizen utilities must be bounded integer triples")
    if any(game.before[actor] != game.after[actor] for actor in ACTORS
           if actor != SHOCKED_ACTOR):
        raise ValueError("only one district may change")
    if any(before[0] != after[0] or before[2] != after[2]
           for before, after in zip(game.before[SHOCKED_ACTOR],
                                    game.after[SHOCKED_ACTOR], strict=True)):
        raise ValueError("only the shocked district's Y1 utility may change")


def district_total(table: Table, actor: int, project: str) -> int:
    if actor not in ACTORS or project not in INDEX:
        raise ValueError("unknown actor or project")
    return sum(row[INDEX[project]] for row in table[actor])


def bundle_total(table: Table, actor: int, second_project: str) -> int:
    if second_project not in SECOND_PROJECTS:
        raise ValueError("unknown second project")
    return district_total(table, actor, "X") + district_total(table, actor, second_project)


def acceptable_coalitions(game: RivalWitness, second_project: str) -> tuple[Coalition, ...]:
    """Four districts each gain from the whole original bundle versus zero."""
    return tuple(coalition for coalition in combinations(ACTORS, 4)
                 if all(bundle_total(game.before, actor, second_project) > 0
                        for actor in coalition))


def scripted_outcome(game: RivalWitness, second_project: str, coalition: Coalition,
                     *, shocked: bool, release_right: bool) -> RivalScriptedOutcome:
    """Condition on signatures; outside votes follow district-sum sign only."""
    validate(game)
    if tuple(sorted(coalition)) != coalition or len(coalition) != 4:
        raise ValueError("coalition must have four distinct sorted members")
    if coalition not in acceptable_coalitions(game, second_project):
        raise ValueError("coalition is not initially acceptable")
    before = game.before
    after = game.after if shocked else before
    first_votes = tuple(actor in coalition or district_total(before, actor, "X") > 0
                        for actor in ACTORS)
    first_passed = sum(first_votes) >= 4
    release_votes = sum(row[INDEX[second_project]] < 0
                        for row in after[SHOCKED_ACTOR])
    released_members = ((SHOCKED_ACTOR,)
                        if (first_passed and shocked and release_right
                            and second_project == "Y1" and SHOCKED_ACTOR in coalition
                            and release_votes >= 5) else ())
    still_bound = set(coalition) - set(released_members)
    second_votes = tuple((first_passed and actor in still_bound)
                         or district_total(after, actor, second_project) > 0
                         for actor in ACTORS)
    second_passed = first_passed and sum(second_votes) >= 4
    project_index = INDEX[second_project]
    citizens = tuple(tuple((row[0] if first_passed else 0) +
                           (row[project_index] if second_passed else 0)
                           for row in district) for district in after)
    return RivalScriptedOutcome(
        first_passed=first_passed,
        second_passed=second_passed,
        released_members=released_members,
        district_utilities=tuple(map(sum, citizens)),
        citizen_utilities=citizens,
    )


def certificate(game: RivalWitness) -> dict[str, object]:
    """Finite opportunity facts; expected values condition on a signed offer."""
    validate(game)
    candidate_coalitions = {
        policy: acceptable_coalitions(game, policy) for policy in SECOND_PROJECTS
    }
    y1_coalition = (0, 1, 2, 3)
    y2_coalition = (0, 1, 2, 4)
    no_shock_y1 = scripted_outcome(game, "Y1", y1_coalition,
                                   shocked=False, release_right=False)
    locked_shock_y1 = scripted_outcome(game, "Y1", y1_coalition,
                                       shocked=True, release_right=False)
    released_shock_y1 = scripted_outcome(game, "Y1", y1_coalition,
                                         shocked=True, release_right=True)
    no_shock_y2 = scripted_outcome(game, "Y2", y2_coalition,
                                   shocked=False, release_right=False)
    shock_y2 = scripted_outcome(game, "Y2", y2_coalition,
                                shocked=True, release_right=True)
    p = game.shock_probability
    return {
        "individual_positive_district_counts": {
            project: sum(district_total(game.before, actor, project) > 0
                         for actor in ACTORS) for project in INDEX
        },
        "initial_bundle_totals": {
            policy: tuple(bundle_total(game.before, actor, policy) for actor in ACTORS)
            for policy in SECOND_PROJECTS
        },
        "coalitions": candidate_coalitions,
        "shock_release_votes": sum(row[1] < 0 for row in game.after[SHOCKED_ACTOR]),
        "y1_shock_second_passed_locked": locked_shock_y1.second_passed,
        "y1_shock_second_passed_release": released_shock_y1.second_passed,
        "y2_shock_second_passed": shock_y2.second_passed,
        "y1_expected_pivot_locked": (
            (1 - p) * no_shock_y1.district_utilities[SHOCKED_ACTOR]
            + p * locked_shock_y1.district_utilities[SHOCKED_ACTOR]),
        "y1_expected_pivot_release": (
            (1 - p) * no_shock_y1.district_utilities[SHOCKED_ACTOR]
            + p * released_shock_y1.district_utilities[SHOCKED_ACTOR]),
        "y1_expected_a0_locked": (
            (1 - p) * no_shock_y1.district_utilities[0]
            + p * locked_shock_y1.district_utilities[0]),
        "y1_expected_a0_release": (
            (1 - p) * no_shock_y1.district_utilities[0]
            + p * released_shock_y1.district_utilities[0]),
        "y2_expected_a0": (
            (1 - p) * no_shock_y2.district_utilities[0]
            + p * shock_y2.district_utilities[0]),
        "y1_expected_total_welfare_locked": (
            (1 - p) * sum(no_shock_y1.district_utilities)
            + p * sum(locked_shock_y1.district_utilities)),
        "y1_expected_total_welfare_release": (
            (1 - p) * sum(no_shock_y1.district_utilities)
            + p * sum(released_shock_y1.district_utilities)),
        "y2_expected_total_welfare": (
            (1 - p) * sum(no_shock_y2.district_utilities)
            + p * sum(shock_y2.district_utilities)),
    }
