"""Engineering checks only: exhaustive finite support, not agent evidence."""
from dataclasses import replace
from fractions import Fraction
from itertools import product

import pytest

from paper3 import retrospective_joint_outcome_bounds as b
from paper3 import retrospective_accountability as institution
from tests.test_paper3_retrospective_score_ledger import fixture


def episode(game, arm, first, second):
    def ask(actor, identity, term, stage, context, index):
        policy = (first, second)[term]
        if stage in ("draft", "final"):
            return dict(policy=policy, message="offline")
        if stage == "response":
            return dict(support=False, counter_policy=0, message="offline")
        return dict(vote=actor < 4)
    return institution.episode(game, arm, ask)


@pytest.mark.parametrize("width", range(2, 9))
@pytest.mark.parametrize("arm", institution.ARMS)
@pytest.mark.parametrize("observed_count", range(3))
def test_all_support_endpoints_against_exhaustive_engine_episodes(width, arm, observed_count):
    game = fixture(width)
    saved = episode(game, arm, 1, 2 % width)
    observed = tuple(t if i < observed_count else None for i, t in enumerate(saved.terms))
    result = b.bounds(game, arm, observed)
    menus = [range(width) if t is None else (t.enacted,) for t in observed]
    candidates = [episode(game, arm, p, q) for p, q in product(*menus)]
    assert result["possible_policy_pairs"] == tuple(product(*menus))
    assert result["observed_terms"] == observed_count
    assert result["complete"] is (observed_count == 2)
    for d in range(7):
        vals = [e.cumulative_district_utilities[d] for e in candidates]
        assert result["district_utility_bounds"][d] == (min(vals), max(vals))
        for c in range(9):
            vals = [e.cumulative_citizen_utilities[d][c] for e in candidates]
            assert result["citizen_utility_bounds"][d][c] == (min(vals), max(vals))
    total = [sum(e.cumulative_district_utilities) for e in candidates]
    harms = [sum(v < 0 for district in e.cumulative_citizen_utilities for v in district)
             for e in candidates]
    assert result["scalar_bounds"]["total_citizen_utility"] == (min(total), max(total))
    assert result["scalar_bounds"]["harmed_citizens"] == (min(harms), max(harms))
    for row, expected in zip(result["possibilities"], candidates, strict=True):
        assert row["citizen_utilities"] == expected.cumulative_citizen_utilities
        assert row["original_incumbent_scores"] == expected.initial_incumbent_scores
        assert row["successor_scores"] == expected.successor_scores
        assert all(Fraction(0) <= r <= Fraction(1) for r in row["district_regrets"])
        assert all(Fraction(0) <= r <= Fraction(1) for district in row["citizen_regrets"] for r in district)
        for metric in b.SCALARS:
            lo, hi = result["scalar_bounds"][metric]
            assert lo <= row[metric] <= hi
    # Both endpoints really are attained by one joint policy pair, per metric.
    for metric, endpoints in result["scalar_bounds"].items():
        assert all(v in [r[metric] for r in result["possibilities"]] for v in endpoints)


def test_aggregate_welfare_not_sum_of_incompatible_individual_extrema():
    result = b.bounds(fixture(4), "binding_majority")
    individual_max_sum = sum(v[1] for district in result["citizen_utility_bounds"] for v in district)
    assert result["scalar_bounds"]["total_citizen_utility"][1] < individual_max_sum
    assert len(result["citizen_utility_bounds"]) == 7
    assert all(len(row) == 9 for row in result["citizen_utility_bounds"])


def test_constant_preferences_have_zero_regret_without_division_by_zero():
    game = fixture(3)
    tables = tuple(tuple(tuple((0, 0, 0) for _ in range(9)) for _ in range(7)) for _ in range(2))
    result = b.bounds(replace(game, utilities=tables), "binding_sum")
    assert result["scalar_bounds"]["mean_normalized_district_regret"] == (0, 0)
    assert result["scalar_bounds"]["mean_normalized_citizen_regret"] == (0, 0)
    assert result["scalar_bounds"]["harmed_citizens"] == (0, 0)


def test_failed_second_term_preserves_first_term_information_and_missingness():
    game = fixture(4)
    saved = episode(game, "binding_sum", 1, 2)
    full = b.bounds(game, "binding_sum", saved.terms)
    partial = b.bounds(game, "binding_sum", (saved.terms[0], None))
    absent = b.bounds(game, "binding_sum")
    assert len(full["possibilities"]) == 1
    assert len(partial["possibilities"]) == 4
    assert len(absent["possibilities"]) == 16
    for metric in b.SCALARS:
        a, z = absent["scalar_bounds"][metric]
        p, q = partial["scalar_bounds"][metric]
        x, y = full["scalar_bounds"][metric]
        assert a <= p <= x == y <= q <= z
    with pytest.raises(ValueError, match="predecessor"):
        b.bounds(game, "binding_sum", (None, saved.terms[1]))


def test_boolean_integer_observation_forgery_rejected_strictly():
    game = fixture(4)
    saved = episode(game, "binding_majority", 1, 2)
    bad = replace(saved.terms[0], proposal_passed=1)
    assert bad == saved.terms[0]  # Python equality alone would silently accept it.
    with pytest.raises(ValueError, match="strict exact"):
        b.bounds(game, "binding_majority", (bad, None))
    with pytest.raises(ValueError):
        b.bounds(game, "binding_sum", saved.terms)


