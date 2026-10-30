"""Offline fabricated transport/receipt tests. No key and no real API calls."""
import copy
from decimal import Decimal
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.error
import zipfile

import pytest

MODULE = Path(__file__).resolve().parents[1]/'experiments/paper3_transport_diagnostic.py'
spec = importlib.util.spec_from_file_location('transport_diagnostic', MODULE)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


def metadata():
    return {'data': {'id': d.MODEL, 'endpoints': [dict(tag='atlas-cloud/fp8',
        provider_name=d.PROVIDER,model_id=d.MODEL,quantization='fp8',
        name='AtlasCloud | '+d.MODELS[1],status=0,max_completion_tokens=147456,
        supported_parameters=['reasoning','max_tokens','temperature','top_p','top_k','min_p',
                              'seed','presence_penalty','repetition_penalty'],
        pricing={'prompt':'0.00000026','completion':'0.00000038'})]}}


@pytest.fixture
def frozen(tmp_path,monkeypatch):
    class Public:
        def open(self,url,timeout):
            assert url==d.METADATA_URL and timeout==20
            return io.BytesIO(json.dumps(metadata()).encode())
    monkeypatch.setattr(d,'opener',lambda:Public())
    monkeypatch.setattr(d,'seed_check',lambda:dict(planned=list(range(315000,315004)),overlaps=[]))
    root=tmp_path/'run'
    protocol=d.prepare(root)
    assert d.verify_freeze(root)[1]==protocol
    return root


def trace(gid='gen-fixture',now=10,model=d.MODEL,finish='stop'):
    frames=[dict(id=gid,model=model,provider=d.PROVIDER,
                 choices=[dict(index=0,delta={'reasoning':'fabricated'},finish_reason=None)]),
            dict(choices=[dict(index=0,delta={'content':'not action-scored'},finish_reason=finish)]),
            dict(choices=[],usage=dict(prompt_tokens=100,completion_tokens=200,cost=.0001,
                                      completion_tokens_details={'reasoning_tokens':190}))]
    lines=[]
    for f in frames: lines += ['data: '+json.dumps(f),'']
    lines += ['data: [DONE]','']
    return dict(started_unix=now,ended_unix=now,http_status=200,generation_header=None,
        lines=lines,line_count=len(lines),byte_count=sum(len(x)+1 for x in lines),
        first_line_unix=now,last_line_unix=now,error_type=None,secret_redacted=False)


def receipt(gid='gen-fixture',now=10,**data):
    fields=dict(id=gid,model=d.MODELS[1],provider_name=d.PROVIDER,total_cost=.0001)
    fields.update(data)
    return dict(http_status=200,error_type=None,secret_redacted=False,data=fields,
                started_unix=now,ended_unix=now)


def row():
    return dict(d.cases()[0],stream=trace(),receipts=[receipt()])


def run_fake(root,mode='ok'):
    guard=threading.Lock(); barrier=threading.Barrier(4); now=[time.time()]
    requests=[]; gets=[]
    def clock():
        with guard: now[0]+=.001; return now[0]
    def sleep(seconds):
        with guard: now[0]+=seconds
    def transport(wire,secret):
        requests.append(json.loads(wire)['seed'])
        barrier.wait(timeout=5)
        if mode=='raise': raise RuntimeError('not persisted')
        answer=trace('gen-'+str(json.loads(wire)['seed']),clock())
        if mode=='truncate': answer['lines']=answer['lines'][:-2];answer['line_count']-=2
        return answer
    def lookup(gid,secret):
        gets.append(gid)
        ans=receipt(gid,clock())
        if mode=='404': ans.update(http_status=404,error_type='HTTPError',data=None)
        return ans
    terminal=d.execute(root,'fixture-secret',transport,lookup,clock,sleep)
    return terminal,requests,gets


def test_exact_wire_only_seed_changes():
    selected=d.cases()
    assert sum(Decimal(c['reserved_usd']) for c in selected)==Decimal('.111891188')
    for c in selected:
        source=d.load(d.ROOT/c['source_call'])
        new=json.loads(c['request_text']); old=json.loads(source['request_text'])
        assert new['seed']==315000+c['index']
        new['seed']=old['seed']
        assert d.encoded(new)==source['request_text']


@pytest.mark.parametrize('model',d.MODELS)
def test_explicit_model_ids_accepted(model):
    r=row(); r['stream']=trace(model=model); r['receipts']=[receipt(model=model)]
    assert d.assess(r)['passed']


@pytest.mark.parametrize('field,value',[('model',d.MODEL+'-other'),('provider_name','different'),
                                      ('id','other-id'),('total_cost',-1),('total_cost','NaN'),
                                      ('total_cost',.1),('total_cost',None)])
