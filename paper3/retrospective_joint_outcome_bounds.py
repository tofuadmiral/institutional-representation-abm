"""Offline prospective all-assignment bounds; never an inference controller.

Missing outcomes range over the joint finite policy menu, not invented ballots
or independent citizen maxima. Completed terms are exact-replayed. These are
sharp menu-support bounds, not confidence intervals, population effects or a
scientific screen. Do not retrofit them into an older frozen analysis.
"""
from dataclasses import asdict
from fractions import Fraction
from itertools import product
import json

from paper3 import retrospective_accountability as institution

SCALARS = ("mean_normalized_district_regret", "mean_normalized_citizen_regret",
           "total_citizen_utility", "harmed_citizens", "removed_incumbents")


def _canonical(value):
    return json.dumps(asdict(value), sort_keys=True, allow_nan=False)


def _interval(values):
    return min(values), max(values)


def _regret(values, observed):
    lo, hi = _interval(values)
    return Fraction(hi - observed, hi - lo) if hi != lo else Fraction(0)


def _validate_observed(game, arm, observed):
    institution.require(type(observed) is tuple and len(observed) == 2,
                        "two term observations including missing")
    institution.require(observed[1] is None or observed[0] is not None,
                        "second term requires observed predecessor")
    previous = None
    for index, term in enumerate(observed):
        if term is None:
            continue
        institution.require(isinstance(term, institution.Term) and term.index == index,
                            "matching observation term")
        replayed = institution.resolve_term(game, arm, index, term.draft,
            term.responses, term.final, term.requested, previous)
        institution.require(_canonical(replayed) == _canonical(term),
                            "strict exact observed term replay")
        previous = term


def bounds(game, arm, observed=(None, None)):
    """Retain seven districts/63 citizens and coupled aggregate endpoints.

Each reported endpoint is attainable for that metric by a single legal pair
of enacted policies. Different metrics' endpoints need not be simultaneous.
Citizen/district regret benchmarks are unrestricted two-term menu optima,
not coalition-feasible policy recommendations or office-inclusive scores.
Only complete observed terms constrain the menu; no guessed partial votes.
"""
    institution.validate(game)
    institution.rules(arm)
    _validate_observed(game, arm, observed)
    width = len(game.utilities[0][0][0])
    menus = tuple((term.enacted,) if term is not None else tuple(range(width))
                  for term in observed)
    district_menus = [[sum(row[p] for row in district) for p in range(width)]
                      for table in game.utilities for district in table]
    citizen_menus = [tuple(a + b for a in first for b in second)
        for d in range(7) for first, second in zip(game.utilities[0][d],
                                                 game.utilities[1][d], strict=True)]
    district_benchmarks = [tuple(a + b for a in district_menus[d]
                                  for b in district_menus[7 + d]) for d in range(7)]
    outcomes = []
    for first, second in product(*menus):
        citizens = tuple(tuple(row[first] + later[second] for row, later in
            zip(game.utilities[0][d], game.utilities[1][d], strict=True)) for d in range(7))
        districts = tuple(map(sum, citizens))
        district_regrets = tuple(_regret(district_benchmarks[d], districts[d]) for d in range(7))
        citizen_regrets = tuple(tuple(_regret(citizen_menus[d * 9 + c], citizens[d][c])
                                       for c in range(9)) for d in range(7))
        first_values = [tuple(row[first] for row in district) for district in game.utilities[0]]
        retained = tuple(arm.startswith("advisory") or
            (sum(v >= 0 for v in values) >= 5 if arm.endswith("majority") else sum(values) >= 0)
            for values in first_values)
        outcomes.append(dict(enacted_policies=(first, second), citizen_utilities=citizens,
            district_utilities=districts, district_regrets=district_regrets,
            citizen_regrets=citizen_regrets, original_incumbent_scores=tuple(
                districts[d] + game.office_value * retained[d] for d in range(7)),
            successor_scores=tuple(None if retained[d] else sum(row[second] for row in
                game.utilities[1][d]) for d in range(7)),
            mean_normalized_district_regret=sum(district_regrets, Fraction(0)) / 7,
            mean_normalized_citizen_regret=sum((v for row in citizen_regrets for v in row), Fraction(0)) / 63,
            total_citizen_utility=sum(districts), harmed_citizens=sum(v < 0 for row in citizens for v in row),
            removed_incumbents=sum(not v for v in retained)))
    return dict(game_id=game.game_id, arm=arm, observed_terms=sum(t is not None for t in observed),
        complete=all(t is not None for t in observed), possible_policy_pairs=tuple(product(*menus)),
        possibilities=tuple(outcomes), scalar_bounds={k: _interval([r[k] for r in outcomes]) for k in SCALARS},
        district_utility_bounds=tuple(_interval([r["district_utilities"][d] for r in outcomes]) for d in range(7)),
        district_regret_bounds=tuple(_interval([r["district_regrets"][d] for r in outcomes]) for d in range(7)),
        citizen_utility_bounds=tuple(tuple(_interval([r["citizen_utilities"][d][c] for r in outcomes])
                                          for c in range(9)) for d in range(7)),
        citizen_regret_bounds=tuple(tuple(_interval([r["citizen_regrets"][d][c] for r in outcomes])
                                         for c in range(9)) for d in range(7)),
        publication_evidence=False,
        limitations="Sharp finite-menu support bounds, not confidence intervals. Per-metric endpoints need not coincide. Normalized principal regret is not total citizen welfare; office scores are not either. No preferred policy or causal claim.")


