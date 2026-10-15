"""Prospective release-right feasibility screen on independently drawn games.

Six opportunity-conditioned games, not a representative population sample.
Unlike the preceding witness perturbations, utility totals and citizen rows
are generated afresh for three distinct coalition-overlap topologies. No
model output is used to accept a profile. Citizens are synthetic principals.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import random

from paper3 import mandate_release_rival_opportunity as opportunity

FAMILIES = ("overlap1", "overlap2", "overlap3")
Y1_SUPPORT = (0, 1, 2, 3)
Y2_SUPPORT = {"overlap1": (0, 4, 5, 6),
              "overlap2": (0, 1, 4, 5),
              "overlap3": (0, 1, 2, 4)}
SPECS = tuple((family, stratum, 930000 + 101 * index)
              for index, (family, stratum) in enumerate(
                  (family, stratum) for family in FAMILIES
                  for stratum in ("pivotal", "nonpivotal")))


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


def _column(total: int, rng: random.Random) -> tuple[int, ...]:
    """Random citizen allocation conditional on a fixed district total."""
    values = [rng.randint(-5, 5) for _ in range(9)]
    while sum(values) != total:
        step = 1 if sum(values) < total else -1
        candidates = [index for index, value in enumerate(values)
                      if -10 <= value + step <= 10]
        if not candidates:
            raise ValueError("impossible bounded district total")
        values[rng.choice(candidates)] += step
    return tuple(values)


def _draw(family: str, stratum: str, rng: random.Random
          ) -> opportunity.RivalWitness:
    rows = []
    for actor in opportunity.ACTORS:
        x = (rng.randint(25, 35) if actor in (0, 1, 2)
             else -rng.randint(5, 9) if actor == 3
             else -rng.randint(18, 27))
        y1_bundle = (rng.randint(10, 16) if actor == 0
                     else rng.randint(8, 14) if actor in Y1_SUPPORT
                     else -rng.randint(30, 38))
        y2_bundle = (rng.randint(3, 9) if actor == 0
                     else rng.randint(8, 14) if actor in Y2_SUPPORT[family]
                     else -rng.randint(30, 38))
        y1 = (rng.randint(2, 8) if stratum == "nonpivotal" and actor == 6
              else y1_bundle - x)
        columns = tuple(_column(total, rng)
                        for total in (x, y1, y2_bundle - x))
        rows.append(tuple(zip(*columns, strict=True)))
    before = tuple(rows)
    shock = _column(-rng.randint(25, 40), rng)
    after = tuple(tuple((row[0], shock[index], row[2])
                        for index, row in enumerate(district))
                  if actor == 3 else district
                  for actor, district in enumerate(before))
    return opportunity.RivalWitness(
        before, after, rng.choice((Fraction(1, 5), Fraction(1, 4),
                                  Fraction(3, 10), Fraction(7, 20))))


def certificate(game: opportunity.RivalWitness, family: str, stratum: str
                ) -> dict[str, object]:
    """Structural facts under sincere outsider votes, never model evidence."""
    opportunity.validate(game)
    if family not in FAMILIES or stratum not in ("pivotal", "nonpivotal"):
        raise ValueError("unknown cell")
    coalitions = {project: opportunity.acceptable_coalitions(game, project)
                 for project in opportunity.SECOND_PROJECTS}
    if coalitions != {"Y1": (Y1_SUPPORT,), "Y2": (Y2_SUPPORT[family],)}:
        raise ValueError("positive-bundle coalition topology changed")
    if any(sum(opportunity.district_total(game.before, actor, project) > 0
               for actor in opportunity.ACTORS) >= 4
           for project in opportunity.INDEX):
        raise ValueError("one project already has an independent majority")
    if sum(row[1] < 0 for row in game.after[3]) < 5:
        raise ValueError("shock does not qualify for constituent release")
    states = {(arm, shocked): opportunity.scripted_outcome(
        game, "Y1", Y1_SUPPORT, shocked=shocked,
        release_right=arm == "constituent_release")
              for arm in ("irrevocable", "constituent_release")
              for shocked in (False, True)}
    if states[("irrevocable", False)] != states[("constituent_release", False)]:
        raise ValueError("release changed unshocked enforcement")
    if not states[("irrevocable", True)].second_passed:
        raise ValueError("locked pledge does not deliver second project")
    if states[("constituent_release", True)].second_passed != (stratum == "nonpivotal"):
        raise ValueError("pivotality changed")
    p = game.shock_probability
    expected = {arm: (1 - p) * states[(arm, False)].district_utilities[3]
                + p * states[(arm, True)].district_utilities[3]
                for arm in ("irrevocable", "constituent_release")}
    if not expected["irrevocable"] < 0:
        raise ValueError("no ex ante downside for exposed signer")
    if stratum == "pivotal" and not expected["constituent_release"] > 0:
        raise ValueError("release does not create a potentially acceptable pledge")
    if stratum == "nonpivotal" and expected["irrevocable"] != expected["constituent_release"]:
        raise ValueError("nonpivotal comparator changed scripted payoff")
    return dict(
        y1_coalition=Y1_SUPPORT, y2_coalition=Y2_SUPPORT[family],
        overlap=len(set(Y1_SUPPORT) & set(Y2_SUPPORT[family])),
        probability=str(p), pivot_expected_y1={key: str(value)
                                             for key, value in expected.items()},
        district_bundle_sums={project: tuple(opportunity.bundle_total(
            game.before, actor, project) for actor in opportunity.ACTORS)
                              for project in opportunity.SECOND_PROJECTS},
        release_votes=sum(row[1] < 0 for row in game.after[3]),
        comparison_assumption="Signed four-person pledge; unbound outsiders vote by district-sum sign.")


def cases() -> tuple[Case, ...]:
    result = []
    for index, (family, stratum, seed) in enumerate(SPECS):
        rng = random.Random(seed)
        for draw in range(1, 20001):
            game = _draw(family, stratum, rng)
            try:
                certificate(game, family, stratum)
            except ValueError:
                continue
            roles = list(opportunity.ACTORS)
            rng.shuffle(roles)
            result.append(Case(f"release-gonogo-{index:02d}", family, stratum,
                               seed, draw, tuple(roles),
                               ("Cedar", "River") if index % 2 == 0
                               else ("River", "Cedar"), game))
            break
        else:
            raise ValueError("generator exhausted without a valid opportunity")
    return tuple(result)


def diversity_audit(per_cell: int = 32) -> dict[str, object]:
    """Prospective generator stress test, using seeds outside the pilot."""
    counts = {}
    profiles = set()
    for family, stratum, _ in SPECS:
        accepted = draws = 0
        for index in range(per_cell):
            rng = random.Random(940000 + 1000 * FAMILIES.index(family)
                                + 100 * (stratum == "nonpivotal") + index)
            for _ in range(20000):
                draws += 1
                game = _draw(family, stratum, rng)
                try:
                    certificate(game, family, stratum)
                except ValueError:
                    continue
                profiles.add((game.before, game.after, game.shock_probability))
                accepted += 1
                break
            else:
                raise ValueError("stress-test opportunity not found")
        counts[family + "/" + stratum] = dict(accepted=accepted, draws=draws)
    return dict(cells=counts, unique_profiles=len(profiles),
                independent_topologies=3, exhaustive_coalition_inventory=35,
                caveat="Conditional profile generation; common two-project institution and sign templates remain.")
