from fractions import Fraction
import pytest
from paper3 import agenda_rights as game
from paper3.agenda_benchmarks import generated_profile
from paper3.agenda_disclosure_benchmarks import disclosure_benchmark
from paper3.agenda_invariance import transform_profile


def test_selected_conflict_requires_choosing_before_learning_rule():
    result = disclosure_benchmark(game.profiles()[0])
    assert result['late_own_best_proposals'] == ['p1']
    assert result['early_own_best_proposals'] == {'D':['p3','p5'],'B':['p1']}
    assert result['full_information_own_utility_exact'] == '197/2'
    assert result['best_lottery_own_utility_exact'] == '90'
    assert result['leader_value_of_information_exact'] == '17/2'
    assert result['leader_value_of_information_normalized_exact'] == '17/214'
    assert result['continuation_outcomes']['D']['p1'] == 'p1'
    assert result['continuation_outcomes']['B']['p1'] == 'p1'


def test_information_value_nonnegative_and_positive_iff_optimal_sets_disjoint():
    for profile in game.profiles()+[generated_profile(2007000+i) for i in range(32)]:
        result = disclosure_benchmark(profile,Fraction(1,3))
        value = Fraction(result['leader_value_of_information_exact'])
        intersection = set(result['early_own_best_proposals']['D']) & set(result['early_own_best_proposals']['B'])
        assert value >= 0
        assert (value == 0) == bool(intersection)
        expected = {p:Fraction(v) for p,v in result['late_expected_own_utility_exact'].items()}
        assert result['late_own_best_proposals'] == [p for p,v in expected.items() if v==max(expected.values())]


@pytest.mark.parametrize('probability,arm',[(0,'D'),(1,'B')])
def test_known_rule_has_no_information_value(probability,arm):
    result = disclosure_benchmark(game.profiles()[0],probability)
    assert result['leader_value_of_information_exact'] == '0'
    assert result['late_own_best_proposals'] == result['early_own_best_proposals'][arm]


def test_utility_units_do_not_change_lottery_choice_or_normalized_group_scores():
    profile = game.profiles()[0]
    scales = {r:i+2 for i,r in enumerate(game.ROLES)}
    before = disclosure_benchmark(profile)
    after = disclosure_benchmark(transform_profile(profile,utility_scales=scales))
    for key in ('early_own_best_proposals','late_own_best_proposals','late_group_best_proposals',
                'late_expected_mean_regret_exact','continuation_outcomes',
                'leader_value_of_information_normalized_exact'):
        assert before[key] == after[key]
    for key in ('leader_value_of_information_exact','full_information_own_utility_exact','best_lottery_own_utility_exact'):
        assert Fraction(after[key]) == Fraction(before[key])*scales[profile['leader']]


@pytest.mark.parametrize('value',[-1,2,Fraction(3,2),0.5,True,'1/2'])
def test_invalid_or_inexact_probability_rejected(value):
    with pytest.raises(ValueError):
        disclosure_benchmark(game.profiles()[0],value)
