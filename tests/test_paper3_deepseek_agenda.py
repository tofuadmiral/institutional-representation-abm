import copy
from decimal import Decimal
import json
from pathlib import Path
import sys
import pytest
from experiments import paper3_deepseek_agenda as study
from analysis.paper3_deepseek_agenda_audit import audit, pairs
from paper3.audit_runtime import PilotStore, digest


def transport(text, secret):
    request = json.loads(text)
    schema = request['response_format']['json_schema']['schema']
    if 190000 <= request['seed'] < 190016:
        case = study.gate_cases()[request['seed']-190000]
        answer = case['expected'] or {'policy_id': 'policy_k'}
    elif 'votes' in schema['properties']:
        answer = {'votes': {p: True for p in schema['properties']['votes']['properties']}}
    else:
        answer = {'policy_id': 'p3'}
        if 'message' in schema['properties']:
            answer['message'] = 'fixture'
    response = dict(id='fake-generation-'+str(request['seed']), model=study.MODEL,
        provider=study.PROVIDER_NAME, usage=dict(prompt_tokens=100, completion_tokens=50,
        completion_tokens_details=dict(reasoning_tokens=40), cost=0.0001),
        choices=[dict(finish_reason='stop', message=dict(role='assistant', content=json.dumps(answer), reasoning='fixture reasoning'))])
    return 200, json.dumps(response), None


def backend(tmp_path, transport_fn=transport):
    store = PilotStore(tmp_path, {'test': True}, [])
    return study.Backend(store, 'TEST_SECRET_NOT_REAL', transport_fn)


def test_fixed_protocol_and_unchanged_decision_inputs():
    protocol, sources = study.prepare()
    assert protocol['max_calls'] == 166
    assert protocol['phase_limits'] == {'gate': {'calls': 16, 'usd': '0.10'}, 'episodes': {'calls': 150, 'usd': '0.36'}}
    assert len(study.specifications())*25 == 150
    assert [(s['seed'], s['arm']) for s in study.specifications()] == [
        (191000,'D'),(191000,'B'),(192000,'B'),(192000,'D'),(193000,'D'),(193000,'B')]
    assert all(s['profile']==study.game.profiles()[0] for s in study.specifications())
    for new, old in zip(study.gate_cases(), study.fixtures.cases()):
        assert {k:v for k,v in new.items() if k!='seed'} == {k:v for k,v in old.items() if k!='seed'}
    request = study.request_for(study.gate_cases()[0])
    assert request['reasoning']=={'enabled':True,'exclude':False}
    assert request['provider']['only']==[study.PROVIDER]
    assert request['provider']['allow_fallbacks'] is False
    assert request['provider']['require_parameters'] is True
    assert request['provider']['quantizations']==['fp8']
    assert request['max_tokens']==4000 and request['plugins']==[]
    assert all(not p.name.startswith('.env') for p in sources)


def test_reserve_and_separate_phase_limits():
    request=study.request_for(study.gate_cases()[0])
    bound,reserve=study.reserve_for(request)
    assert bound==len(study.encoded_request(request).encode())+1024
    assert reserve==(bound*Decimal('.269')+4000*Decimal('.4'))/1000000
    rows=[dict(phase='gate',status='started',reserved_usd='.099')]
    with pytest.raises(study.Halt,match='spending'):
        study.budget_guard(rows,'gate',Decimal('.002'))
    study.budget_guard(rows,'episodes',Decimal('.002'))
    with pytest.raises(study.Halt,match='call limit'):
        study.budget_guard([dict(phase='gate',status='started',reserved_usd='0')]*16,'gate',reserve)


def test_before_send_marker_cache_no_retry_and_no_key_artifacts(tmp_path):
    requests=[]
    def checking_transport(text,secret):
        saved=list((tmp_path/'calls').glob('*.json'))
        assert len(saved)==1 and json.loads(saved[0].read_text())['status']=='started'
        requests.append(text)
        return transport(text,secret)
    worker=backend(tmp_path,checking_transport)
    case=study.gate_cases()[0]
    key,row=worker.call(case,'gate')
    assert study.gate_score(row,case)['passed']
    assert worker.call(case,'gate')==(key,row) and len(requests)==1
    path=tmp_path/'calls'/(key+'.json')
    assert 'TEST_SECRET_NOT_REAL' not in path.read_text()
    row['status']='started'
    path.write_text(json.dumps(row))
    with pytest.raises(study.Halt,match='never retried'):
        worker.call(case,'gate')
    assert len(requests)==1


