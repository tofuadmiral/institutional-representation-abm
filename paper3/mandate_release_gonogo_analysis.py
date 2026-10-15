"""Frozen feasibility triage and worst-case missingness bounds, not inference."""
from fractions import Fraction

from paper3 import mandate_release_gonogo_design as design
from paper3 import mandate_release_fresh_analysis as metrics
from paper3 import mandate_release_institution as institution


def _citizen_bounds(case, pair):
    """Safe menu bounds for every missing outcome; no imputed enactment."""
    result = []
    p = case.game.shock_probability
    for actor in range(7):
        district = []
        for citizen in range(9):
            lower = upper = Fraction(0)
            for state, weight in ((0, 1 - p), (1, p)):
                if pair[state] is not None:
                    lo = hi = pair[state].citizen_utilities[actor][citizen]
                else:
                    row = (case.game.after if state else case.game.before)[actor][citizen]
                    lo = min(0, row[0]) + min(0, row[1], row[2])
                    hi = max(0, row[0]) + max(0, row[1], row[2])
                lower += weight * lo
                upper += weight * hi
            district.append((lower, upper))
        result.append(district)
    return result


def screen(outcomes):
    inventory = design.cases()
    expected = {(case.case_id, arm, shock) for case in inventory
                for arm in institution.ARMS for shock in (False, True)}
    if not set(outcomes) <= expected:
        raise ValueError("unexpected outcome")
    rows = []
    for case in inventory:
        arms = {arm: tuple(outcomes.get((case.case_id, arm, shock))
                           for shock in (False, True)) for arm in institution.ARMS}
        for arm, pair in arms.items():
            for shock, episode in zip((False, True), pair, strict=True):
                if episode is not None and (episode.arm != arm or episode.shocked != shock):
                    raise ValueError("arm/state mismatch")
            if all(pair) and metrics._pre_shock(pair[0]) != metrics._pre_shock(pair[1]):
                raise ValueError("divergent pre-shock history")
        complete = all(item is not None for pair in arms.values() for item in pair)
        locked, released = arms["irrevocable"][0], arms["constituent_release"][0]
        activation = {arm: (int(pair[0].active and pair[0].final.second_project == "Y1"
                               and 3 in pair[0].final.coalition)
                           if pair[0] is not None else None)
                      for arm, pair in arms.items()}
        delta = (activation["constituent_release"] - activation["irrevocable"]
                 if complete else None)
        expected_district_delta = None
        expected_citizen_delta = None
        if complete:
            p = case.game.shock_probability
            expected_district_delta = [str(sum(
                weight * (arms["constituent_release"][shock].district_utilities[actor]
                          - arms["irrevocable"][shock].district_utilities[actor])
                for shock, weight in ((0, 1 - p), (1, p)))) for actor in range(7)]
            expected_citizen_delta = [[str(sum(
                weight * (arms["constituent_release"][shock].citizen_utilities[actor][citizen]
                          - arms["irrevocable"][shock].citizen_utilities[actor][citizen])
                for shock, weight in ((0, 1 - p), (1, p)))) for citizen in range(9)]
                                     for actor in range(7)]
        payoff_bounds = {arm: _citizen_bounds(case, pair) for arm, pair in arms.items()}
        citizen_delta_bounds = [[[str(payoff_bounds["constituent_release"][actor][citizen][0]
                                      - payoff_bounds["irrevocable"][actor][citizen][1]),
                                  str(payoff_bounds["constituent_release"][actor][citizen][1]
                                      - payoff_bounds["irrevocable"][actor][citizen][0])]
                                 for citizen in range(9)] for actor in range(7)]
        district_delta_bounds = [[str(sum(Fraction(citizen_delta_bounds[actor][citizen][bound])
                                          for citizen in range(9))) for bound in (0, 1)]
                                 for actor in range(7)]
        rows.append(dict(
            case_id=case.case_id, family=case.family, stratum=case.stratum,
            complete=complete, activation=activation, activation_delta=delta,
            arm_state_available={arm: [item is not None for item in pair]
                                 for arm, pair in arms.items()},
            any_active=bool(complete and (locked.active or released.active)),
            agreement_changed=(metrics._agreement(locked) != metrics._agreement(released)
                               if complete else None),
            expected_district_delta=expected_district_delta,
            expected_citizen_delta=expected_citizen_delta,
            expected_citizen_delta_bounds=citizen_delta_bounds,
            expected_district_delta_bounds=district_delta_bounds,
            arm_state_outcomes={arm: [metrics._summary(item, case.game) for item in pair]
                                for arm, pair in arms.items()}))
    pivotal = [row for row in rows if row["stratum"] == "pivotal"]
    controls = [row for row in rows if row["stratum"] == "nonpivotal"]
    observed = sum(row["activation_delta"] or 0 for row in pivotal)
    missing = sum(not row["complete"] for row in pivotal)
    bounds = (Fraction(observed - missing, 3), Fraction(observed + missing, 3))
    active = sum(row["any_active"] for row in rows)
    stable_controls = sum(row["complete"] and not row["agreement_changed"]
                          and row["any_active"] for row in controls)
    citizen_effect_cases = sum(row["complete"] and row["agreement_changed"]
                              and any(Fraction(value) != 0
                                      for value in row["expected_district_delta"])
                              for row in pivotal)
    if sum(row["complete"] for row in pivotal) < 3 or sum(row["complete"] for row in controls) < 2:
        verdict = "inconclusive_coverage_stop"
    elif active < 4:
        verdict = "no_go_agreements_rare"
    elif stable_controls < 2:
        verdict = "no_go_control_specificity"
    elif (bounds[0] >= Fraction(2, 3) or bounds[1] <= Fraction(-2, 3)) and citizen_effect_cases >= 2:
        verdict = "go_independent_validation_only"
    else:
        verdict = "no_go_no_consistent_behavioral_lead"
    return dict(verdict=verdict, complete_pairs=sum(row["complete"] for row in rows),
                assigned_pairs=6, active_pairs_lower_bound=active,
                stable_active_controls_lower_bound=stable_controls,
                pivotal_citizen_effect_cases=citizen_effect_cases,
                pivotal_mean_activation_delta_bounds=[str(value) for value in bounds],
                pivotal_missing_pairs=missing,
                control_missing_pairs=sum(not row["complete"] for row in controls),
                all_assigned_mean_total_welfare_delta_bounds=[str(sum(
                    Fraction(row["expected_district_delta_bounds"][actor][bound])
                    for row in rows for actor in range(7)) / 6) for bound in (0, 1)],
                cases=rows,
                interpretation="Directional selected-case triage on three independent draws/topologies, one model and one trajectory per arm. No p-value, population claim, or publication result. A go authorizes proposing independent validation, not launching it.")
