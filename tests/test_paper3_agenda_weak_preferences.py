"""No inference: fabricated utility tables and exact game enumeration."""
import copy
from itertools import product

import pytest

from paper3 import agenda_benchmarks as bench
from paper3.agenda_weak_preferences import (
    ratification_outcomes, selector_outcomes, best_outcomes, certificate, scan)
from paper3.agenda_invariance import transform_profile


def test_sponsor_union_equals_brute_force_all_fixed_tie_resolutions():
    possibilities = {'a': {'p', 'q'}, 'b': {'p', 'r'}, 'c': {'s'}}
    for values in product(range(3), repeat=4):
        u = dict(zip(('p', 'q', 'r', 's'), values))
        union = set()
        for outcomes in product(*possibilities.values()):
            maximum = max(u[o] for o in outcomes)
            union.update(o for o in outcomes if u[o] == maximum)
        assert best_outcomes(possibilities, u) == union


def test_only_pivotal_indifference_makes_ratification_ambiguous():
    p = copy.deepcopy(bench.generated_profile(1005025))
    assert ratification_outcomes(p, 'p4') == {'p4'}  # Utility-zero r3 is nonpivotal.
    for r, v in zip(p['utilities'], [1, 1, 1, 0, -1, -1, -1]):
        p['utilities'][r]['p4'] = v
    assert ratification_outcomes(p, 'p4') == {'p4', 'q'}
    with pytest.raises(ValueError, match='ratification ambiguity'):
        selector_outcomes(p, 'B', 'p4', 'q')
    assert ratification_outcomes(p, 'q') == {'q'}


def test_selector_sets_equal_exhaustive_indifferent_ballots_and_leader_choices():
    # Fabricated rankings with both policies strictly ratifiable.
    for deltas in product((-1, 0, 1), repeat=7):
        p = {'status_quo': 'q', 'leader': 'r0', 'utilities': {
            f'r{i}': {'q': 0, 'p1': 5, 'p2': 5 + delta} for i, delta in enumerate(deltas)}}
        choices = [('p2',) if d > 0 else ('p1',) if d < 0 else ('p1', 'p2') for d in deltas]
        expected = {'p2' if ballots.count('p2') >= 4 else 'p1' for ballots in product(*choices)}
        assert selector_outcomes(p, 'B', 'p1', 'p2') == expected
        assert selector_outcomes(p, 'D', 'p1', 'p2') == set(choices[0])


@pytest.mark.parametrize('seed', [1005025, 1005072])
def test_original_counterexamples_remain_not_point_identified(seed):
    assert not certificate(bench.generated_profile(seed))['identified']


def test_unknown_rule_rejected_and_scan_retains_every_seed():
    with pytest.raises(ValueError, match='unknown authority'):
        selector_outcomes(bench.generated_profile(1005025), 'X', 'q', 'p1')
    report = scan(1006000, 3)
    assert [r['seed'] for r in report['rows']] == [1006000, 1006001, 1006002]
    assert sum(report['counts'].values()) == 3
    with pytest.raises(ValueError):
        scan(0, 0)


def test_certificate_is_label_invariant():
    p = bench.generated_profile(1006000)
    pm = {'q': 'q', **{f'p{i}': f'p{8-i}' for i in range(1, 8)}}
    rm = {f'r{i}': f'r{6-i}' for i in range(7)}
    a, b = certificate(p), certificate(transform_profile(p, policy_mapping=pm, role_mapping=rm))
    assert a['identified'] == b['identified']
    assert a['stratum'] == b['stratum']
    assert {pm[p] for p in a['ratification_ambiguous']} == set(b['ratification_ambiguous'])
    if a['identified']:
        assert a['predictions']['normalized_information_value_exact'] == b['predictions']['normalized_information_value_exact']


def test_fixed_frame_separating_witness_has_set_valued_proposal_prediction():
    c = certificate(bench.generated_profile(1006576))
    assert c['identified'] and c['stratum'] == 'positive_separating'
    assert c['predictions']['normalized_information_value_exact'] == '3/38'
    assert c['predictions']['own_best']['D'] == ['p2']
    assert set(c['predictions']['own_best']['B']) == {'q', 'p1', 'p3', 'p4', 'p5', 'p7'}
    assert set(c['predictions']['group_best']['B']) == {'p2', 'p6'}
    assert c['sponsor_best_outcomes']['B']['p2'] == ['p6']
    assert c['sponsor_best_outcomes']['B']['q'] == ['q']


def test_first_control_has_same_own_optimum_under_every_disclosure_condition():
    c = certificate(bench.generated_profile(1006006))
    assert c['identified'] and c['stratum'] == 'zero_control'
    assert c['predictions']['normalized_information_value_exact'] == '0'
    assert all(proposals == ['p3'] for proposals in c['predictions']['own_best'].values())
