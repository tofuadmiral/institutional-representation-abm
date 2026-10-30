"""Generator tests use engineering seeds, never model responses or pilot cases."""
from dataclasses import replace
from random import Random

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design


def test_constructed_columns_exact_sums_signs_and_bounds():
    rng = Random(90201)
    for total in range(-32, 33):
        if total == 0:
            continue
        for aligned in (True, False):
            values = design.citizen_column(rng, total, aligned)
            assert len(values) == 9 and sum(values) == total
            assert all(type(value) is int and 1 <= abs(value) <= 10 for value in values)
            assessment = institution.assess(values)
            assert (assessment.majority_passed == assessment.sum_passed) == aligned


def test_dynamic_counts_match_brute_force_small_instances():
    from itertools import product
    for positive, negative in ((1, 0), (0, 1), (1, 1), (2, 1)):
        domains = [range(1, 11)] * positive + [range(-10, 0)] * negative
        sums = [sum(row) for row in product(*domains)]
        for total in range(-21, 22):
            assert design._completions(positive, negative, total) == sums.count(total)


@pytest.mark.parametrize("seed", range(91000, 91012))
def test_pairs_have_matched_sums_fresh_roles_and_competing_opportunities(seed):
    pair = design.generate(seed)
    assert pair == design.generate(seed)
    assert pair.aligned.chairs[0] != pair.aligned.chairs[1]
    assert pair.aligned.utilities[1] == pair.conflict.utilities[1]
    assert design.district_sums(pair.aligned.utilities[0]) == (
        design.district_sums(pair.conflict.utilities[0]))
    report = design.opportunity(pair)
    assert report["distinct_baseline_coalitions"] >= 2
    assert report["baseline_passable"] >= 2
    assert report["majority_binding_passable"] >= 1
    assert report["changed_policy_scores"] >= 2
    assert report["changed_policy_support"] >= 2
    assert report["conditional_frontier_gap"] > 0
    for profile in (pair.aligned, pair.conflict):
        # Sum-aligned removal penalizes negative-welfare enactment further;
        # score magnitudes differ, but support signs and feasible frontier do not.
        baseline = design.conditional_menu(profile, "advisory_sum")
        assert baseline == design.conditional_menu(profile, "advisory_majority")
        binding_sum = design.conditional_menu(profile, "binding_sum")
        assert baseline["best_feasible_regret"] == binding_sum["best_feasible_regret"]
        for a, b in zip(baseline["policies"], binding_sum["policies"], strict=True):
            assert a["support"] == b["support"]
            assert b["score_differences"] == tuple(delta if delta >= 0 else
                                                 delta - profile.office_value
                                                 for delta in a["score_differences"])
    assert design.conditional_menu(pair.aligned, "binding_majority") == (
        design.conditional_menu(pair.aligned, "binding_sum"))


def test_zero_office_value_erases_benchmark_authority_difference_not_game():
    pair = design.generate(91050)
    profile = replace(pair.conflict, office_value=0)
    assert design.conditional_menu(profile, "binding_majority") == (
        design.conditional_menu(profile, "advisory_sum"))


def test_restricted_equilibria_match_every_unilateral_payoff_deviation():
    from itertools import product
    pair = design.generate(91060)
    profile = pair.conflict
    for arm in institution.ARMS:
        for policy in range(6):
            expected = []
            for votes in product((False, True), repeat=7):
                stable = True
                for actor in institution.ACTORS:
                    peers = votes[:actor] + votes[actor + 1:]
                    scores = institution.conditional_ballot_scores(profile, arm, actor,
                                                                   policy, peers)
                    if scores[not votes[actor]] > scores[votes[actor]]:
                        stable = False
                        break
                if stable:
                    expected.append(votes)
            actual = design.restricted_vote_equilibria(profile, arm, policy)
            assert actual == tuple(expected)
            # All-yes and all-no are stable purely through nonpivotality.
            # Do not describe the selected support frontier as a Nash prediction.
            assert (True,) * 7 in actual
            assert (False,) * 7 in actual


def test_opportunity_rejects_changed_district_sums_or_exposure_inventory():
    pair = design.generate(91051)
    with pytest.raises(ValueError, match="exposure inventory"):
        design.opportunity(replace(pair, exposed=()))
    table = list(pair.conflict.utilities[0])
    district = list(table[0])
    district[0] = (0,) * 6
    table[0] = tuple(district)
    changed = replace(pair.conflict, utilities=(tuple(table), pair.conflict.utilities[1]))
    with pytest.raises(ValueError, match="matched district policy sums"):
        design.opportunity(replace(pair, conflict=changed))


def test_bounded_failure_never_returns_a_replacement_or_relaxes_conditions():
    # B=0 makes the selected conditional gap impossible. It is a control,
    # not a positive-gap electorate population to be regenerated until it passes.
    with pytest.raises(ValueError, match="draw bound"):
        design.generate(91052, office_value=0, max_draws=2)
    for seed in (-1, True):
        with pytest.raises(ValueError, match="seed"):
            design.generate(seed)