def test_invalid_receipt_cannot_hide_behind_valid_one(field,value):
    r=row(); r['receipts'].append(receipt(**{field:value}))
    a=d.assess(r)
    assert not a['passed'] and not a['receipt_certified']
    assert Decimal(a['accounted_usd'])>=Decimal(r['reserved_usd'])


def test_missing_receipt_keeps_reserve_and_valid_later_observation_certifies():
    r=row(); r['receipts']=[dict(http_status=404,error_type='HTTPError',data=None)]
    assert d.assess(r)['accounted_usd']==r['reserved_usd']
    r['receipts'].append(receipt())
    assert d.assess(r)['passed']


def test_conflicting_costs_and_stream_receipt_mismatch():
    r=row();r['receipts'].append(receipt(total_cost=.0002))
    assert not d.assess(r)['receipt_certified']
    r['receipts']=[receipt(total_cost=.0002)]
    assert not d.assess(r)['receipt_certified']


@pytest.mark.parametrize('kind',['truncated','error','malformed','after_done','two_done','no_usage',
                               'wrong_index','mixed_identity','exception','redaction','no_provider'])
def test_invalid_stream_never_rescued_by_valid_charge(kind):
    r=row(); t=r['stream']; lines=t['lines']
    if kind=='truncated': t['lines']=lines[:-2]
    elif kind=='error': lines[:0]=['data: {"error":{"message":"failure"}}','']
    elif kind=='malformed': lines[:0]=['data: {invalid','']
    elif kind=='after_done': lines+=['data: {}','']
    elif kind=='two_done': lines+=['data: [DONE]','']
    elif kind=='no_usage': t['lines']=lines[:4]+lines[6:]
    elif kind=='wrong_index': lines[0]=lines[0].replace('"index": 0','"index": 1')
    elif kind=='mixed_identity': lines[:0]=['data: {"id":"different"}','']
    elif kind=='exception': t['error_type']='TimeoutError'
    elif kind=='redaction': t['secret_redacted']=True
    elif kind=='no_provider': lines[0]=lines[0].replace(', "provider": "AtlasCloud"','')
    a=d.assess(r)
    assert not a['passed']
    if kind!='mixed_identity': assert a['receipt_certified']


def test_sse_comments_multiline_and_repeated_terminal_finish():
    t=trace(finish='length')
    t['lines'][:0]=[': keepalive','event: message','']
    t['lines'][-2:-2]=['data: {"choices":', 'data: [{"index":0,"finish_reason":"length"}]}','']
    r=row();r['stream']=t
    assert d.assess(r)['passed'] and d.assess(r)['length_ending']


@pytest.mark.parametrize('value',[None,'bad',[],['bad'],True])
def test_bad_usage_fails_without_crashing(value):
    r=row();r['stream']['lines'][4]='data: '+json.dumps({'usage':value})
    assert not d.assess(r)['passed']


def test_prepare_and_source_tamper(frozen):
    with pytest.raises(ValueError,match='overwrite'):d.prepare(frozen)
    snap=d.load(frozen/'sources.json');snap['experiments/paper3_transport_diagnostic.py']+='\n'
    d.save(frozen/'sources.json',snap)
    with pytest.raises(ValueError,match='frozen source changed'):d.verify_freeze(frozen)


@pytest.mark.parametrize('field,value',[('workers',5),('cap_usd','.20'),
                                      ('stream_socket_timeout_seconds',30)])
def test_protocol_invariants(frozen,field,value):
    m=d.load(frozen/'manifest.json');m['protocol'][field]=value;d.save(frozen/'manifest.json',m)
    with pytest.raises(ValueError):d.verify_freeze(frozen)


def test_four_attempts_receipt_schedule_and_no_restart(frozen):
    terminal,requests,gets=run_fake(frozen)
    assert sorted(requests)==list(range(315000,315004)) and len(gets)==16
    assert terminal['accounted_usd']=='0.0004'
    report=d.audit(frozen)
    assert report['all_four_passed'] and report['calls']==4
    for p in (frozen/'calls').glob('*.json'):
        assert [o['scheduled_offset_seconds'] for o in d.load(p)['receipts']]==[0,20,40,60]
    with pytest.raises(ValueError,match='never restart'):d.execute(frozen,'fixture')


@pytest.mark.parametrize('mode',['truncate','404','raise'])
def test_failures_retained_without_extra_inference(frozen,mode):
    terminal,requests,gets=run_fake(frozen,mode)
    assert len(requests)==4 and len(set(requests))==4
    report=d.audit(frozen)
    assert not report['all_four_passed'] and report['assigned']==4 and terminal['stopped']
    assert Decimal(report['accounted_usd'])==(Decimal('.0004') if mode=='truncate' else Decimal('.111891188'))
    assert len(gets)==(0 if mode=='raise' else 16)


