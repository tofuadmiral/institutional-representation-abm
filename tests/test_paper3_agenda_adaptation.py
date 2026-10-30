import copy
import json
import pytest
from paper3 import agenda_rights as game
from analysis.paper3_agenda_adaptation import paired_readout


def episode(arm, proposal='p3'):
    profile=game.profiles()[0]
    def ask(messages):
        c=json.loads(messages[-1]['content'].split('\n',1)[0])
        role, stage=c['representative'],c['stage']
        if stage=='ratification':
            value={'votes':{p:profile['utilities'][role][p]>0 for p in c['candidate_policy_ids']}}
        elif stage=='pairwise':
            value={'policy_id':max(c['candidate_policy_ids'],key=lambda p:profile['utilities'][role][p])}
        else:
            value={'policy_id':'p6' if stage=='amendment' else proposal,'message':'fixture'}
        return json.dumps(value)
    return dict(game.run_episode(profile,arm,ask),profile=profile,arm=arm)


def test_identical_actions_can_change_outcomes_without_anticipation():
    pair={a:episode(a) for a in game.ARMS}
    assert pair['D']['actions']==pair['B']['actions']
    report=paired_readout(pair)
    assert report['complete_pair']
    assert report['primary_endpoints']['locked_leader_advantage_B_minus_D']==0
    assert report['enacted_B_minus_D']['before']=='p3'
    assert report['enacted_B_minus_D']['after']=='p6'
    assert report['primary_endpoints']['enacted_mean_regret_B_minus_D']<0
    for arm in game.ARMS:
        assert report['same_history_selector_replays'][arm]['selector_only_B_minus_D']==report['enacted_B_minus_D']


def test_distributional_changes_need_not_be_pareto_improvement():
    report=paired_readout({'D':episode('D','p5'),'B':episode('B')})
    delta=report['enacted_B_minus_D']
    assert delta['mean_regret_change']<0
    assert delta['principals_gaining']==2 and delta['principals_losing']==5
    assert report['primary_endpoints']['locked_leader_advantage_B_minus_D']>0


def test_incomplete_pairs_and_tampered_outcomes_not_invented():
    pair={a:episode(a) for a in game.ARMS}
    failed=copy.deepcopy(pair)
    failed['B']={'arm':'B','profile':pair['B']['profile'],'status':'failed'}
    result=paired_readout(failed)
    assert not result['complete_pair'] and 'primary_endpoints' not in result
    with pytest.raises(ValueError,match='both assigned'):
        paired_readout({'D':pair['D']})
    wrong=copy.deepcopy(pair);wrong['B']['resolution']['outcome']='q'
    with pytest.raises(ValueError,match='disagrees'):
        paired_readout(wrong)
    wrong=copy.deepcopy(pair);wrong['B']['profile']['leader']='r2'
    with pytest.raises(ValueError,match='mismatched'):
        paired_readout(wrong)
