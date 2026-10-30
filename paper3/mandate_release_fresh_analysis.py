"""Prewritten selected-case screen for a possible branching discovery pilot.

This module does not authorize or run model calls. The unit is the numeric
game; 63 citizen rows are outcomes, not independent experimental units. The
screen recognizes agent-authored pre-shock contract changes, never a
controller-enforced second ballot by itself.
"""

from __future__ import annotations

from paper3 import mandate_release_fresh_design as design
from paper3 import mandate_release_institution as institution
from paper3 import mandate_release_rival_opportunity as opportunity


def _pre_shock(episode: institution.Episode) -> tuple[object, ...]:
    return (episode.draft, episode.responses, episode.final, episode.consent,
            episode.requested_x, episode.executed_x, episode.x_passed)


def _agreement(episode: institution.Episode) -> tuple[object, ...]:
    """Agent-authored final agreement, excluding mechanically enforced ballots."""
    if not episode.active:
        return (False, None, ())
    return (episode.active, episode.final.second_project,
            episode.final.coalition)


def _citizen_delta(locked: institution.Episode,
                   released: institution.Episode) -> tuple[tuple[int, ...], ...]:
    return tuple(tuple(b - a for a, b in zip(
        locked.citizen_utilities[actor], released.citizen_utilities[actor],
        strict=True)) for actor in institution.ACTORS)


def _summary(episode: institution.Episode | None,
             game: opportunity.RivalWitness) -> dict[str, object] | None:
    if episode is None:
        return None
    table = game.after if episode.shocked else game.before
    citizen_menu_regret = tuple(tuple(
        max(0, row[0]) + max(0, row[1], row[2]) - realized
        for row, realized in zip(district, episode.citizen_utilities[actor],
                                 strict=True))
        for actor, district in enumerate(table))
    district_menu_regret = tuple(
        max(0, opportunity.district_total(table, actor, "X"))
        + max(0, opportunity.district_total(table, actor, "Y1"),
              opportunity.district_total(table, actor, "Y2"))
        - episode.district_utilities[actor]
        for actor in institution.ACTORS)
    majority_positive = tuple(sum(value > 0 for value in district) >= 5
                              for district in episode.citizen_utilities)
    district_positive = tuple(value > 0 for value in episode.district_utilities)
    return dict(
        active=episode.active, final_project=episode.final.second_project,
        final_coalition=episode.final.coalition,
        requested_x=episode.requested_x, executed_x=episode.executed_x,
        requested_y=episode.requested_y, executed_y=episode.executed_y,
        released=episode.released, x_passed=episode.x_passed,
        y_passed=episode.y_passed,
        district_utilities=episode.district_utilities,
        citizen_utilities=episode.citizen_utilities,
        district_menu_regret=district_menu_regret,
        citizen_menu_regret=citizen_menu_regret,
        total_district_menu_regret=sum(district_menu_regret),
        total_citizen_menu_regret=sum(value for district in
                                      citizen_menu_regret for value in district),
        total_welfare=sum(episode.district_utilities),
        harmed_citizens=sum(value < 0 for district in
                            episode.citizen_utilities for value in district),
        citizen_majority_positive=majority_positive,
        district_sum_positive=district_positive,
        majority_sum_disagreement=sum(a != b for a, b in zip(
            majority_positive, district_positive, strict=True)),
    )


def _state(locked: institution.Episode,
           released: institution.Episode) -> dict[str, object]:
    citizen_delta = _citizen_delta(locked, released)
    return dict(
        locked_x_passed=locked.x_passed,
        release_x_passed=released.x_passed,
        locked_y_passed=locked.y_passed,
        release_y_passed=released.y_passed,
        locked_total_welfare=sum(locked.district_utilities),
        release_total_welfare=sum(released.district_utilities),
        locked_harmed_citizens=sum(value < 0 for district in
                                   locked.citizen_utilities for value in district),
        release_harmed_citizens=sum(value < 0 for district in
                                    released.citizen_utilities for value in district),
        district_delta=tuple(b - a for a, b in zip(
            locked.district_utilities, released.district_utilities, strict=True)),
        citizen_delta=citizen_delta,
    )