@pytest.mark.parametrize('kind',['http','timeout','secret','wrong_provider','missing_cost','overspend'])
def test_transport_billing_and_credential_failures_halt(tmp_path,kind):
    def broken(text,secret):
        status,raw,error=transport(text,secret)
        data=json.loads(raw)
        if kind=='http': return 429,'{"error":{"code":429}}','HTTPError'
        if kind=='timeout': return None,'','TimeoutError'
        if kind=='secret': data['echo']=secret
        if kind=='wrong_provider': data['provider']='DifferentProvider'
        if kind=='missing_cost': del data['usage']['cost']
        if kind=='overspend': data['usage']['cost']=10
        return status,json.dumps(data),error
    worker=backend(tmp_path,broken)
    _,row=worker.call(study.gate_cases()[0],'gate')
    assert worker.halt and row['accounting_error']
    assert study.ledger(worker.rows(),'gate')[1]==Decimal(row['reserved_usd'])
    assert 'TEST_SECRET_NOT_REAL' not in ''.join(p.read_text() for p in (tmp_path/'calls').glob('*'))


def test_reasoning_and_length_failures_not_repaired(tmp_path):
    worker=backend(tmp_path)
    _,row=worker.call(study.gate_cases()[0],'gate')
    for mutation in ('length','no_reasoning','invalid_json'):
        edited=copy.deepcopy(row)
        choice=edited['response']['choices'][0]
        if mutation=='length': choice['finish_reason']='length'
        elif mutation=='no_reasoning': edited['response']['usage']['completion_tokens_details']['reasoning_tokens']=0
        else: choice['message']['content']='policy_k'
        assert not study.gate_score(edited,study.gate_cases()[0])['passed']


def test_full_offline_run_exact_audit_and_terminal_idempotence(tmp_path,monkeypatch):
    count=[]
    def counted(text,secret):
        count.append(json.loads(text))
        return transport(text,secret)
    monkeypatch.setattr(study,'transmit',counted)
    monkeypatch.setattr(study,'read_key',lambda: 'TEST_SECRET_NOT_REAL')
    monkeypatch.setattr(sys,'argv',['test','--output',str(tmp_path)])
    study.main()
    assert len(count)==166
    report=audit(tmp_path)
    assert report['integrity_errors']==[]
    assert report['terminal']['gate_passed'] and len(report['terminal']['episodes'])==6
    assert report['certified_cost_records']==166
    assert all(p['completed'] for p in report['pairs'])
    assert Decimal(report['total_accounted_usd'])==Decimal('.0166')
    study.main()
    assert len(count)==166
    # Altering a raw response independently of its serialized response is detected.
    file=next((tmp_path/'calls').glob('*.json'))
    changed=json.loads(file.read_text()); changed['response']['usage']['cost']=0
    file.write_text(json.dumps(changed))
    assert audit(tmp_path)['integrity_errors']


def test_failed_gate_prevents_all_150_calls(tmp_path,monkeypatch):
    count=[]
    def wrong(text,secret):
        status,raw,error=transport(text,secret)
        count.append(text)
        data=json.loads(raw)
        if len(count)==1:
            data['choices'][0]['message']['content']='{"selected_policy":"policy_k","votes":{"policy_k":false,"policy_m":false}}'
        return status,json.dumps(data),error
    monkeypatch.setattr(study,'transmit',wrong)
    monkeypatch.setattr(study,'read_key',lambda: 'TEST_SECRET_NOT_REAL')
    monkeypatch.setattr(sys,'argv',['test','--output',str(tmp_path)])
    study.main()
    report=audit(tmp_path)
    assert len(count)==16 and report['integrity_errors']==[]
    assert not report['terminal']['gate_passed'] and not report['terminal']['episodes']
    assert all(not p['completed'] for p in report['pairs'])


def test_early_http_failure_retained_and_auditable(tmp_path,monkeypatch):
    monkeypatch.setattr(study,'transmit',lambda text,secret:(402,'{"error":{"code":402}}','HTTPError'))
    monkeypatch.setattr(study,'read_key',lambda: 'TEST_SECRET_NOT_REAL')
    monkeypatch.setattr(sys,'argv',['test','--output',str(tmp_path)])
    study.main()
    report=audit(tmp_path)
    assert report['calls']==1 and report['integrity_errors']==[]
    assert report['terminal']['halt']=='transport/accounting/routing failure'


def test_episode_budget_stop_before_transport_replays_without_policy(tmp_path,monkeypatch):
    monkeypatch.setitem(study.LIMITS,'episodes',(150,Decimal('.00011')))
    monkeypatch.setattr(study,'transmit',transport)
    monkeypatch.setattr(study,'read_key',lambda: 'TEST_SECRET_NOT_REAL')
    monkeypatch.setattr(sys,'argv',['test','--output',str(tmp_path)])
    study.main()
    report=audit(tmp_path)
    assert report['calls']==16 and report['integrity_errors']==[]
    assert report['terminal']['halt']=='authorized phase spending ceiling reached'
    assert report['terminal']['episodes']=={'conflict39-s191000-D':'failed'}
    assert 'resolution' not in report['episodes']['conflict39-s191000-D']
