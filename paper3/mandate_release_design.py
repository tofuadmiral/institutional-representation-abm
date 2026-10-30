"""Prospective, opportunity-conditioned release-right profile inventory.

No model outputs are consulted. The accepted cases are selected synthetic
opportunities, not a representative electorate or independent population.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import random

from paper3 import mandate_release_rival_opportunity as opportunity
from paper3 import mandate_release_institution as institution


@dataclass(frozen=True)
class Case:
    case_id: str
    stratum: str
    seed: int
    draw_index: int
    shocked: bool
    display_roles: tuple[int, ...]
    display_projects: tuple[str, str]
    game: opportunity.RivalWitness


SPECS = (
    ("pivotal", Fraction(1, 4), True, 991001),
    ("pivotal", Fraction(1, 4), False, 991003),
    ("pivotal", Fraction(1, 4), True, 991007),
    ("pivotal", Fraction(1, 4), False, 991009),
    ("low_risk", Fraction(1, 10), True, 991013),
    ("low_risk", Fraction(1, 10), False, 991021),
    ("high_risk", Fraction(1, 2), True, 991027),
    ("high_risk", Fraction(1, 2), False, 991031),
    ("nonpivotal", Fraction(1, 4), True, 991033),
    ("nonpivotal", Fraction(1, 4), False, 991039),
)


def _perturb(base: opportunity.RivalWitness, rng: random.Random,
             nonpivotal: bool) -> opportunity.RivalWitness:
    before = [[list(row) for row in district] for district in base.before]
    after = [[list(row) for row in district] for district in base.after]
    for actor in opportunity.ACTORS:
        if actor == 6:
            continue
        for project_index in range(3):
            # One or two independent bounded citizen-level payoff changes per
            # actor and project. The two potential states share the same
            # background perturbations; only actor 3's Y1 shock is additional.
            for _ in range(rng.choice((1, 2))):
                citizen = rng.randrange(9)
                delta = rng.choice((-1, 1))
                before[actor][citizen][project_index] += delta
                after[actor][citizen][project_index] += delta
    if nonpivotal:
        # Make an otherwise non-signing district a possible substitute Y1
        # ballot after the release, without making X+Y1 attractive to it.
        for citizen in rng.sample(range(9), 3):
            before[4][citizen][1] += 1
            after[4][citizen][1] += 1
    for actor in (0, 1):
        # Preserve both district totals but make five of nine citizens prefer
        # the lower-district-sum Y2 option. This prevents a district-sum
        # mandate from masquerading as unanimous constituent consent.
        difference = sum(row[1] - row[2] for row in before[actor])
        if difference <= 0:
            continue
        y2_majority = set(rng.sample(range(9), 5))
        y1_minority = [citizen for citizen in range(9)
                       if citizen not in y2_majority]
        positive_total = difference + 5
        quotient, remainder = divmod(positive_total, 4)
        for citizen in y2_majority:
            before[actor][citizen][1] = before[actor][citizen][2] - 1
            after[actor][citizen][1] = after[actor][citizen][2] - 1
        for offset, citizen in enumerate(y1_minority):
            gain = quotient + (offset < remainder)
            before[actor][citizen][1] = before[actor][citizen][2] + gain
            after[actor][citizen][1] = after[actor][citizen][2] + gain
    game = opportunity.RivalWitness(
        before=tuple(tuple(tuple(row) for row in district) for district in before),
        after=tuple(tuple(tuple(row) for row in district) for district in after),
        shock_probability=base.shock_probability,
    )
    opportunity.validate(game)
    return game


def _certificate(game: opportunity.RivalWitness, stratum: str) -> bool:
    if (0, 1, 2, 3) not in opportunity.acceptable_coalitions(game, "Y1"):
        return False
    if not {(0, 1, 2, 4), (0, 1, 2, 5)}.issubset(
        set(opportunity.acceptable_coalitions(game, "Y2"))
    ):
        return False
    if any(sum(opportunity.district_total(game.before, actor, project) > 0
               for actor in opportunity.ACTORS) >= 4
           for project in opportunity.INDEX):
        return False
    release_yes = sum(row[1] < 0 for row in game.after[3])
    if release_yes < 5:
        return False
    y1 = (0, 1, 2, 3)
    locked = opportunity.scripted_outcome(game, "Y1", y1,
                                          shocked=True, release_right=False)
    released = opportunity.scripted_outcome(game, "Y1", y1,
                                            shocked=True, release_right=True)
    unshocked = opportunity.scripted_outcome(game, "Y1", y1,
                                             shocked=False, release_right=False)
    if not locked.first_passed or not locked.second_passed:
        return False
    if opportunity.scripted_outcome(game, "Y1", y1, shocked=False,
                                     release_right=True) != unshocked:
        return False
    if stratum == "nonpivotal":
        if not released.second_passed:
            return False
    elif released.second_passed:
        return False
    p = game.shock_probability
    expected_locked = ((1 - p) * unshocked.district_utilities[3]
                       + p * locked.district_utilities[3])
    expected_release = ((1 - p) * unshocked.district_utilities[3]
                        + p * released.district_utilities[3])
    if stratum == "pivotal" and not expected_locked < 0 < expected_release:
        return False
    if stratum == "low_risk" and not 0 < expected_locked < expected_release:
        return False
    if stratum == "high_risk" and not expected_locked < expected_release < 0:
        return False
    if stratum == "nonpivotal" and expected_locked != expected_release:
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
    for index, (stratum, probability, shocked, seed) in enumerate(SPECS):
        base = opportunity.witness(shock_probability=probability)
        rng = random.Random(seed)
        for draw_index in range(1, 20_001):
            candidate = _perturb(base, rng, stratum == "nonpivotal")
            if _certificate(candidate, stratum):
                result.append(Case(
                    case_id=f"release-{index:02d}", stratum=stratum,
                    seed=seed, draw_index=draw_index, shocked=shocked,
                    display_roles=tuple((actor + index) % 7 for actor in opportunity.ACTORS),
                    display_projects=(("Amber", "Blue") if index % 2 == 0
                                      else ("Blue", "Amber")),
                    game=candidate,
                ))
                break
        else:
            raise ValueError(f"no structurally accepted draw for {stratum} seed {seed}")
    return tuple(result)


def screen(outcomes: dict[tuple[str, str], institution.Episode | None]) -> dict[str, object]:
    """Prewritten two-sided, selected-case *discovery* screen.

    Incomplete episodes remain missing; no imputation or selection of only
    active contracts. The treatment sign uses agent-authored pre-shock
    agreement, never mechanically enforced second-stage ballots.
    """
    inventory = cases()
    expected = {(case.case_id, arm) for case in inventory for arm in institution.ARMS}
    if type(outcomes) is not dict or not set(outcomes) <= expected:
        raise ValueError("outcome inventory")
    rows = []
    for case in inventory:
        locked = outcomes.get((case.case_id, "irrevocable"))
        release = outcomes.get((case.case_id, "constituent_release"))
        for arm, outcome in (("irrevocable", locked), ("constituent_release", release)):
            if outcome is not None and (not isinstance(outcome, institution.Episode)
                                        or outcome.arm != arm
                                        or outcome.shocked != case.shocked):
                raise ValueError("episode arm or realization mismatch")
        complete = locked is not None and release is not None
        locked_y1 = (locked.active and locked.final.second_project == "Y1"
                     and 3 in locked.final.coalition) if locked else None
        release_y1 = (release.active and release.final.second_project == "Y1"
                      and 3 in release.final.coalition) if release else None
        rows.append(dict(case_id=case.case_id, stratum=case.stratum,
                         shocked=case.shocked, complete=complete,
                         irrevocable_y1_activated=locked_y1,
                         release_y1_activated=release_y1,
                         release_only=(release_y1 and not locked_y1) if complete else None,
                         irrevocable_only=(locked_y1 and not release_y1) if complete else None,
                         x_changed=(locked.x_passed != release.x_passed) if complete else None,
                         y_changed=(locked.y_passed != release.y_passed) if complete else None,
                         district_delta=(tuple(b - a for a, b in zip(
                             locked.district_utilities, release.district_utilities, strict=True))
                             if complete else None),
                         citizen_delta=(tuple(tuple(b - a for a, b in zip(
                             locked.citizen_utilities[actor],
                             release.citizen_utilities[actor], strict=True))
                             for actor in opportunity.ACTORS) if complete else None)))
    pivotal = [row for row in rows if row["stratum"] == "pivotal"]
    nonpivotal = [row for row in rows if row["stratum"] == "nonpivotal"]
    missing = sum(not row["complete"] for row in rows)
    release_only = sum(row["release_only"] is True for row in pivotal)
    locked_only = sum(row["irrevocable_only"] is True for row in pivotal)
    nonpivotal_changed = sum(
        row["release_only"] is True or row["irrevocable_only"] is True
        for row in nonpivotal)
    complete_enough = (all(row["complete"] for row in (*pivotal, *nonpivotal))
                       and missing <= 1)
    if not complete_enough:
        classification = "incomplete_or_control_missing"
    elif nonpivotal_changed:
        classification = "nonpivotal_control_changed"
    elif release_only >= 3 and locked_only == 0:
        classification = "selected_case_release_behavioral_lead"
    elif locked_only >= 3 and release_only == 0:
        classification = "selected_case_irrevocable_behavioral_lead"
    else:
        classification = "no_prespecified_behavioral_lead"
    return dict(rows=rows, missing_pairs=missing,
                pivotal_release_only=release_only,
                pivotal_irrevocable_only=locked_only,
                nonpivotal_changed=nonpivotal_changed,
                classification=classification,
                caveat="One template family, one model, selected opportunities: a lead is not population evidence or a paper result. Executed-ballot changes alone never qualify.")