def first_term_bounds(game, arm, observed=(None, None)):
    """Anticipatory behavior before replacement, with all-assignment missingness.

    A completed first term is observed even if the second term later fails.
    Never call that a completed episode, or change an older two-term screen.
    Benchmarks remain each principal's unrestricted first-term policy menu.
    """
    institution.validate(game)
    institution.rules(arm)
    _validate_observed(game, arm, observed)
    width = len(game.utilities[0][0][0])
    policies = (observed[0].enacted,) if observed[0] is not None else tuple(range(width))
    binding, majority = institution.rules(arm)
    outcomes = []
    for policy in policies:
        metrics = institution.menu_metrics(game, 0, policy)
        citizens = tuple(item["citizen_utilities"] for item in metrics)
        districts = tuple(map(sum, citizens))
        district_regrets = tuple(item["normalized_district_regret"] for item in metrics)
        citizen_regrets = tuple(tuple(_regret(game.utilities[0][d][c], citizens[d][c])
            for c in range(9)) for d in range(7))
        retained = tuple(not binding or
            (item["assessment"]["majority_passed"] if majority
             else item["assessment"]["sum_passed"]) for item in metrics)
        outcomes.append(dict(enacted_policy=policy, district_utilities=districts,
            citizen_utilities=citizens, district_regrets=district_regrets,
            citizen_regrets=citizen_regrets,
            mean_normalized_district_regret=sum(district_regrets, Fraction(0)) / 7,
            mean_normalized_citizen_regret=sum((x for row in citizen_regrets for x in row), Fraction(0)) / 63,
            total_citizen_utility=sum(districts),
            harmed_citizens=sum(x < 0 for row in citizens for x in row),
            removed_incumbents=sum(not x for x in retained)))
    return dict(game_id=game.game_id, arm=arm, horizon="first_term",
        complete=observed[0] is not None, episode_complete=all(t is not None for t in observed),
        observed_terms=sum(t is not None for t in observed), possible_policies=policies,
        possibilities=tuple(outcomes), scalar_bounds={
            key: _interval([row[key] for row in outcomes]) for key in SCALARS},
        district_utility_bounds=tuple(_interval([row["district_utilities"][d] for row in outcomes]) for d in range(7)),
        district_regret_bounds=tuple(_interval([row["district_regrets"][d] for row in outcomes]) for d in range(7)),
        citizen_utility_bounds=tuple(tuple(_interval([row["citizen_utilities"][d][c] for row in outcomes])
            for c in range(9)) for d in range(7)),
        citizen_regret_bounds=tuple(tuple(_interval([row["citizen_regrets"][d][c] for row in outcomes])
            for c in range(9)) for d in range(7)),
        publication_evidence=False,
        limitations="First-term menu support, not full-episode completion or a "
                    "population effect. Fidelity and welfare exclude office value; "
                    "two-term missingness must still be reported separately.")


def contrast(assignments, metric, horizon="two_term"):
    """Linear all-assignment contrast; weights and inventory fixed prospectively.

Each tuple is (id, game, arm, two observed terms, signed rational weight).
Missing assignments remain explicit. Independent potential-outcome support
across arms is unrestricted; paired seeds do not force identical outcomes.
"""
    institution.require(type(assignments) is tuple and bool(assignments) and metric in SCALARS,
                        "nonempty assigned contrast/metric")
    institution.require(horizon in ("first_term", "two_term"), "explicit outcome horizon")
    ids = [row[0] for row in assignments]
    institution.require(all(type(i) is str and i for i in ids) and len(set(ids)) == len(ids),
                        "unique assignment ids")
    low = high = Fraction(0)
    rows = []
    for identifier, game, arm, observed, weight in assignments:
        institution.require(type(weight) in (int, Fraction) and weight != 0,
                            "nonzero exact contrast weight")
        result = (first_term_bounds if horizon == "first_term" else bounds)(game, arm, observed)
        a, b = result["scalar_bounds"][metric]
        x, y = sorted((weight * a, weight * b))
        low += x
        high += y
        rows.append(dict(id=identifier, weight=weight, complete=result["complete"],
                         episode_complete=all(t is not None for t in observed), bounds=(a, b)))
    return dict(metric=metric, horizon=horizon, assignments=tuple(rows), assigned=len(rows),
        completed=sum(row["complete"] for row in rows), support_bounds=(low, high),
        zero_excluded=(low > 0 or high < 0), publication_evidence=False,
        caveat="Support bounds alone do not satisfy a scientific gate or identify a population effect.")
