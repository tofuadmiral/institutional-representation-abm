import json
from decimal import Decimal
import sys
import pytest
from experiments import paper3_deepseek_fresh_profiles as study
from analysis.paper3_deepseek_fresh_profiles_audit import audit
from paper3.audit_runtime import PilotStore

REAL_PREREQUISITE=study.prerequisite


def prerequisite_fixture():
    return dict(terminal={'test_fixture':True},protocol_hash='offline-fixture',prior_conservative_usd='0.2')


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    monkeypatch.setattr(study,'prerequisite',prerequisite_fixture)
    study.configure(0)
    yield
    study.configure(0)


def transport(text,secret):
    request=json.loads(text)
    c=json.loads(request['messages'][-1]['content'].split('\n',1)[0])
    stage,profile,role=c['stage'],c['profile'],c['representative']
    available=c.get('candidate_policy_ids',[p['policy_id'] for p in profile['catalog']])
    if stage=='ratification':
        answer={'votes':{p:profile['utilities'][role][p]>0 for p in available}}
    else:
        answer={'policy_id':available[0]}
        if stage!='pairwise':answer['message']='fixture'
    return 200,json.dumps(dict(model=study.MODEL,provider=study.PROVIDER_NAME,
        usage=dict(prompt_tokens=100,completion_tokens=6000,cost=.0024,
            completion_tokens_details=dict(reasoning_tokens=5950)),
        choices=[dict(finish_reason='stop',message=dict(content=json.dumps(answer),reasoning='fixture'))])),None


def launch(root,monkeypatch,fn=transport,index=0):
    path=root/f'profile-{index}'
    monkeypatch.setattr(study,'transmit',fn)
    monkeypatch.setattr(study,'read_key',lambda:'TEST_SECRET_NOT_REAL')
    monkeypatch.setattr(sys,'argv',['test','--output',str(path),'--index',str(index)])
    study.main()
    return audit(path)


def test_fresh_frame_all_indices_budget_and_request_identity():
    from experiments import paper3_deepseek_long_agenda as previous
    for index in range(8):
        study.configure(index)
        p,s=study.prepare()
        assert p['profile_seeds']==list(range(1002000,1002008))
        assert len(p['fresh_frame'])==len(p['analytic_certificates'])==8
        assert p['episodes'][0]['arm']==('D' if index%2==0 else 'B')
        assert {x['seed'] for x in p['episodes']}=={241000+1000*index}
        assert all(x['profile']==p['fresh_frame'][index] for x in p['episodes'])
        spec=p['episodes'][0]
        case=study.case_for(study.game.messages(spec['profile'],spec['arm'],spec['profile']['leader'],'opening',[]),spec['seed'])
        assert study.request_for(case)==previous.request_for(case)
        assert study.LIMITS['episodes']==(50,Decimal('.375'))
    for wrong in (-1,8,True,'0'):
        with pytest.raises(ValueError):study.configure(wrong)


def test_complete_shard_exact_replay_and_no_restart(tmp_path,monkeypatch):
    calls=[]
    def count(text,secret):
        calls.append(text);return transport(text,secret)
    r=launch(tmp_path,monkeypatch,count,index=1)
    assert r['integrity_errors']==[] and r['calls']==50 and r['pairs'][0]['completed']
    study.main()
    assert len(calls)==50


def test_ordinary_cutoff_not_repaired_and_other_arm_runs(tmp_path,monkeypatch):
    count=0
    def fail(text,secret):
        nonlocal count
        count+=1
        status,raw,error=transport(text,secret)
        d=json.loads(raw)
        if count==1:
            d['choices'][0].update(finish_reason='length')
            d['choices'][0]['message']['content']=None
        return status,json.dumps(d),error
    r=launch(tmp_path,monkeypatch,fail)
    assert r['calls']==26 and r['integrity_errors']==[] and not r['pairs'][0]['completed']
    assert not (tmp_path/'batch_stop.json').exists()


def test_transport_error_stops_admission_in_other_shards(tmp_path,monkeypatch):
    def fail(text,secret):return 429,'{"error":"unavailable"}','HTTPError'
    first=launch(tmp_path,monkeypatch,fail,index=0)
    assert first['integrity_errors']==[] and first['calls']==1
    assert (tmp_path/'batch_stop.json').exists()
    second=launch(tmp_path,monkeypatch,index=1)
    assert second['integrity_errors']==[] and second['calls']==0
    assert second['terminal']['halt']=='coordinated batch safety halt'


def test_started_call_not_retried_and_reservations_include_margin(tmp_path):
    store=PilotStore(tmp_path/'profile-0',{'fixture':True},[])
    backend=study.Backend(store,'TEST_SECRET_NOT_REAL',transport)
    s=study.specifications()[0]
    case=study.case_for(study.game.messages(s['profile'],s['arm'],s['profile']['leader'],'opening',[]),s['seed'])
    bound,reserve=study.reserve_for(study.request_for(case))
    assert reserve==(bound*Decimal('.269')+65552*Decimal('.4'))/1000000
    key,row=backend.call(case,'episodes')
    row['status']='started';store.save('calls',key,row)
    with pytest.raises(study.Halt,match='never retried'):backend.call(case,'episodes')
    with pytest.raises(study.Halt,match='spending'):
        study.budget_guard([dict(phase='episodes',status='started',reserved_usd='.374')],'episodes',reserve)


@pytest.mark.parametrize('failure',['episode','audit','budget',None])
def test_real_successor_prerequisite_refuses_failed_uncertified_or_overbudget_predecessor(tmp_path,monkeypatch,failure):
    from analysis import paper3_deepseek_long_agenda_audit as parent_audit
    parent=tmp_path/'results/paper3/deepseek_long_agenda_a1'
    (parent/'sessions').mkdir(parents=True)
    terminal=dict(episodes={'conflict39-s232000-B':'completed','conflict39-s232000-D':'completed'},
        halt=None,budgets={'episodes':{'accounted_usd':'7' if failure=='budget' else '.1'}})
    if failure=='episode':terminal['episodes']['conflict39-s232000-D']='failed'
    (parent/'sessions/terminal.json').write_text(json.dumps(terminal))
    (parent/'manifest.json').write_text(json.dumps({'fixture':True}))
    monkeypatch.setattr(study,'ROOT',tmp_path)
    monkeypatch.setattr(parent_audit,'audit',lambda _:dict(integrity_errors=['fixture'] if failure=='audit' else []))
    if failure:
        with pytest.raises(study.Halt):REAL_PREREQUISITE()
    else:
        assert REAL_PREREQUISITE()['prior_conservative_usd']=='0.186293343'
