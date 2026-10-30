import copy
from paper3 import agenda_rights as game
from analysis.paper3_agenda_fidelity import final_vote_fidelity


def events(cards):
    return [dict(stage='locked_proposal',action=dict(policy_id='p3')),
        dict(stage='amendment',action=dict(policy_id='p3')),
        dict(stage='pairwise',ballots={r:'p3' for r in game.ROLES}),
        dict(stage='leader_selection',action=dict(policy_id='p3')),
        dict(stage='ratification',cards=cards)]


def test_majority_imposed_loss_is_not_own_agent_betrayal():
    profile=game.profiles()[0]
    cards={r:{'p3':profile['utilities'][r]['p3']>0} for r in game.ROLES}
    report=final_vote_fidelity(profile,'D',events(cards))
    assert report['resolution']['ratification_yes']==5
    assert report['harmed_principals']==2
    assert report['strictly_harmful_own_votes']==0
    assert not any(r['pivotal'] for r in report['actors'].values())


def test_pivotal_own_error_vs_nonpivotal_inconsistent_card():
    profile=game.profiles()[0]
    # Synthetic utility-table unit fixture: all prefer p3 to q; r0 could supply
    # the fourth yes. Its no is costly; r4's yes is not pivotal at three yes votes.
    profile=copy.deepcopy(profile)
    for row in profile['utilities'].values():
        row['p3']=10
    cards={r:{'p3':r in ('r4','r5','r6')} for r in game.ROLES}
    report=final_vote_fidelity(profile,'B',events(cards))
    assert report['resolution']['outcome']=='q'
    assert report['actors']['r0']['pivotal'] and report['actors']['r0']['unilateral_vote_flip_gain']==10
    assert not report['actors']['r4']['pivotal']
    cards={r:{'p3':r!='r0'} for r in game.ROLES}
    report=final_vote_fidelity(profile,'B',events(cards))
    assert report['actors']['r0']['selected_vote_sign_consistent'] is False
    assert not report['actors']['r0']['strictly_harmful_own_vote']
