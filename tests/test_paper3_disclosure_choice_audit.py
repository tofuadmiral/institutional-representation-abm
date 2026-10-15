import copy
from fractions import Fraction
import json
import pytest
from analysis.paper3_disclosure_choice_audit import (
    sponsor_options, proposal_bounds, lock_report, episode_report, diagnose)
from paper3 import agenda_benchmarks as bench
from paper3 import agenda_rights as game


def fixture(profile, arm, proposal, amendment):
    ids = {proposal, amendment}
    u = profile['utilities']
    pc, ac = [bench.continuation(profile, p) for p in (proposal, amendment)]
    ballots = {r: amendment if u[r][ac] > u[r][pc] else proposal for r in game.ROLES}
    leader = profile['leader']
    choice = amendment if u[leader][ac] > u[leader][pc] else proposal
    cards = {r: {p: u[r][p] > 0 for p in ids} for r in game.ROLES}
    return dict(status='completed', events=[
        dict(stage='locked_proposal', action=dict(policy_id=proposal)),
        dict(stage='amendment', action=dict(policy_id=amendment)),
        dict(stage='pairwise', ballots=ballots),
        dict(stage='leader_selection', action=dict(policy_id=choice)),
        dict(stage='ratification', cards=cards)],
        resolution=game.resolve(profile, arm, proposal, amendment, ballots, choice, cards))


def test_sponsor_tie_is_not_a_suboptimal_choice():
    p = bench.generated_profile(1005025)
    assert set(sponsor_options(p, 'B', 'p6')) == {'p1', 'p2'}
    r = episode_report(p, 'B', fixture(p, 'B', 'p6', 'p2'))
    assert r['sponsor_payoff_maximizing']
    assert r['point_benchmark_outcome'] == 'p1'
    assert r['outcome'] == r['same_pair_scripted_outcome'] == 'p2'


def test_second_tie_has_different_leader_losses():
    p = bench.generated_profile(1005072)
    assert set(sponsor_options(p, 'B', 'q')) == {'p1', 'p5'}
    assert proposal_bounds(p, 'late')['q'] == [Fraction(-87, 2), Fraction(-47, 2)]


def test_early_lock_dominated_under_every_sponsor_tie():
    p = bench.generated_profile(1005025)
    r = lock_report(p, 'B', 'p2')
    assert r['leader_payoff_bounds_exact'] == ['-56', '-56']
    assert r['robust_dominators']['p1']['minimum_gain_exact'] == '41'


def test_lottery_lock_dominated_even_at_optimistic_tie():
    p = bench.generated_profile(1005072)
    r = lock_report(p, 'late', 'q')
    assert r['robust_dominators']['p4']['minimum_gain_exact'] == '5/2'
    assert not lock_report(p, 'late', 'p4')['robust_dominators']


def test_zero_utility_card_is_not_strict_error():
    p = bench.generated_profile(1005025)
    s = fixture(p, 'B', 'p2', 'p4')
    s['events'][-1]['cards']['r3']['p4'] = True
    s['resolution']['ratification_yes'] += 1
    assert not episode_report(p, 'B', s)['card_departures']


def test_off_path_card_error_cannot_change_recorded_outcome():
    p = bench.generated_profile(1005025)
    s = fixture(p, 'D', 'p7', 'p2')
    s['events'][-1]['cards']['r0']['p2'] = False
    row = episode_report(p, 'D', s)['card_departures'][0]
    assert not row['selected'] and row['fixed_history_flip_gain'] == 0


def test_pivotal_card_error_is_distinguished():
    p = copy.deepcopy(bench.generated_profile(1005025))
    s = fixture(p, 'B', 'p2', 'p2')
    cards = {r: {'p2': r in ('r4', 'r5', 'r6')} for r in game.ROLES}
    s['events'][-1]['cards'] = cards
    s['resolution'] = dict(selected='p2', outcome='q', passed=False, ratification_yes=3)
    row = next(r for r in episode_report(p, 'B', s)['card_departures'] if r['actor'] == 'r0')
    assert row['selected'] and row['fixed_history_flip_gain'] == 32


def test_reject_incomplete_episode_bad_resolution_and_live_run(tmp_path):
    p = bench.generated_profile(1005025)
    with pytest.raises(ValueError, match='completed episode'):
        episode_report(p, 'B', {'status': 'failed'})
    s = fixture(p, 'B', 'p2', 'p4')
    s['resolution']['outcome'] = 'q'
    with pytest.raises(ValueError, match='resolution mismatch'):
        episode_report(p, 'B', s)
    with pytest.raises(ValueError, match='unknown disclosure'):
        proposal_bounds(p, 'unknown')
    with pytest.raises(ValueError, match='terminal run'):
        diagnose(tmp_path)


def test_failed_frozen_audit_blocks_diagnostic(tmp_path, monkeypatch):
    from analysis import paper3_disclosure_validation_audit as frozen
    (tmp_path/'sessions').mkdir()
    (tmp_path/'sessions/terminal.json').write_text('{}')
    monkeypatch.setattr(frozen, 'audit', lambda root: {'integrity_errors': ['fabricated test failure']})
    with pytest.raises(ValueError, match='frozen integrity audit failed'):
        diagnose(tmp_path)


def test_incomplete_profile_keeps_observed_lock_without_outcome(tmp_path, monkeypatch):
    from analysis import paper3_disclosure_validation_audit as frozen
    (tmp_path/'sessions').mkdir()
    (tmp_path/'sessions/terminal.json').write_text('{}')
    p = bench.generated_profile(1005009)
    (tmp_path/'manifest.json').write_text(json.dumps({'protocol': {'frame': {
        'profiles': [p], 'seeds': [1005009]}}}))
    sessions = tmp_path/'profile-0/sessions'
    sessions.mkdir(parents=True)
    (sessions/'early-B.json').write_text(json.dumps({'condition': 'early', 'arm': 'B',
        'status': 'failed', 'actions': [{'stage': 'locked_proposal',
                                       'action': {'policy_id': 'p5'}}]}))
    # This fixture tests aggregation, not provenance. The real CLI separately
    # passed the unchanged frozen audit on every assigned profile.
    monkeypatch.setattr(frozen, 'audit', lambda root: {
        'integrity_errors': [], 'profiles': [{'complete': False}]})
    report = diagnose(tmp_path)['profiles'][0]
    assert report['complete'] is False and report['completed_episodes'] == {}
    assert report['locks']['early-B']['robust_dominators']['p2']['minimum_gain_exact'] == '60'
