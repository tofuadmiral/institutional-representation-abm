"""Instrument checks using fabricated agents, never an API/model."""
import copy
import json
from fractions import Fraction

import pytest

from paper3 import agenda_disclosure_canonical as instrument
from paper3 import agenda_rights as game
from paper3 import agenda_benchmarks as bench
from paper3.agenda_weak_preferences import certificate
from paper3 import disclosure_identification_design as design
from paper3.source_closure import closure


def decode(messages):
    return json.loads(messages[1]['content'].split('\n',1)[0])


def scripted(messages, position):
    c=decode(messages);p=c['profile'];events=c['official_events'];stage=c['stage']
    e={v['stage']:v for v in events}
    condition=('late' if 'not yet decided' in messages[0]['content'] else
               'D' if "leader's selection determines" in messages[0]['content'] else 'B')
    predictions=certificate(p)['predictions']
    ids=c.get('candidate_policy_ids')
    u=p['utilities'][c['representative']]
    if stage in ('opening','responses','locked_proposal'):
        action=dict(policy_id=predictions['own_best'][condition][0],message='public argument')
    elif stage=='amendment':
        arm=e['authority_in_force']['rule']
        proposal=e['locked_proposal']['action']['policy_id']
        action=dict(policy_id=bench.sponsor_response(p,arm,proposal)['amendment'],message='amendment')
    elif stage=='ratification':
        action=dict(votes={pid:u[pid]>0 for pid in ids})
    else:
        best=max(ids,key=lambda pid:u[bench.continuation(p,pid)])
        action=dict(policy_id=best)
        if stage!='pairwise':action['message']='selection'
    return json.dumps(action)


def test_rules_barrier_common_event_and_sealed_stages():
    p=bench.generated_profile(1006576);seen={}
    def capture(label):
        seen[label]=[]
        def ask(messages,position):
            seen[label].append((copy.deepcopy(messages),position))
            return scripted(messages,position)
        return ask
    early={a:instrument.run_early(p,a,capture('early-'+a)) for a in 'DB'}
    late=instrument.run_late(p,capture('late'),'DB')
    assert all(e['status']=='completed' and len(e['actions'])==25 for e in early.values())
    assert late['status']=='completed' and len(seen['late'])==41
    assert sum(map(len,seen.values()))==91
    for messages,pos in seen['late'][:9]:
        assert 'not yet decided' in messages[0]['content'] and 'probability 1/2 each' in messages[0]['content']
        assert not any(e['stage']=='authority_in_force' for e in decode(messages)['official_events'])
        assert pos<9
    for a,offset in (('D',9),('B',25)):
        for (m,pos),(em,epos) in zip(seen['late'][offset:offset+16],seen['early-'+a][9:]):
            assert pos==epos and m[0]==em[0]
            assert 'not yet decided' not in m[0]['content']
            for messages in (m,em):
                ev=decode(messages)['official_events']
                assert ev[3]==dict(stage='authority_in_force',rule=a)
                assert ev[2]['stage']=='locked_proposal'
    for records in seen.values():
        for m,pos in records:
            c=decode(m)
            if c['stage'] in ('responses','pairwise','ratification'):
                assert c['stage'] not in [e['stage'] for e in c['official_events']]


def test_cloned_late_prefix_and_branch_order_invariance():
    p=bench.generated_profile(1006576)
    left=instrument.run_late(p,scripted,'DB');right=instrument.run_late(p,scripted,'BD')
    assert left['prefix_events']==right['prefix_events']
    assert left['branches']==right['branches']
    snapshot=copy.deepcopy(left['prefix_events'])
    left['branches']['D']['events'][0]['action']['message']='branch-only mutation'
    left['branches']['D']['actions'][0]['action']['policy_id']='p7'
    assert left['prefix_events']==snapshot
    assert left['branches']['B']['events'][:3]==snapshot
    assert left['branches']['B']['actions'][:9]==left['prefix_actions']


@pytest.mark.parametrize('profile_index',[0,1])
def test_scripted_predictions_and_stage_lengths(profile_index):
    p=design.frame()['profiles'][profile_index]
    e={a:instrument.run_early(p,a,scripted) for a in 'DB'}
    l=instrument.run_late(p,scripted,'DB')
    outcomes={'early':{a:e[a]['resolution']['outcome'] for a in 'DB'},
              'late':{a:l['branches'][a]['resolution']['outcome'] for a in 'DB'}}
    assert outcomes==({'early':dict(D='p2',B='q'),'late':dict(D='q',B='q')} if profile_index==0
                      else {'early':dict(D='p3',B='p3'),'late':dict(D='p3',B='p3')})
    u=p['utilities'][p['leader']]
    value=Fraction(sum(u[outcomes['early'][a]]-u[outcomes['late'][a]] for a in 'DB'),
                   2*(max(u.values())-min(u.values())))
    assert value==(Fraction(3,38) if profile_index==0 else 0)
    assert len(l['prefix_actions'])==9
    assert all(len(v['actions'])==25 for v in l['branches'].values())


def test_failed_prefix_does_not_spawn_branches():
    calls=[]
    def bad(messages,position):calls.append(position);return '{}'
    out=instrument.run_late(bench.generated_profile(1006576),bad,'DB')
    assert calls==[0] and out['status']=='failed'
    assert all(v['status']=='failed' for v in out['branches'].values())


def test_failure_in_one_late_branch_does_not_mutate_other():
    def ask(messages,position):
        if position==9 and decode(messages)['official_events'][3]['rule']=='D':return '{}'
        return scripted(messages,position)
    out=instrument.run_late(bench.generated_profile(1006576),ask,'DB')
    assert out['status']=='partial' and out['branches']['D']['status']=='failed'
    assert out['branches']['B']['status']=='completed'
    assert len(out['branches']['B']['actions'])==25


def test_source_closure_relative_and_absolute_imports(tmp_path):
    (tmp_path/'pkg').mkdir()
    (tmp_path/'pkg/__init__.py').write_text('from . import leaf\n')
    (tmp_path/'pkg/main.py').write_text('from .leaf import x\nimport json\n')
    (tmp_path/'pkg/leaf.py').write_text('x=1\n')
    found=closure(tmp_path,[tmp_path/'pkg/main.py'])
    assert {p.name for p in found}=={'main.py','leaf.py','__init__.py'}
    with pytest.raises(ValueError):closure(tmp_path,[tmp_path/'missing.py'])
