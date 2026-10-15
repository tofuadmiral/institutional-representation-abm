"""Small fabricated report fixtures; no API calls, no empirical claims."""
import pytest
from analysis.paper3_disclosure_validation_report import interval, render


def fixtures():
    seeds = [1, 2, 3, 4]
    protocol = dict(frame=dict(seeds=seeds, selection=dict(positive=[1, 3], zero_control=[2, 4]),
        predictions={str(s):dict(theory=dict(leader_value_of_information_normalized_exact='1/4' if s%2 else '0')) for s in seeds}))
    rows = []
    for seed in seeds:
        done = seed in (1, 2)
        rows.append(dict(seed=seed, stratum='positive' if seed%2 else 'zero_control', complete=done,
            outcomes={'early':dict(D='q', B='p1'), 'late':dict(D='q', B='p1')} if done else {'early':{}, 'late':{}},
            information_benefit_bounds_exact=['1/4', '1/4'] if done else ['-1', '1'],
            interaction_bounds=dict(mean_regret=[0., 0.] if done else [-2., 2.],
                                    leader_advantage=[0., 0.] if done else [-4., 4.])) )
    return dict(integrity_errors=[], calls=190, accounted_usd='0.25', cumulative_additional_usd='2.00',
                complete_profiles=2, profiles=rows), protocol


def test_all_assigned_denominators_and_exact_missingness_bounds():
    report, protocol = fixtures()
    text = render(report, protocol)
    assert '| positive | 1 / 2 | [-3/8, 5/8] |' in text
    assert '| zero_control | 1 / 2 | [-3/8, 5/8] |' in text
    assert '| 3 | positive | no | missing | missing | missing | missing |' in text
    assert '| 1 | positive | yes | q | p1 | q | p1 |' in text
    assert '| 3 | 1/4 | [-1, 1] | [-5/4, 3/4] |' in text
    assert 'not independent experimental units' in text and 'not confidence intervals' in text


@pytest.mark.parametrize('failure', ['audit', 'missing', 'order', 'duplicate', 'stratum', 'count', 'cells'])
def test_refuse_invalid_or_success_only_readout(failure):
    report, protocol = fixtures()
    if failure == 'audit': report['integrity_errors'] = ['fabricated integrity error']
    elif failure == 'missing': report['profiles'].pop()
    elif failure == 'order': report['profiles'].reverse()
    elif failure == 'duplicate': protocol['frame']['seeds'][-1] = 1
    elif failure == 'stratum': report['profiles'][0]['stratum'] = 'zero_control'
    elif failure == 'count': report['complete_profiles'] = 4
    elif failure == 'cells': report['profiles'][0]['outcomes']['late'].pop('B')
    with pytest.raises(ValueError): render(report, protocol)


def test_interval_does_not_round_or_hide_negative_bounds():
    assert interval(['1/11', '1/11']) == '1/11'
    assert interval(['-1/11', '1/11']) == '[-1/11, 1/11]'
    with pytest.raises(ValueError): interval([1, -1])