def test_unstarted_cases_retained_after_immediate_failure(frozen,monkeypatch):
    class Sequential:
        def __init__(self,**kw): pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def map(self,fn,items):return map(fn,items)
    monkeypatch.setattr(d,'ThreadPoolExecutor',Sequential)
    def fail(*args):raise RuntimeError('no retries')
    t=d.execute(frozen,'fixture',transport=fail)
    assert t['admitted_indices']==[0] and t['stopped']
    a=d.audit(frozen)
    assert a['calls']==1 and a['assigned']==4
    assert [r['status'] for r in a['cases']]==['instrument_error']+['not_started']*3


def test_receipt_http_status_and_exception_without_secret(monkeypatch):
    secret='do-not-persist-this-value'
    class Broken:
        def open(self,request,timeout):
            assert timeout==10
            raise urllib.error.HTTPError(request.full_url,404,secret,{},None)
    monkeypatch.setattr(d,'opener',lambda:Broken())
    ans=d.receipt_lookup('generation',secret)
    assert ans['http_status']==404 and ans['error_type']=='HTTPError'
    assert secret not in json.dumps(ans)


def test_transmit_captures_counts_and_redacts(monkeypatch):
    secret='test-only-private-string'
    class Response(io.BytesIO):
        status=200
        headers={'X-Generation-Id':'example'}
    class Fake:
        def open(self,request,timeout):
            assert timeout==900 and request.method=='POST'
            return Response(('data: '+json.dumps({'text':secret})+'\n\n').encode())
    monkeypatch.setattr(d,'opener',lambda:Fake())
    ans=d.transmit('{}',secret)
    assert ans['line_count']==2 and ans['byte_count']>0 and ans['secret_redacted']
    assert secret not in json.dumps(ans)
    assert d.NoRedirect().redirect_request(None,None,None,None,None,None) is None


def test_metadata_fails_on_different_mapping_or_price():
    m=metadata();m['data']['endpoints'][0]['name']='AtlasCloud | '+d.MODEL+'-new'
    with pytest.raises(ValueError,match='canonical identity'):d.check_metadata(m)
    m=metadata();m['data']['endpoints'][0]['pricing']['completion']='0.00000041'
    with pytest.raises(ValueError,match='price'):d.check_metadata(m)


def test_seed_audit_includes_unexecuted_recent_positions(tmp_path):
    p=tmp_path/'results/paper3/fixture';p.mkdir(parents=True)
    d.save(p/'manifest.json',{'protocol':{'seed':314000}})
    s=d.seed_check(tmp_path)
    assert 314024 in s['expanded_recent_schedules'] and 292024 in s['expanded_recent_schedules']
    d.save(p/'manifest.json',{'protocol':{'seed':315001}})
    with pytest.raises(ValueError,match='overlap'):d.seed_check(tmp_path)


@pytest.mark.parametrize('mode',['ok','404'])
def test_actual_isolated_archive_replay(frozen,tmp_path,mode):
    run_fake(frozen,mode)
    target=tmp_path/'evidence.zip'
    info=d.archive(frozen,target)
    assert info['files']>6
    with pytest.raises(ValueError,match='overwrite'):d.archive(frozen,target)
    bundle=tmp_path/'unpacked'
    with zipfile.ZipFile(target) as z:z.extractall(bundle)
    protocol=d.verify_freeze(frozen)[1]
    cmd=[sys.executable,'-I','-S',str(bundle/'code/experiments/paper3_transport_diagnostic.py'),
         str(bundle),'--replay','--expected-protocol',protocol]
    completed=subprocess.run(cmd,cwd=tmp_path,env={},capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr
    assert json.loads(completed.stdout)==d.audit(frozen)
    (bundle/'run/calls/0.json').write_text('changed')
    bad=subprocess.run(cmd,cwd=tmp_path,env={},capture_output=True,text=True)
    assert bad.returncode!=0 and 'hash mismatch' in bad.stderr


def test_archive_credential_scan_and_offline_guard(frozen,tmp_path):
    run_fake(frozen)
    with pytest.raises(ValueError,match='credential found'):
        d.archive(frozen,tmp_path/'forbidden.zip','Four approved transport-only')
    assert not (tmp_path/'forbidden.zip').exists()
    with pytest.raises(RuntimeError,match='forbidden'):d.offline_guard('socket.__new__',())
    with pytest.raises(RuntimeError,match='forbidden'):d.offline_guard('subprocess.Popen',())
