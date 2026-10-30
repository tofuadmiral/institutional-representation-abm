"""Theory-only checks. No provider calls, model outputs, or credentials."""
import copy
from fractions import Fraction

import pytest

from paper3 import agenda_benchmarks as bench
from paper3.agenda_disclosure_benchmarks import disclosure_benchmark
from paper3.agenda_identification import certificate, scan
from paper3.agenda_invariance import transform_profile


@pytest.mark.parametrize('seed,proposal,outcomes', [
    (1005025, 'p6', ['p1', 'p2']), (1005072, 'q', ['p1', 'p5'])])
def test_known_sponsor_indifference_has_no_identified_point_value(seed, proposal, outcomes):
    c = certificate(bench.generated_profile(seed))
    assert c['sponsor_best']['B'][proposal]['outcomes'] == outcomes
    assert not c['unique_sponsor_best_outcomes']
    assert c['stratum'] is None
    assert 'normalized_information_value_exact' not in c


def test_duplicate_amendments_with_same_outcome_are_not_ambiguity():
    from paper3.agenda_rights import profiles
    c = certificate(profiles()[1])
    assert c['unique_sponsor_best_outcomes']
    assert any(len(v['amendments']) > 1 for row in c['sponsor_best'].values() for v in row.values())


def test_strict_screen_reports_zero_cards_and_distinct_outcome_ties():
    c = certificate(bench.generated_profile(1005025))
    assert c['zero_utility_non_q_cards']['r3'] == ['p4']
    assert ['p1', 'p2'] in c['indifferent_continuation_pairs']['r0']
    assert not c['strict_downstream_preferences']


def test_unique_values_agree_with_old_script_without_discarding_proposal_ties():
    count = 0
    for seed in range(1006000, 1006030):
        p = bench.generated_profile(seed)
        c = certificate(p)
        if not c['unique_sponsor_best_outcomes']:
            continue
        old = disclosure_benchmark(p)
        assert c['normalized_information_value_exact'] == old['leader_value_of_information_normalized_exact']
        assert c['own_best']['late'] == old['late_own_best_proposals']
        assert Fraction(c['normalized_information_value_exact']) >= 0
        count += 1
    assert count > 0


def test_certificate_does_not_mutate_profile_and_is_label_invariant():
    p = bench.generated_profile(1005025)
    saved = copy.deepcopy(p)
    pm = {'q': 'q', **{f'p{i}': f'p{8-i}' for i in range(1, 8)}}
    rm = {f'r{i}': f'r{6-i}' for i in range(7)}
    transformed = transform_profile(p, policy_mapping=pm, role_mapping=rm)
    a, b = certificate(p), certificate(transformed)
    assert p == saved
    assert a['stratum'] == b['stratum']
    assert a['unique_sponsor_best_outcomes'] == b['unique_sponsor_best_outcomes']
    for arm, row in a['sponsor_best'].items():
        for policy, best in row.items():
            assert {pm[o] for o in best['outcomes']} == set(b['sponsor_best'][arm][pm[policy]]['outcomes'])


def test_scan_retains_ineligible_seeds_and_rejects_bad_ranges():
    result = scan(1006000, 3)
    assert [r['seed'] for r in result['rows']] == [1006000, 1006001, 1006002]
    assert sum(result['counts'].values()) == 3
    assert scan(1006000, 3) == result
    for start, count in [(-1, 2), (0, 0), (1.5, 2), (True, 2), (0, True)]:
        with pytest.raises(ValueError):
            scan(start, count)