def screen(outcomes: dict[tuple[str, str, bool], institution.Episode | None]
           ) -> dict[str, object]:
    inventory = design.cases()
    expected = {(case.case_id, arm, shocked) for case in inventory
                for arm in institution.ARMS for shocked in (False, True)}
    if type(outcomes) is not dict or not set(outcomes) <= expected:
        raise ValueError("outcome inventory")
    rows = []
    for case in inventory:
        arms = {}
        for arm in institution.ARMS:
            pair = tuple(outcomes.get((case.case_id, arm, shocked))
                         for shocked in (False, True))
            for shocked, episode in zip((False, True), pair, strict=True):
                if episode is not None and (
                    not isinstance(episode, institution.Episode)
                    or episode.arm != arm or episode.shocked != shocked
                ):
                    raise ValueError("episode arm or state mismatch")
            if all(episode is not None for episode in pair) and (
                _pre_shock(pair[0]) != _pre_shock(pair[1])
            ):
                raise ValueError("pre-shock prefix differs by realized state")
            arms[arm] = pair
        complete = all(episode is not None for pair in arms.values()
                       for episode in pair)
        locked = arms["irrevocable"][0]
        release = arms["constituent_release"][0]
        locked_y1 = (locked.active and locked.final.second_project == "Y1"
                     and 3 in locked.final.coalition) if locked else None
        release_y1 = (release.active and release.final.second_project == "Y1"
                      and 3 in release.final.coalition) if release else None
        agreement_changed = (_agreement(locked) != _agreement(release)
                             if complete else None)
        rows.append(dict(
            case_id=case.case_id, family=case.family, stratum=case.stratum,
            complete=complete,
            arm_state_available={arm: tuple(episode is not None for episode in pair)
                                 for arm, pair in arms.items()},
            arm_state_outcomes={arm: tuple(_summary(episode, case.game)
                                           for episode in pair)
                                for arm, pair in arms.items()},
            locked_active=locked.active if locked else None,
            release_active=release.active if release else None,
            locked_final_project=locked.final.second_project if locked else None,
            release_final_project=release.final.second_project if release else None,
            locked_y1_pivot_activated=locked_y1,
            release_y1_pivot_activated=release_y1,
            agreement_changed=agreement_changed,
            release_only=(release_y1 and not locked_y1) if complete else None,
            irrevocable_only=(locked_y1 and not release_y1) if complete else None,
            no_shock=_state(arms["irrevocable"][0],
                            arms["constituent_release"][0]) if complete else None,
            shock=_state(arms["irrevocable"][1],
                         arms["constituent_release"][1]) if complete else None,
        ))
    pivotal = [row for row in rows if row["stratum"] == "pivotal"]
    controls = [row for row in rows if row["stratum"] == "nonpivotal"]
    by_family = {
        family: dict(
            release_only=sum(row["release_only"] is True for row in pivotal
                             if row["family"] == family),
            irrevocable_only=sum(row["irrevocable_only"] is True for row in pivotal
                                 if row["family"] == family),
            complete=sum(row["complete"] for row in pivotal
                         if row["family"] == family),
        ) for family in ("overlap2", "overlap3")
    }
    control_changed = sum(row["agreement_changed"] is True for row in controls)
    missing = sum(not row["complete"] for row in rows)
    if missing:
        classification = "incomplete"
    elif control_changed:
        classification = "nonpivotal_control_changed"
    elif (all(value["release_only"] >= 3 for value in by_family.values())
          and all(value["irrevocable_only"] == 0 for value in by_family.values())):
        classification = "selected_case_release_behavioral_lead"
    elif (all(value["irrevocable_only"] >= 3 for value in by_family.values())
          and all(value["release_only"] == 0 for value in by_family.values())):
        classification = "selected_case_irrevocable_behavioral_lead"
    else:
        classification = "no_prespecified_behavioral_lead"
    return dict(rows=rows, missing_games=missing, control_changed=control_changed,
                by_family=by_family, classification=classification,
                caveat="Two opportunity-conditioned families, one model and one trajectory per arm. Menu regret uses each principal's or citizen's individually best X choice plus best of Y1/Y2/none; those individual ideals need not be collectively feasible. A selected-case lead is mechanism discovery, not population evidence or a paper result. Mechanical Y-ballot effects do not qualify.")