def test_linear_contrast_retains_all_assigned_missing_arms_and_signed_weights():
    game = fixture(4)
    arms = institution.ARMS
    weights = (1, -1, -1, 1)
    assignments = tuple((arm, game, arm, (None, None), w) for arm, w in zip(arms, weights, strict=True))
    report = b.contrast(assignments, "total_citizen_utility")
    supports = [b.bounds(game, arm)["scalar_bounds"]["total_citizen_utility"] for arm in arms]
    extremes = [sum(w * v for w, v in zip(weights, values, strict=True)) for values in product(*supports)]
    assert report["assigned"] == 4 and report["completed"] == 0
    assert report["support_bounds"] == (min(extremes), max(extremes))
    assert not report["zero_excluded"] and not report["publication_evidence"]
    complete = tuple((arm, game, arm, episode(game, arm, 1, 2).terms, w)
                     for arm, w in zip(arms, weights, strict=True))
    report = b.contrast(complete, "mean_normalized_district_regret")
    assert report["completed"] == 4 and report["support_bounds"] == (0, 0)
    with pytest.raises(ValueError, match="unique"):
        b.contrast((assignments[0], assignments[0]), "harmed_citizens")
    with pytest.raises(ValueError, match="weight"):
        b.contrast(((*assignments[0][:-1], True),), "harmed_citizens")


@pytest.mark.parametrize("width", range(2, 9))
@pytest.mark.parametrize("arm", institution.ARMS)
def test_first_term_support_matches_engine_and_preserves_second_term_failure(width, arm):
    game = fixture(width)
    saved = episode(game, arm, 1, 0)
    absent = b.first_term_bounds(game, arm)
    partial = b.first_term_bounds(game, arm, (saved.terms[0], None))
    complete = b.first_term_bounds(game, arm, saved.terms)
    assert not absent["complete"] and not absent["episode_complete"]
    assert partial["complete"] and not partial["episode_complete"]
    assert complete["complete"] and complete["episode_complete"]
    assert partial["scalar_bounds"] == complete["scalar_bounds"]
    assert partial["possible_policies"] == (1,)
    assert len(absent["citizen_utility_bounds"]) == 7
    assert all(len(row) == 9 for row in absent["citizen_utility_bounds"])
    candidates = [episode(game, arm, p, 0).terms[0] for p in range(width)]
    assert absent["possible_policies"] == tuple(range(width))
    for row, term in zip(absent["possibilities"], candidates, strict=True):
        assert row["citizen_utilities"] == term.citizen_utilities
        assert row["district_utilities"] == tuple(a.district_sum for a in term.assessments)
        assert row["removed_incumbents"] == sum(not a for a in term.tenure_retained)
        assert row["total_citizen_utility"] == sum(row["district_utilities"])
        for d in range(7):
            menu = [sum(v[p] for v in game.utilities[0][d]) for p in range(width)]
            expected = Fraction(max(menu) - row["district_utilities"][d], max(menu) - min(menu)) if max(menu) != min(menu) else 0
            assert row["district_regrets"][d] == expected
            for c in range(9):
                menu = game.utilities[0][d][c]
                expected = Fraction(max(menu) - row["citizen_utilities"][d][c], max(menu) - min(menu)) if max(menu) != min(menu) else 0
                assert row["citizen_regrets"][d][c] == expected
    for metric in b.SCALARS:
        values = [row[metric] for row in absent["possibilities"]]
        assert absent["scalar_bounds"][metric] == (min(values), max(values))
        assert partial["scalar_bounds"][metric][0] == partial["scalar_bounds"][metric][1]
    for d in range(7):
        values = [row["district_utilities"][d] for row in absent["possibilities"]]
        assert absent["district_utility_bounds"][d] == (min(values), max(values))
    with pytest.raises(ValueError, match="strict exact"):
        b.first_term_bounds(game, arm, (replace(saved.terms[0], proposal_passed=1), None))


def test_first_term_all_assignment_contrast_not_complete_episode_filter():
    game = fixture(4)
    assigned = tuple((arm, game, arm, (episode(game, arm, 1, 2).terms[0], None), weight)
        for arm, weight in zip(institution.ARMS, (1, -1, -1, 1), strict=True))
    first = b.contrast(assigned, "mean_normalized_district_regret", "first_term")
    full = b.contrast(assigned, "mean_normalized_district_regret")
    assert first["completed"] == 4 and first["support_bounds"] == (0, 0)
    assert full["completed"] == 0
    assert all(not row["episode_complete"] for row in first["assignments"])
    partially_missing = (*assigned[:-1], (*assigned[-1][:3], (None, None), assigned[-1][-1]))
    missing = b.contrast(partially_missing, "mean_normalized_district_regret", "first_term")
    assert missing["assigned"] == 4 and missing["completed"] == 3
    assert missing["support_bounds"][0] < missing["support_bounds"][1]
    assert not missing["publication_evidence"]
    with pytest.raises(ValueError, match="horizon"):
        b.contrast(assigned, "total_citizen_utility", "served_terms_only")
