import copy
import pytest
from paper3 import agenda_rights as game
from paper3 import agenda_benchmarks as bench


def test_selected_fixture_reproduces_prior_analytical_predictions():
    profile=game.profiles()[0]
    d=bench.benchmark(profile,'D'); b=bench.benchmark(profile,'B')
    assert (d['proposal'],d['amendment'],d['resolution']['outcome'])==('p3','p3','p3')
    assert (b['proposal'],b['amendment'],b['resolution']['outcome'])==('p1','p1','p1')
    myopic=bench.benchmark(profile,'B',lookahead=False)
    assert (myopic['proposal'],myopic['amendment'],myopic['resolution']['outcome'])==('p3','p6','p6')
    assert b['enacted_metrics']['mean_regret']==pytest.approx(.18411345858364242)


def test_common_interest_control_and_display_order_invariance():
    for profile in game.profiles():
        reversed_profile=copy.deepcopy(profile)
        reversed_profile['catalog'].reverse()
        assert bench.certificate(profile)==bench.certificate(reversed_profile)
    for arm in game.ARMS:
        result=bench.benchmark(game.profiles()[1],arm)
        assert result['proposal']==result['amendment']==result['resolution']['outcome']=='p7'


def test_viability_and_challenge_certificate_independently_counted():
    for profile in game.profiles()+[bench.generated_profile(s) for s in range(1000000,1000004)]:
        result=bench.certificate(profile)
        for p in bench.policy_ids(profile):
            votes=sum(profile['utilities'][r][p]>0 for r in game.ROLES)
            assert bench.continuation(profile,p)==(p if votes>=4 else 'q')
        for row in result['sponsor_beneficial_majority_challenges']:
            p,a=row['proposal'],row['amendment']
            assert p in result['viable'] and a in result['viable']
            assert len(row['supporters'])>=4
            assert profile['utilities'][profile['leader']][a]<profile['utilities'][profile['leader']][p]
            assert profile['utilities'][profile['sponsor']][a]>profile['utilities'][profile['sponsor']][p]
        assert result['pareto_policies'] and result['mean_regret_optima']


def test_no_lookahead_claim_of_equilibrium_and_deterministic_generator():
    profile=bench.generated_profile(1000000)
    assert profile==bench.generated_profile(1000000)
    assert profile!=bench.generated_profile(1000001)
    assert profile['leader']!=profile['sponsor']
    assert len({tuple(p['coordinates']) for p in profile['catalog']})==8
    assert len({tuple(p['ideal']) for p in profile['principals'].values()})==7
    for actor in game.ROLES:
        principal=profile['principals'][actor]
        for p in profile['catalog']:
            loss=sum(w*(a-b)**2 for w,a,b in zip(principal['weights'],p['coordinates'],principal['ideal']))
            assert profile['losses'][actor][p['policy_id']]==loss


def test_status_quo_retention_is_not_false_negative_control():
    profile=bench.generated_profile(1001006)
    result=bench.certificate(profile)
    assert not result['sponsor_beneficial_majority_challenges']
    assert result['sponsor_beneficial_continuation_challenges']
    assert any(c['proposal_continuation']=='q' for c in result['sponsor_beneficial_continuation_challenges'])
    d=result['lookahead']['D']['resolution']['outcome']
    b=result['lookahead']['B']['resolution']['outcome']
    assert d=='q' and b=='p5'
    assert profile['utilities'][profile['leader']][b]<0
