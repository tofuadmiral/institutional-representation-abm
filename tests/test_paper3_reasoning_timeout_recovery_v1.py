"""PRIVATE recovery tests, never paid model calls or experimental observations."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments import paper3_reasoning_timeout_recovery_v1 as w
from experiments import paper3_independent_validation_v1 as old
from paper3 import retrospective_reasoning_timeout_recovery_v1 as p
from tests.test_paper3_independent_validation_v1 import fixture
from tests.test_paper3_retrospective_deepinfra_core_v1 import evidence

REPO=Path(__file__).resolve().parents[1]
SAVED=REPO/old.ROOT_NAME/'block-0/calls'/(w.FAILED+'.json')


def test_real_saved_timeout_now_eligible_without_modifying_its_verdict_or_charge():
    before=SAVED.read_bytes()
    row=w.load(SAVED)
    assert not p.original.overload(row)['eligible']
    result=p.eligibility(row)
    assert result['eligible'] and not result['received_action']
    assert result['certified_actual_charge_preserved']
    assert not result['full_failed_reservation_retained']
    assert row['result']['status']=='unsafe_failed' and SAVED.read_bytes()==before


def set_delta(row,change):
    for i,line in enumerate(row['stream']['lines']):
        if line.startswith('data:'):
            frame=json.loads(line[5:].strip())
            if frame.get('choices'):
                change(frame['choices'][0]['delta'])
                row['stream']['lines'][i]='data: '+json.dumps(frame)
                break
    row['assessment']=p.billing.assess(row,p.classifier.CONFIG)


@pytest.mark.parametrize('change',[
    lambda d:d.update(content='x'),
    lambda d:d.update(content=' '),
    lambda d:d.update(tool_calls=[]),
    lambda d:d.update(tool_calls=[dict(index=0,function=dict(arguments='{'))]),
    lambda d:d.update(function_call=dict(arguments='{')),
    lambda d:d.update(refusal='refused'),
    lambda d:d.update(audio={}),
    lambda d:d.update(role='user'),
    lambda d:d.update(unknown_channel='x'),
])
def test_any_action_fragment_or_unknown_channel_still_cannot_retry(change):
    row=w.load(SAVED)
    set_delta(row,change)
    assert not p.eligibility(row)['eligible']


@pytest.mark.parametrize('change',[
    lambda r:r['stream'].update(error_type='ValueError'),
    lambda r:r['stream'].update(http_status=401),
    lambda r:r['stream'].update(secret_redacted=True),
    lambda r:r['stream'].update(http_error_body_truncated=True),
    lambda r:r['request']['provider'].update(allow_fallbacks=True),
    lambda r:r['request'].update(model='different'),
    lambda r:r.update(final_content='{}'),
    lambda r:r['result'].update(status='recorded_valid',action={}),
    lambda r:r['receipts'][0]['data'].update(total_cost=0.99),
    lambda r:r['receipts'][0]['data'].update(provider_name='other'),
])
def test_native_route_cost_content_secret_and_auth_guards_stay_strict(change):
    row=w.load(SAVED)
    change(row)
    row['assessment']=p.billing.assess(row,p.classifier.CONFIG)
    assert not p.eligibility(row)['eligible']


def test_known_absent_transient_receipts_keep_full_reservation_not_unknown_billing():
    row=w.load(SAVED)
    row['receipts']=[dict(http_status=404 if i%2==0 else None,
        error_type='HTTPError' if i%2==0 else 'TimeoutError',data=None,
        secret_redacted=False,scheduled_offset_seconds=offset)
        for i,offset in enumerate(p.billing.OFFSETS)]
    row['assessment']=p.billing.assess(row,p.classifier.CONFIG)
    verdict=p.eligibility(row)
    assert verdict['eligible'] and verdict['full_failed_reservation_retained']
    assert row['assessment']['accounted_usd']==row['reserved_usd']
    row['receipts'][0].update(http_status=403)
    row['assessment']=p.billing.assess(row,p.classifier.CONFIG)
    assert not p.eligibility(row)['eligible']


def timeout_stream(request,identifier,clock):
    stream=deepcopy(evidence(request,identifier)['stream'])
    frame=dict(id=identifier,model=old.previous.route.MODEL,
        provider=old.previous.route.PROVIDER,
        choices=[dict(index=0,delta=dict(role='assistant',content=None,
            reasoning='PRIVATE fabricated reasoning, no decision.'),finish_reason=None)])
    lines=['data: '+json.dumps(frame),'']
    stream.update(lines=lines,line_count=len(lines),byte_count=sum(len(s.encode())+1 for s in lines),
        error_type='TimeoutError',started_unix=clock(),ended_unix=clock(),
        first_line_unix=clock(),last_line_unix=clock(),http_error_body_truncated=False)
    return stream


def private_setup(tmp_path,monkeypatch):
    root,legacy,sent,base_send,base_lookup,book=fixture(tmp_path,monkeypatch)
    clock=old.time.time
    def send(wire,secret):
        if len(sent)==17:
            sent.append((wire,clock()))
            return timeout_stream(json.loads(wire),'gen-private-reasoning-only',clock)
        return base_send(wire,secret)
    def lookup(identifier,secret):
        if identifier=='gen-private-reasoning-only':
            return dict(http_status=200,error_type=None,secret_redacted=False,
                data=dict(id=identifier,model=old.previous.route.MODEL_ALIAS,
                    provider_name=old.previous.route.PROVIDER,total_cost=0.0001))
        return base_lookup(identifier,secret)
    # First the UNCHANGED old controller stops on this exact missing case.
    assert old.run(root,legacy,send=send,lookup=lookup)['status']=='paused'
    assert len(sent)==18 and len(list((root/'block-0/accepted').glob('*.json')))==16
    meta=root/'reasoning_timeout_amendment_v1'
    meta.mkdir()
    monkeypatch.setattr(w,'ROOT',root)
    monkeypatch.setattr(w,'META',meta)
    monkeypatch.setattr(w,'REPO',tmp_path)
    monkeypatch.setattr(w,'LEGACY',legacy)
    monkeypatch.setattr(w,'time',SimpleNamespace(time=clock,sleep=clock.sleep,
        time_ns=lambda:int(clock()*1e9)))
    monkeypatch.setattr(book,'_entries',lambda:[w.load(p)
        for p in (book.root/'entries').glob('*.json')],raising=False)
    amendment=dict(accepted_prefix={f.stem:w.load(f)
        for f in (root/'block-0/accepted').glob('*.json')},
        disclosure='PRIVATE fabricated software fixture only')
    monkeypatch.setattr(w,'verify',lambda *a,**k:amendment)
    def admit(unused):
        admit.observed_unix=clock()
    return root,legacy,sent,send,lookup,book,admit


def test_full480_resume_preserves_16_decisions_and_failed_cost_then_entire_amended_audit(
        tmp_path,monkeypatch):
    root,legacy,sent,send,lookup,book,admit=private_setup(tmp_path,monkeypatch)
    old_raw={f: f.read_bytes() for f in (root/'block-0/calls').glob('*.json')}
    old_entries={f:f.read_bytes() for f in (book.root/'entries').glob('*.json')}
    old_admission=(root/'block-0/admission.json').read_bytes()
    original_terminal=(root/'invocations/0000-terminal.json').read_bytes()
    result=w.run('f'*64,send=send,lookup=lookup,admission=admit)
    assert result['status']=='complete' and len(sent)==482,result
    assert sent[17][0]==sent[18][0] and sent[18][1]-sent[17][1]>=300
    assert all(f.read_bytes()==raw for f,raw in old_raw.items())
    assert all(f.read_bytes()==raw for f,raw in old_entries.items())
    assert (root/'block-0/admission.json').read_bytes()==old_admission
    assert (root/'invocations/0000-terminal.json').read_bytes()==original_terminal
    report=old.journal.decode(w.load(root/'report.json'))
    assert report['analysis']['episodes_complete']==16
    assert report['transport_recovery']['amendment_protocol']=='f'*64
    assert w.audit('f'*64)['entire_report_matched']
    assert len(sent)==482
    window=w.load(w.META/'remaining_frame0_admission.json')
    assert window['deadline_unix']-window['started_unix']==86400


def test_expired_remaining_window_never_resets_or_sends(tmp_path,monkeypatch):
    root,legacy,sent,send,lookup,book,admit=private_setup(tmp_path,monkeypatch)
    window=w.META/'remaining_frame0_admission.json'
    w.atomic(window,dict(started_unix=0,deadline_unix=1))
    before=window.read_bytes()
    count=len(sent)
    with pytest.raises(ValueError,match='never reset'):
        w.run('f'*64,send=send,lookup=lookup,admission=admit)
    assert len(sent)==count and window.read_bytes()==before


def test_exact_durable_worker_economics_and_receipt_code_objects_unchanged():
    assert p.DurableResponses._respond.__code__ is p.original.DurableResponses._respond.__code__
    assert old.billing.execute.__code__ is old.billing.engine.execute.__code__
    assert old.billing.Calls.one.__code__ is old.billing.native.Calls.one.__code__
