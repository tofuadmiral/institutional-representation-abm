import copy
from fractions import Fraction
import pytest
from paper3 import agenda_rights as game
from paper3.agenda_invariance import transform_profile, map_resolution_inputs


def mappings():
    return ({r: game.ROLES[(i+2) % 7] for i, r in enumerate(game.ROLES)},
            dict(q='q', **{f'p{i}': f'p{8-i}' for i in range(1, 8)}))


def test_identity_and_no_mutation():
    original = game.profiles()[0]
    saved = copy.deepcopy(original)
    result = transform_profile(original)
    assert result == original and result is not original
    result['principals']['r0']['weights'][0] = 999
    assert original == saved


def test_scaled_spatial_numbers_and_normalized_metrics_remain_consistent():
    original = game.profiles()[0]
    rm, pm = mappings()
    scales = {r: 10**i for i, r in enumerate(game.ROLES)}
    transformed = transform_profile(original, role_mapping=rm, policy_mapping=pm,
        utility_scales=scales, catalog_order=['q']+[f'p{i}' for i in range(1,8)])
    for r in game.ROLES:
        principal = transformed['principals'][rm[r]]
        for item in transformed['catalog']:
            loss = sum(w*(x-z)**2 for w,x,z in zip(principal['weights'],
                item['coordinates'], principal['ideal']))
            assert transformed['losses'][rm[r]][item['policy_id']] == loss
        for p in original['utilities'][r]:
            assert transformed['utilities'][rm[r]][pm[p]] == original['utilities'][r][p]*scales[r]
            assert transformed['utilities'][rm[r]][pm[p]] == transformed['losses'][rm[r]]['q']-transformed['losses'][rm[r]][pm[p]]
    for p in original['utilities']['r0']:
        before, after = game.metrics(original,p), game.metrics(transformed,pm[p])
        for metric in ('mean_regret','worst_regret','leader_advantage'):
            assert after[metric] == pytest.approx(before[metric])
        for metric in ('sincere_support','principals_worse_than_status_quo'):
            assert after[metric] == before[metric]
        for r in game.ROLES:
            assert after['regret'][rm[r]] == before['regret'][r]
            assert after['unweighted_l2'][rm[r]] == before['unweighted_l2'][r]


def test_positive_scaling_preserves_lottery_preferences():
    original = game.profiles()[0]
    scales = {r: i+1 for i,r in enumerate(game.ROLES)}
    transformed = transform_profile(original, utility_scales=scales)
    for r in game.ROLES:
        for denominator in range(1,8):
            probability = Fraction(1,denominator)
            old = probability*original['utilities'][r]['p1']+(1-probability)*original['utilities'][r]['p6']-original['utilities'][r]['p3']
            new = probability*transformed['utilities'][r]['p1']+(1-probability)*transformed['utilities'][r]['p6']-transformed['utilities'][r]['p3']
            assert new == old*scales[r]


def test_scaling_preserves_scripted_own_and_normalized_group_optima():
    from paper3.agenda_benchmarks import generated_profile
    from paper3.agenda_objective_benchmarks import objective_benchmarks
    for profile in game.profiles() + [generated_profile(2006000+i) for i in range(10)]:
        scales = {r: i+1 for i,r in enumerate(game.ROLES)}
        changed = transform_profile(profile, utility_scales=scales)
        before, after = objective_benchmarks(profile), objective_benchmarks(changed)
        assert before['own_optimal_sets_disjoint'] == after['own_optimal_sets_disjoint']
        assert before['own_vs_group_disjoint'] == after['own_vs_group_disjoint']
        for arm in game.ARMS:
            for key in ('own_best_proposals','group_best_proposals',
                        'continuation_mean_regret_exact','continuation_outcomes','sponsor_amendments'):
                assert before['arms'][arm][key] == after['arms'][arm][key]
            assert after['arms'][arm]['continuation_own_utilities'] == {
                p:v*scales[profile['leader']] for p,v in before['arms'][arm]['continuation_own_utilities'].items()}


def test_resolution_isomorphic_for_every_candidate_and_majority_size():
    original = game.profiles()[0]
    rm,pm = mappings()
    transformed = transform_profile(original, role_mapping=rm, policy_mapping=pm)
    ids = list(pm)
    for proposal in ids:
        for amendment in ids:
            for n in range(8):
                ballots = {r: amendment if i<n else proposal for i,r in enumerate(game.ROLES)}
                cards = {r:{p:original['utilities'][r][p]>0 for p in {proposal,amendment}} for r in game.ROLES}
                for choice in {proposal,amendment}:
                    mapped = map_resolution_inputs(proposal,amendment,ballots,choice,cards,rm,pm)
                    for arm in game.ARMS:
                        before = game.resolve(original,arm,proposal,amendment,ballots,choice,cards)
                        after = game.resolve(transformed,arm,**mapped)
                        assert after == dict(before,selected=pm[before['selected']],outcome=pm[before['outcome']])


@pytest.mark.parametrize('kwargs',[
    {'utility_scales':{r:0 for r in game.ROLES}},
    {'utility_scales':{r:True for r in game.ROLES}},
    {'utility_scales':{'r0':2}},
    {'role_mapping':{r:'r0' for r in game.ROLES}},
    {'policy_mapping':dict(q='p1',p1='q',**{f'p{i}':f'p{i}' for i in range(2,8)})},
    {'catalog_order':['q']*8},
])
def test_rejects_non_isomorphic_transforms(kwargs):
    with pytest.raises(ValueError):
        transform_profile(game.profiles()[0],**kwargs)
