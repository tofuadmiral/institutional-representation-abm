"""Offline structural witness for a constituent release right.

This module makes no model calls and supplies no experimental result. It checks
whether a release rule can be consequential without fixing the coalition that
agents will choose. The scripted positive-sum ballots are a comparator, not a
prediction of agent behavior or a claim about strategic equilibrium.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

Citizen = tuple[int, int]  # (project X utility, project Y utility)
District = tuple[Citizen, ...]
Table = tuple[District, ...]
Coalition = tuple[int, ...]

REPRESENTATIVES = tuple(range(7))
SHOCKED_REPRESENTATIVE = 3
PROJECTS = ("X", "Y")


@dataclass(frozen=True)
class Witness:
    before: Table
    after: Table
    shock_probability: Fraction
    shocked_representatives: tuple[int, ...] = (SHOCKED_REPRESENTATIVE,)


@dataclass(frozen=True)
class ScriptedOutcome:
    first_votes: tuple[bool, ...]
    second_votes: tuple[bool, ...]
    first_passed: bool
    second_passed: bool
    released_members: tuple[int, ...]
    district_utilities: tuple[int, ...]
    citizen_utilities: tuple[tuple[int, ...], ...]


def _district(x: tuple[int, ...], package: tuple[int, ...]) -> District:
    assert len(x) == len(package) == 9
    return tuple((x_utility, total - x_utility)
                 for x_utility, total in zip(x, package, strict=True))


def witness(*, sector_shock: bool = False,
            shock_probability: Fraction = Fraction(1, 4)) -> Witness:
    """One transparent exchange with an individual or shared sector shock.

    These are selected structural examples, not independently sampled games.
    """
    package = (1, 1, 1, 1, 1, 1, -1, -1, -1)
    a = _district((2, 2, 2, 2, 0, 0, 0, 0, 0), package)
    b = _district((-1, -1, -1, -1, -1, 0, 0, 0, 0), package)
    outsider = tuple((-1, -1) for _ in range(6)) + tuple((0, 0) for _ in range(3))
    before = (a, a, a, b, b, b, outsider)

    shocked_package = (-2, -2, -2, -2, -2, -2, 0, 0, 0)
    shocked_b = _district((-1, -1, -1, -1, -1, 0, 0, 0, 0), shocked_package)
    shocked_representatives = (3, 4, 5) if sector_shock else (3,)
    after = (a, a, a,
             shocked_b,
             shocked_b if sector_shock else b,
             shocked_b if sector_shock else b,
             outsider)
    result = Witness(before=before, after=after,
                     shock_probability=shock_probability,
                     shocked_representatives=shocked_representatives)
    validate_witness(result)
    return result


def validate_witness(game: Witness) -> None:
    if (not game.shocked_representatives
            or len(set(game.shocked_representatives)) != len(game.shocked_representatives)
            or any(actor not in REPRESENTATIVES for actor in game.shocked_representatives)):
        raise ValueError("shocked representatives must be unique chamber members")
    if not 0 <= game.shock_probability <= 1:
        raise ValueError("shock probability must be between zero and one")
    for table in (game.before, game.after):
        if len(table) != 7 or any(len(district) != 9 for district in table):
            raise ValueError("expected seven districts of nine citizens")
        if any(type(value) is not int or not -10 <= value <= 10
               for district in table for row in district for value in row):
            raise ValueError("citizen project utilities must be bounded integers")
    for actor in REPRESENTATIVES:
        if actor not in game.shocked_representatives and game.before[actor] != game.after[actor]:
            raise ValueError("only the shocked district may change")
    for actor in game.shocked_representatives:
        if any(before[0] != after[0] for before, after in zip(
                game.before[actor], game.after[actor], strict=True)):
            raise ValueError("the already-voted first project may not change")


def district_total(table: Table, actor: int, project: str) -> int:
    if actor not in REPRESENTATIVES or project not in PROJECTS:
        raise ValueError("unknown representative or project")
    project_index = PROJECTS.index(project)
    return sum(row[project_index] for row in table[actor])


def package_total(table: Table, actor: int) -> int:
    return district_total(table, actor, "X") + district_total(table, actor, "Y")


def release_approved(game: Witness, actor: int, shocked: bool) -> bool:
    """Constituents vote on release from the *remaining* Y pledge."""
    if not shocked or actor not in game.shocked_representatives:
        return False
    district = game.after[actor]
    return sum(y_utility < 0 for _, y_utility in district) >= 5


def initially_acceptable_coalitions(game: Witness) -> tuple[Coalition, ...]:
    """Four signers each gain from the complete initial package versus zero."""
    return tuple(coalition for coalition in combinations(REPRESENTATIVES, 4)
                 if all(package_total(game.before, actor) > 0 for actor in coalition))


def scripted_outcome(game: Witness, coalition: Coalition, *, shocked: bool,
                     release_right: bool) -> ScriptedOutcome:
    """Apply the fixed vote rule to one hypothesized *signed* coalition.

    This conditions on agreement and uses positive-own-project ballots for
    non-bound representatives. It is not an estimate of signing or voting.
    """
    validate_witness(game)
    if tuple(sorted(coalition)) != coalition or len(coalition) != 4:
        raise ValueError("coalition must contain four distinct sorted representatives")
    if coalition not in initially_acceptable_coalitions(game):
        raise ValueError("coalition is not initially acceptable to every signer")

    table = game.after if shocked else game.before
    first_votes = tuple(actor in coalition or district_total(game.before, actor, "X") > 0
                        for actor in REPRESENTATIVES)
    first_passed = sum(first_votes) >= 4
    released_members = tuple(actor for actor in coalition
                             if first_passed and release_right
                             and release_approved(game, actor, shocked))
    still_bound = set(coalition)
    still_bound.difference_update(released_members)
    second_votes = tuple((actor in still_bound and first_passed)
                         or district_total(table, actor, "Y") > 0
                         for actor in REPRESENTATIVES)
    second_passed = first_passed and sum(second_votes) >= 4

    citizen_utilities = tuple(tuple((x if first_passed else 0) +
                                    (y if second_passed else 0)
                                    for x, y in district) for district in table)
    district_utilities = tuple(sum(district) for district in citizen_utilities)
    return ScriptedOutcome(
        first_votes=first_votes,
        second_votes=second_votes,
        first_passed=first_passed,
        second_passed=second_passed,
        released_members=released_members,
        district_utilities=district_utilities,
        citizen_utilities=citizen_utilities,
    )


def opportunity_certificate(game: Witness) -> dict[str, object]:
    """Return structural counts without treating scripted outcomes as data."""
    validate_witness(game)
    coalitions = initially_acceptable_coalitions(game)
    pivotal: list[Coalition] = []
    no_shock_disagreement: list[Coalition] = []
    for coalition in coalitions:
        locked = scripted_outcome(game, coalition, shocked=True, release_right=False)
        released = scripted_outcome(game, coalition, shocked=True, release_right=True)
        if locked.second_passed != released.second_passed:
            pivotal.append(coalition)
        locked_control = scripted_outcome(game, coalition, shocked=False, release_right=False)
        release_control = scripted_outcome(game, coalition, shocked=False, release_right=True)
        if locked_control != release_control:
            no_shock_disagreement.append(coalition)

    pivot_coalition = (0, 3, 4, 5)
    locked_shock = scripted_outcome(game, pivot_coalition, shocked=True, release_right=False)
    release_shock = scripted_outcome(game, pivot_coalition, shocked=True, release_right=True)
    no_shock = scripted_outcome(game, pivot_coalition, shocked=False, release_right=False)
    probability = game.shock_probability
    return {
        "citizens": sum(len(district) for district in game.before),
        "initial_positive_districts_by_project": {
            project: sum(district_total(game.before, actor, project) > 0
                         for actor in REPRESENTATIVES)
            for project in PROJECTS
        },
        "initial_package_district_sums": tuple(package_total(game.before, actor)
                                               for actor in REPRESENTATIVES),
        "shocked_package_district_sums": tuple(package_total(game.after, actor)
                                               for actor in REPRESENTATIVES),
        "release_votes_after_shock": {
            actor: sum(y < 0 for _, y in game.after[actor])
            for actor in game.shocked_representatives
        },
        "acceptable_coalitions": coalitions,
        "pivotal_release_coalitions": tuple(pivotal),
        "no_shock_disagreement_coalitions": tuple(no_shock_disagreement),
        "example_pivot_coalition": pivot_coalition,
        "example_pivot_expected_utility_locked": (
            (1 - probability) * no_shock.district_utilities[3]
            + probability * locked_shock.district_utilities[3]),
        "example_pivot_expected_utility_release": (
            (1 - probability) * no_shock.district_utilities[3]
            + probability * release_shock.district_utilities[3]),
        "example_shock_welfare_locked": sum(locked_shock.district_utilities),
        "example_shock_welfare_release": sum(release_shock.district_utilities),
    }
