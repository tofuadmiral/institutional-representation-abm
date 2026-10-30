from fractions import Fraction
import pytest
from paper3.agenda_objective_benchmarks import objective_benchmarks
from paper3 import agenda_benchmarks as bench
from paper3 import agenda_rights as game


def test_selected_case_does_not_false_reject_tied_leader_proposal():
    r=objective_benchmarks(game.profiles()[0])
    assert r['arms']['D']['own_best_proposals']==['p3','p5']
    assert r['arms']['B']['own_best_proposals']==['p1']
    assert r['own_optimal_sets_disjoint']
    assert r['own_vs_group_disjoint']=={'D':True,'B':False}


def test_fresh_frame_retains_all_four_equal_terminal_payoff_proposals():
    r=objective_benchmarks(bench.generated_profile(1002005))
    assert r['arms']['B']['own_best_proposals']==['p1','p3','p4','p5']
    assert r['own_optimal_sets_disjoint']
    assert not r['own_vs_group_disjoint']['B']


def test_fresh_case_distinguishes_own_and_group_continuation_objectives():
    r=objective_benchmarks(bench.generated_profile(1002003))
    assert r['own_vs_group_disjoint']['B']
    assert r['arms']['B']['group_best_proposals']==['p4']
    assert 'p4' not in r['arms']['B']['own_best_proposals']


def test_exact_group_score_matches_primary_metric_and_point_benchmark_in_sets():
    for seed in range(1002000,1002008):
        p=bench.generated_profile(seed);r=objective_benchmarks(p)
        for arm,a in r['arms'].items():
            assert bench.benchmark(p,arm)['proposal'] in a['own_best_proposals']
            for proposal,outcome in a['continuation_outcomes'].items():
                assert float(Fraction(a['continuation_mean_regret_exact'][proposal]))==pytest.approx(game.metrics(p,outcome)['mean_regret'])
