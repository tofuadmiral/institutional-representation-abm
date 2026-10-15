"""No-inference tests for the two-package constituent-release opportunity."""

from fractions import Fraction

import pytest

from paper3.mandate_release_rival_opportunity import (
    acceptable_coalitions,
    bundle_total,
    certificate,
    district_total,
    scripted_outcome,
    witness,
)


def test_two_packages_support_rival_non_dominating_coalitions():
    game = witness()
    assert [district_total(game.before, actor, "X") for actor in range(7)] == [
        8, 8, 8, -5, -5, -5, -6,
    ]
    assert [district_total(game.before, actor, "Y1") for actor in range(7)] == [
        -4, -4, -4, 8, -1, -1, -6,
    ]
    assert [district_total(game.before, actor, "Y2") for actor in range(7)] == [
        -5, -5, -5, 4, 8, 8, -6,
    ]
    assert [bundle_total(game.before, actor, "Y1") for actor in range(7)] == [
        4, 4, 4, 3, -6, -6, -12,
    ]
    assert [bundle_total(game.before, actor, "Y2") for actor in range(7)] == [
        3, 3, 3, -1, 3, 3, -12,
    ]
    assert acceptable_coalitions(game, "Y1") == ((0, 1, 2, 3),)
    assert len(acceptable_coalitions(game, "Y2")) == 5
    assert (0, 1, 2, 4) in acceptable_coalitions(game, "Y2")
    assert (0, 1, 2, 5) in acceptable_coalitions(game, "Y2")


def test_shock_release_is_pivotal_only_for_first_package():
    game = witness()
    y1 = (0, 1, 2, 3)
    locked = scripted_outcome(game, "Y1", y1, shocked=True, release_right=False)
    released = scripted_outcome(game, "Y1", y1, shocked=True, release_right=True)
    assert locked.first_passed and released.first_passed
    assert locked.second_passed and not released.second_passed
    assert locked.district_utilities[3] == -12
    assert released.district_utilities[3] == -5
    assert released.released_members == (3,)
    no_shock_locked = scripted_outcome(game, "Y1", y1, shocked=False,
                                       release_right=False)
    no_shock_release = scripted_outcome(game, "Y1", y1, shocked=False,
                                        release_right=True)
    assert no_shock_locked == no_shock_release

    y2 = (0, 1, 2, 4)
    y2_locked = scripted_outcome(game, "Y2", y2, shocked=True,
                                 release_right=False)
    y2_release = scripted_outcome(game, "Y2", y2, shocked=True,
                                  release_right=True)
    assert y2_locked == y2_release
    assert y2_locked.first_passed and y2_locked.second_passed


def test_expected_choice_opportunity_is_not_a_claim_about_model_behavior():
    result = certificate(witness(shock_probability=Fraction(1, 4)))
    assert result["individual_positive_district_counts"] == {"X": 3, "Y1": 1, "Y2": 3}
    assert result["shock_release_votes"] == 6
    assert result["y1_expected_pivot_locked"] == Fraction(-3, 4)
    assert result["y1_expected_pivot_release"] == Fraction(1, 1)
    assert result["y1_expected_a0_locked"] == Fraction(4, 1)
    assert result["y1_expected_a0_release"] == Fraction(5, 1)
    assert result["y2_expected_a0"] == Fraction(3, 1)
    assert result["y1_expected_total_welfare_locked"] < result[
        "y1_expected_total_welfare_release"] < result["y2_expected_total_welfare"]


def test_all_considered_outcomes_preserve_all_citizen_rows():
    game = witness()
    for policy in ("Y1", "Y2"):
        for coalition in acceptable_coalitions(game, policy):
            for shocked in (False, True):
                for release_right in (False, True):
                    result = scripted_outcome(game, policy, coalition,
                                              shocked=shocked,
                                              release_right=release_right)
                    assert len(result.citizen_utilities) == 7
                    assert all(len(district) == 9 for district in result.citizen_utilities)
                    assert tuple(map(sum, result.citizen_utilities)) == result.district_utilities
    with pytest.raises(ValueError):
        scripted_outcome(game, "Y1", (0, 1, 2, 4), shocked=True,
                         release_right=True)
