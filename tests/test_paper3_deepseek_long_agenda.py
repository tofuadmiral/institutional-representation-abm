import copy
from decimal import Decimal
import json
import sys
import pytest
from experiments import paper3_deepseek_long_agenda as study
from experiments import paper3_deepseek_plain_agenda as previous
from analysis.paper3_deepseek_long_agenda_audit import audit
from paper3.audit_runtime import PilotStore


def transport(text,secret):
    request=json.loads(text)
    context=json.loads(request['messages'][-1]['content'].split('\n',1)[0])
    if context['stage']=='ratification':
        answer={'votes':{p:True for p in context['candidate_policy_ids']}}
    elif context['stage']=='pairwise':
        answer={'policy_id':'p3'}
    else:
        answer={'policy_id':'p3','message':'fixture'}
    return 200,json.dumps(dict(model=study.MODEL,provider=study.PROVIDER_NAME,
        usage=dict(prompt_tokens=100,completion_tokens=6000,cost=.0024,
            completion_tokens_details=dict(reasoning_tokens=5950)),
        choices=[dict(finish_reason='stop',message=dict(content=json.dumps(answer),reasoning='fixture'))])),None


def launch(tmp_path,monkeypatch,fn=transport):
    monkeypatch.setattr(study,'transmit',fn)
    monkeypatch.setattr(study,'read_key',lambda:'TEST_SECRET_NOT_REAL')
    monkeypatch.setattr(sys,'argv',['test','--output',str(tmp_path)])
    study.main()
    return audit(tmp_path)


def test_protocol_same_institution_only_budget_and_seed_change():
    protocol,sources=study.prepare()
    assert protocol['max_calls']==50 and protocol['cases']==[]
    assert protocol['inherited_gate']['gate_passed']
    assert [(s['seed'],s['arm']) for s in protocol['episodes']]==[(232000,'B'),(232000,'D')]
    assert study.LIMITS=={'gate':(0,Decimal('0')),'episodes':(50,Decimal('2.00'))}
    case=study.case_for(study.game.messages(study.game.profiles()[0],'D','r0','opening',[]),232000)
    request=study.request_for(case)
    old=previous.request_for(case)
    assert request['max_tokens']==65536 and study.BILLING_OUTPUT_BOUND==65552
    request['max_tokens']=4000
    assert request==old
    assert all(not p.name.startswith('.env') for p in sources)


def test_full_fifty_calls_audit_and_terminal_no_rerun(tmp_path,monkeypatch):
    calls=[]
    def counted(text,secret):
        calls.append(text)
        return transport(text,secret)
    report=launch(tmp_path,monkeypatch,counted)
    assert report['integrity_errors']==[] and len(calls)==50
    assert report['terminal']['checks']==0 and report['terminal']['gate_passed']
    assert report['terminal']['gate_reused_from']==study.prepare()[0]['inherited_gate_protocol']
    assert report['certified_cost_records']==50 and report['pairs'][0]['completed']
    study.main()
    assert len(calls)==50


def test_length_failure_is_retained_other_arm_runs(tmp_path,monkeypatch):
    calls=[]
    def cutoff(text,secret):
        calls.append(text)
        status,raw,error=transport(text,secret)
        data=json.loads(raw)
        if len(calls)==1:
            data['usage']['completion_tokens']=65538
            data['usage']['completion_tokens_details']['reasoning_tokens']=65537
            data['usage']['cost']=.025
            data['choices'][0].update(finish_reason='length')
            data['choices'][0]['message']['content']=None
        return status,json.dumps(data),error
    report=launch(tmp_path,monkeypatch,cutoff)
    assert len(calls)==26 and report['integrity_errors']==[]
    assert report['terminal']['halt'] is None
    assert report['terminal']['episodes']=={'conflict39-s232000-B':'failed','conflict39-s232000-D':'completed'}
    assert not report['pairs'][0]['completed']
    assert 'resolution' not in report['episodes']['conflict39-s232000-B']


@pytest.mark.parametrize('kind',['http','secret','over_bound'])
def test_global_safety_halts_and_no_leaks(tmp_path,monkeypatch,kind):
    calls=[]
    def broken(text,secret):
        calls.append(text)
        status,raw,error=transport(text,secret)
        data=json.loads(raw)
        if kind=='http': return 429,'{"error":429}','HTTPError'
        if kind=='secret': data['echo']=secret
        if kind=='over_bound': data['usage']['completion_tokens']=65553
        return status,json.dumps(data),error
    report=launch(tmp_path,monkeypatch,broken)
    assert len(calls)==1 and report['integrity_errors']==[]
    assert report['terminal']['halt']=='transport/accounting/routing failure'
    assert not any('TEST_SECRET_NOT_REAL' in p.read_text() for p in (tmp_path/'calls').glob('*.json'))


def test_budget_reserves_accounting_margin_and_no_gate_calls(tmp_path):
    case=study.case_for(study.game.messages(study.game.profiles()[0],'D','r0','opening',[]),232000)
    request=study.request_for(case)
    bound,reserve=study.reserve_for(request)
    assert reserve==(bound*Decimal('.269')+65552*Decimal('.4'))/1000000
    with pytest.raises(study.Halt,match='call limit'):
        study.budget_guard([],'gate',reserve)
    with pytest.raises(study.Halt,match='spending'):
        study.budget_guard([dict(phase='episodes',status='started',reserved_usd='1.999')],'episodes',reserve)


def test_started_call_never_retried(tmp_path):
    store=PilotStore(tmp_path,{'test':True},[])
    worker=study.Backend(store,'TEST_SECRET_NOT_REAL',transport)
    case=study.case_for(study.game.messages(study.game.profiles()[0],'D','r0','opening',[]),232000)
    key,row=worker.call(case,'episodes')
    row['status']='started'; store.save('calls',key,row)
    with pytest.raises(study.Halt,match='never retried'):
        worker.call(case,'episodes')
