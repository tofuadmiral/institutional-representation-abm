"""Offline tests of the release-right structural witness, not model evidence."""

from fractions import Fraction

import pytest

from paper3.mandate_release_opportunity import (
    district_total,
    initially_acceptable_coalitions,
    opportunity_certificate,
    package_total,
    release_approved,
    scripted_outcome,
    witness,
)


def test_witness_has_genuine_exchange_and_constituent_disagreement():
    game = witness()
    assert len(game.before) == len(game.after) == 7
    assert all(len(district) == 9 for district in game.before)
    assert [district_total(game.before, actor, "X") for actor in range(7)] == [
        8, 8, 8, -5, -5, -5, -6,
    ]
    assert [district_total(game.before, actor, "Y") for actor in range(7)] == [
        -5, -5, -5, 8, 8, 8, -6,
    ]
    assert [package_total(game.before, actor) for actor in range(7)] == [
        3, 3, 3, 3, 3, 3, -12,
    ]
    assert [package_total(game.after, actor) for actor in range(7)] == [
        3, 3, 3, -12, 3, 3, -12,
    ]
    assert sum(x + y > 0 for x, y in game.before[3]) == 6
    assert sum(x + y < 0 for x, y in game.before[3]) == 3
    assert not release_approved(game, 3, shocked=False)
    assert release_approved(game, 3, shocked=True)


def test_release_is_pivotal_for_some_coalitions_but_not_others():
    game = witness()
    coalitions = initially_acceptable_coalitions(game)
    assert len(coalitions) == 15
    certificate = opportunity_certificate(game)
    assert certificate["citizens"] == 63
    assert certificate["initial_positive_districts_by_project"] == {"X": 3, "Y": 3}
    assert certificate["release_votes_after_shock"] == {3: 6}
    assert certificate["no_shock_disagreement_coalitions"] == ()
    assert certificate["pivotal_release_coalitions"] == (
        (0, 3, 4, 5), (1, 3, 4, 5), (2, 3, 4, 5),
    )
    assert len(set(coalitions) - set(certificate["pivotal_release_coalitions"])) == 12

    pivot = (0, 3, 4, 5)
    locked = scripted_outcome(game, pivot, shocked=True, release_right=False)
    released = scripted_outcome(game, pivot, shocked=True, release_right=True)
    assert locked.first_passed and released.first_passed
    assert locked.second_passed and not released.second_passed
    assert locked.released_members == ()
    assert released.released_members == (3,)
    assert locked.district_utilities[3] == -12
    assert released.district_utilities[3] == -5
    assert certificate["example_shock_welfare_locked"] == -9
    assert certificate["example_shock_welfare_release"] == 3
    assert certificate["example_pivot_expected_utility_locked"] == Fraction(-3, 4)
    assert certificate["example_pivot_expected_utility_release"] == Fraction(1, 1)


def test_shared_sector_shock_makes_release_pivotal_across_coalitions():
    game = witness(sector_shock=True)
    certificate = opportunity_certificate(game)
    assert certificate["shocked_package_district_sums"] == (
        3, 3, 3, -12, -12, -12, -12,
    )
    assert certificate["release_votes_after_shock"] == {3: 6, 4: 6, 5: 6}
    assert certificate["pivotal_release_coalitions"] == certificate["acceptable_coalitions"]
    assert certificate["no_shock_disagreement_coalitions"] == ()
    assert scripted_outcome(game, (0, 3, 4, 5), shocked=True,
                            release_right=True).released_members == (3, 4, 5)


def test_probability_changes_ex_ante_sign_without_changing_opportunity():
    low_risk = opportunity_certificate(witness(sector_shock=True,
                                               shock_probability=Fraction(1, 10)))
    middle_risk = opportunity_certificate(witness(sector_shock=True,
                                                  shock_probability=Fraction(1, 4)))
    high_risk = opportunity_certificate(witness(sector_shock=True,
                                                shock_probability=Fraction(1, 2)))
    assert low_risk["pivotal_release_coalitions"] == middle_risk[
        "pivotal_release_coalitions"] == high_risk["pivotal_release_coalitions"]
    assert low_risk["example_pivot_expected_utility_locked"] > 0
    assert low_risk["example_pivot_expected_utility_release"] > 0
    assert middle_risk["example_pivot_expected_utility_locked"] < 0
    assert middle_risk["example_pivot_expected_utility_release"] > 0
    assert high_risk["example_pivot_expected_utility_locked"] < 0
    assert high_risk["example_pivot_expected_utility_release"] < 0


def test_scripted_outcomes_preserve_every_citizen_and_reject_invalid_coalition():
    game = witness()
    for coalition in initially_acceptable_coalitions(game):
        for shocked in (False, True):
            for release_right in (False, True):
                result = scripted_outcome(game, coalition, shocked=shocked,
                                          release_right=release_right)
                assert len(result.citizen_utilities) == 7
                assert all(len(district) == 9 for district in result.citizen_utilities)
                assert tuple(map(sum, result.citizen_utilities)) == result.district_utilities
    with pytest.raises(ValueError):
        scripted_outcome(game, (0, 3, 4, 6), shocked=True, release_right=True)
