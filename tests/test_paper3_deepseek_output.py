import copy
from decimal import Decimal
import json
import sys
import pytest
from experiments import paper3_deepseek_output_diagnostic as study
from analysis.paper3_deepseek_output_audit import audit
from paper3.audit_runtime import PilotStore


def transport(text, secret):
    request = json.loads(text)
    answer = study.base.gate_cases()[request['seed']-200000]['expected']
    response = dict(model=study.base.MODEL, provider=study.base.PROVIDER_NAME,
        usage=dict(prompt_tokens=100, completion_tokens=50, cost=.0001,
            completion_tokens_details=dict(reasoning_tokens=30)),
        choices=[dict(finish_reason='stop', message=dict(content=json.dumps(answer), reasoning=json.dumps(answer)))])
    return 200, json.dumps(response), None


def launch(tmp_path, monkeypatch, fn=transport):
    monkeypatch.setattr(study.base, 'transmit', fn)
    monkeypatch.setattr(study.base, 'read_key', lambda:'TEST_SECRET_NOT_REAL')
    monkeypatch.setattr(sys, 'argv', ['test','--output',str(tmp_path)])
    study.main()
    return audit(tmp_path)


def test_only_response_format_changes_and_balanced_order():
    cases = study.cases()
    assert len(cases) == 16
    for i in range(8):
        pair = cases[2*i:2*i+2]
        assert [r['mode'] for r in pair] == (['strict','plain'] if i%2==0 else ['plain','strict'])
        requests = {r['mode']:study.request_for(r) for r in pair}
        strict = copy.deepcopy(requests['strict'])
        del strict['response_format']
        assert strict == requests['plain']
        assert strict['messages'] == study.base.gate_cases()[i]['messages']
        assert strict['seed'] == 200000+i and strict['reasoning']['enabled']
    protocol,sources = study.prepare()
    assert protocol['max_calls']==16 and protocol['max_usd']=='0.10'
    assert not any(p.name.startswith('.env') for p in sources)


def test_complete_run_exact_replay_idempotent_no_secrets(tmp_path,monkeypatch):
    count=[]
    def counted(text,secret):
        count.append(text)
        return transport(text,secret)
    report=launch(tmp_path,monkeypatch,counted)
    assert report['integrity_errors']==[] and len(count)==16
    assert report['certified_cost_records']==16
    assert report['terminal']['budget']['accounted_usd']=='0.0016'
    assert report['terminal']['episodes']=={}
    assert all(report['terminal']['modes'][m]['exact']==8 for m in study.MODES)
    study.main()
    assert len(count)==16
    assert not any('TEST_SECRET_NOT_REAL' in p.read_text() for p in (tmp_path/'calls').glob('*.json'))
    path=next((tmp_path/'calls').glob('*.json'))
    row=json.loads(path.read_text()); row['response']['usage']['cost']=0
    path.write_text(json.dumps(row))
    assert audit(tmp_path)['integrity_errors']


def test_reasoning_does_not_repair_wrong_final():
    case=study.cases()[0]
    request=study.request_for(case)
    _,raw,_=transport(study.base.encoded_request(request),'fake')
    bound,reserve=study.base.reserve_for(request)
    row=dict(response=json.loads(raw),input_token_bound=bound,reserved_usd=str(reserve))
    row['response']['choices'][0]['message']['content']='{"selected_policy":"policy_m","votes":{"policy_k":false,"policy_m":true}}'
    result=study.score(row,case)
    assert result['valid'] and not result['exact']
    assert result['reasoning_observation']['exact']
    assert result['reasoning_observation']['agrees_with_final'] is False
    row['response']['choices'][0]['message']['reasoning']='prose only; not scored'
    assert study.score(row,case)['reasoning_observation']==dict(json_count=0,available=False)


def test_last_complete_reasoning_object_selected_no_prose_inference():
    case=study.cases()[0]
    value=case['expected']
    text='earlier '+json.dumps(dict(selected_policy='policy_m',votes=dict(policy_k=False,policy_m=True)))+' later '+json.dumps(value)+' {broken'
    row=dict(response=dict(choices=[dict(message=dict(reasoning=text))]))
    result=study.reasoning_report(row,case,dict(valid=True,reply=value))
    assert result['json_count']==2 and result['reply']==value and result['agrees_with_final']


@pytest.mark.parametrize('kind',['http','secret','wrong_provider','missing_cost'])
def test_global_failures_no_retry(tmp_path,monkeypatch,kind):
    calls=[]
    def broken(text,secret):
        calls.append(text)
        status,raw,error=transport(text,secret)
        data=json.loads(raw)
        if kind=='http': return 429,'{"error":{"code":429}}','HTTPError'
        if kind=='secret': data['echo']=secret
        if kind=='wrong_provider': data['provider']='other'
        if kind=='missing_cost': del data['usage']['cost']
        return status,json.dumps(data),error
    report=launch(tmp_path,monkeypatch,broken)
    assert len(calls)==1 and report['calls']==1 and report['integrity_errors']==[]
    assert report['terminal']['halt']=='transport/accounting/routing failure'
    assert not any('TEST_SECRET_NOT_REAL' in p.read_text() for p in (tmp_path/'calls').glob('*.json'))


def test_invalid_plain_response_retained_rest_continue(tmp_path,monkeypatch):
    def plain_bad(text,secret):
        status,raw,error=transport(text,secret)
        data=json.loads(raw)
        if 'response_format' not in json.loads(text):
            data['choices'][0]['message']['content']='policy_k'
        return status,json.dumps(data),error
    report=launch(tmp_path,monkeypatch,plain_bad)
    assert report['calls']==16 and report['integrity_errors']==[]
    assert report['terminal']['modes']['plain']['valid']==0
    assert report['terminal']['modes']['strict']['exact']==8


def test_started_never_resent_and_no_episode_phase(tmp_path):
    store=PilotStore(tmp_path,{'test':True},[])
    worker=study.Backend(store,'fake',transport)
    key,row=worker.call(study.cases()[0])
    row['status']='started'; store.save('calls',key,row)
    with pytest.raises(study.base.Halt,match='never retried'):
        worker.call(study.cases()[0])
    with pytest.raises(study.base.Halt,match='no episode'):
        worker.call(study.cases()[1],'episodes')


def test_budget_checked_before_send(tmp_path,monkeypatch):
    monkeypatch.setitem(study.base.LIMITS,'gate',(16,Decimal('.00001')))
    calls=[]
    def forbidden(text,secret):
        calls.append(text)
        raise AssertionError('must not send')
    report=launch(tmp_path,monkeypatch,forbidden)
    assert not calls and report['calls']==0 and report['integrity_errors']==[]
    assert report['terminal']['halt']=='authorized phase spending ceiling reached'
