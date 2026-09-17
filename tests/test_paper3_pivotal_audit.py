import json

from analysis.paper3_pivotal_memory_audit import audit


def test_audit_keeps_failures_and_does_not_impute_payoffs(tmp_path):
    """Synthetic scorer unit test, not experiment evidence."""
    (tmp_path / 'sessions').mkdir()
    cases = []
    for view in ('transcript', 'event_index', 'registry'):
        expected = dict(principal_id=0, current_project_utility=-3, obligation_due=False, vote=False)
        cases.append(dict(name=view, base_case='fixture', profile_seed=1, view=view, expected=expected))
        if view == 'event_index':
            result = dict(status='failed', error='unit fixture timeout')
        else:
            result = dict(status='completed', reply={**expected, 'vote': view == 'transcript'})
        (tmp_path / 'sessions' / (view + '.json')).write_text(json.dumps(result))
    (tmp_path / 'manifest.json').write_text(json.dumps(dict(protocol=dict(cases=cases))))
    report = audit(tmp_path)
    assert report['views']['transcript']['harmful_unbound_yes'] == 1
    assert report['views']['registry']['action_error'] == 0
    assert report['views']['event_index']['valid'] == 0
    assert report['views']['event_index']['action_error'] == 1
    assert report['cases']['fixture']['event_index']['marginal_payoff'] is None
    assert report['paired_action_contrasts']['transcript']['registry_repairs'] == 1
    assert report['paired_action_contrasts']['event_index']['registry_repairs'] == 1
