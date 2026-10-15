"""Unfrozen, two-sided discovery screen; no inference or population claim.

The unit is a matched electorate pair, never a citizen or an API call.
Missing first-term outcomes range over the full finite policy menu. Actual
first terms remain usable for readout even if their second term failed;
the discovery gate nevertheless requires all two-term episodes complete.
"""
from dataclasses import asdict
from fractions import Fraction
from statistics import median

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design

PROPOSED_MIN_EFFECT = Fraction(1, 25)
STRATA = ("aligned", "conflict")
WEIGHTS = {"binding_majority": 1, "binding_sum": -1,
           "advisory_majority": -1, "advisory_sum": 1}


def _mean_regret(game, policy):
    return sum((row["normalized_district_regret"] for row in
                institution.menu_metrics(game, 0, policy)), Fraction(0)) / 7


def first_term(game, arm, term):
    institution.validate(game)
    institution.rules(arm)
    menu = range(len(game.utilities[0][0][0]))
    if term is None:
        possibilities = [_mean_regret(game, policy) for policy in menu]
        return dict(available=False, mean_regret=None,
                    regret_bounds=(min(possibilities), max(possibilities)),
                    citizen_utility_bounds=tuple(tuple((min(row), max(row)) for row in district)
                                                 for district in game.utilities[0]),
                    district_utility_bounds=tuple((min(row), max(row)) for row in
                                                 design.district_sums(game.utilities[0])))
    institution.require(isinstance(term, institution.Term) and term.index == 0,
                        "first-term observation")
    replayed = institution.resolve_term(game, arm, 0, term.draft, term.responses,
                                        term.final, term.requested)
    institution.require(term == replayed, "first-term replay mismatch")
    metrics = institution.menu_metrics(game, 0, term.enacted)
    regret = _mean_regret(game, term.enacted)
    ranks = tuple(tuple(1 + sum(value > row[term.enacted] for value in row) for row in district)
                  for district in game.utilities[0])
    return dict(available=True, mean_regret=regret, regret_bounds=(regret, regret),
                term=asdict(term), district_metrics=metrics, citizen_menu_ranks=ranks,
                median_citizen_menu_ranks=tuple(median(row) for row in ranks),
                district_utilities=tuple(item.district_sum for item in term.assessments),
                total_welfare=sum(item.district_sum for item in term.assessments),
                harmed_citizens=sum(row["harmed_citizens"] for row in metrics),
                counteroffers_distinct_from_draft=sum(item.counter_policy != term.draft.policy
                                                     for item in term.responses),
                chair_revised_offer=term.final.policy != term.draft.policy)


def _contrast(rows):
    low = high = Fraction(0)
    for arm, weight in WEIGHTS.items():
        a, b = rows[arm]["regret_bounds"]
        low += weight * (a if weight > 0 else b)
        high += weight * (b if weight > 0 else a)
    return low, high


def screen(pairs, observations, *, completed_episodes, qualified):
    """Proposed gate only: two pairs, full coverage, signed/control coherence.

    Require |mean conflict-minus-aligned interaction| >= 0.04 normalized regret,
    the same nonzero direction in both pairs, and mean absolute aligned
    interaction <= half the conflict interaction. Either direction can justify
    proposing independent validation, never a publishable claim or new run.
    All thresholds must join the source/case freeze before model calls.
    """
    institution.require(type(pairs) is tuple and len(pairs) == 2 and
                        all(isinstance(pair, design.Pair) for pair in pairs) and
                        len({pair.seed for pair in pairs}) == 2, "two distinct pair blocks")
    institution.require(type(qualified) is bool, "qualification boolean")
    expected = {(pair.seed, stratum, arm) for pair in pairs for stratum in STRATA
                for arm in institution.ARMS}
    institution.require(type(observations) is dict and set(observations) == expected,
                        "retain all sixteen assigned observations, including missing")
    institution.require(type(completed_episodes) is set and completed_episodes <= expected,
                        "episode completion inventory")
    rows = []
    for pair in pairs:
        design.opportunity(pair)
        strata = {}
        for stratum in STRATA:
            game = getattr(pair, stratum)
            strata[stratum] = {arm: first_term(game, arm, observations[(pair.seed, stratum, arm)])
                               for arm in institution.ARMS}
        contrasts = {stratum: _contrast(strata[stratum]) for stratum in STRATA}
        a, b = contrasts["aligned"], contrasts["conflict"]
        difference = (b[0] - a[1], b[1] - a[0])
        rows.append(dict(seed=pair.seed, strata=strata, interaction_bounds=contrasts,
                         conflict_minus_aligned_bounds=difference))
    available = {key for key, term in observations.items() if term is not None}
    institution.require(completed_episodes <= available, "completed episode missing first term")
    complete = available == completed_episodes == expected
    mean_bounds = tuple(sum((row["conflict_minus_aligned_bounds"][index] for row in rows),
                            Fraction(0)) / 2 for index in (0, 1))
    verdict = "incomplete"
    direction = None
    coherent = attenuation = magnitude = None
    if not qualified:
        verdict = "qualification_failed"
    elif complete:
        differences = [row["conflict_minus_aligned_bounds"][0] for row in rows]
        coherent = all(value > 0 for value in differences) or all(value < 0 for value in differences)
        alignment = sum(abs(row["interaction_bounds"]["aligned"][0]) for row in rows) / 2
        conflict = sum(abs(row["interaction_bounds"]["conflict"][0]) for row in rows) / 2
        attenuation = alignment <= conflict / 2
        magnitude = abs(mean_bounds[0]) >= PROPOSED_MIN_EFFECT
        if coherent and attenuation and magnitude:
            verdict = "selected_case_lead"
            direction = "higher_sum_mandate_regret" if mean_bounds[0] > 0 else "lower_sum_mandate_regret"
        else:
            verdict = "no_selected_case_lead"
    return dict(verdict=verdict, direction=direction, assigned=16, first_terms_available=len(available),
                episodes_complete=len(completed_episodes), qualified=qualified, blocks=tuple(rows),
                mean_contrast_bounds=mean_bounds, same_direction=coherent,
                aligned_attenuation=attenuation, minimum_magnitude=magnitude,
                min_effect=PROPOSED_MIN_EFFECT, publication_evidence=False)
