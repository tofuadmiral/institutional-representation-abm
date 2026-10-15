"""Prospective offline tests; fabricated streams are never research observations."""
from copy import deepcopy
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
from experiments import paper3_qwen_channel_gate as r
from paper3.pivot_b_budget import BUDGET_ID,atomic


def metadata():
    return dict(data=dict(id=r.MODEL,endpoints=[dict(tag=r.TAG,provider_name=r.PROVIDER,
        model_id=r.MODEL,quantization="fp8",name=r.PROVIDER+" | "+r.MODELS[1],status=0,
        max_completion_tokens=16384,context_length=40960,
        supported_parameters=["reasoning","max_tokens","temperature","top_p","top_k","min_p",
            "seed","presence_penalty","repetition_penalty","response_format"],
        pricing=dict(prompt="0.00000008",completion="0.00000028"))]))


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    class Public:
        def open(self,url,timeout):
            assert url==r.METADATA_URL
            return io.BytesIO(json.dumps(metadata()).encode())
    monkeypatch.setattr(r.t,"opener",lambda:Public())
    monkeypatch.setattr(r,"seed_audit",lambda:dict(planned=list(range(r.SEED,r.SEED+8))+list(range(r.SEED+100,r.SEED+108)),overlap=[]))
    root=tmp_path/"run";r.prepare(root)
    budget=tmp_path/"budget";budget.mkdir()
    atomic(budget/"authority.json",dict(budget_id=BUDGET_ID,cap_usd="10.00",credit_purchases_authorized=False))
    return root,budget


def trace(answer,gid,mode="valid"):
    frames=[dict(id=gid,model=r.MODELS[1],provider=r.PROVIDER,
        choices=[dict(index=0,delta=dict(reasoning="fabricated reasoning"),finish_reason=None)]),
        dict(choices=[dict(index=0,delta=dict(content=answer),finish_reason="stop")]),
        dict(choices=[],usage=dict(prompt_tokens=100,completion_tokens=100,cost=.0001,
            completion_tokens_details=dict(reasoning_tokens=80)))]
    if mode in ("channel_only","no_reasoning"):frames[2]["usage"]["completion_tokens_details"]={}
    if mode=="tokens_only":frames[0]["choices"][0]["delta"]={}
    if mode=="no_reasoning":frames[0]["choices"][0]["delta"]={}
    if mode=="bad_reasoning_count":frames[2]["usage"]["completion_tokens_details"]["reasoning_tokens"]=200
    if mode=="identity":frames[0]["provider"]="Wrong"
    if mode=="model":frames[0]["model"]="different/model"
    if mode=="length":frames[1]["choices"][0]["finish_reason"]="length"
    if mode=="high_cost":frames[2]["usage"]["cost"]=.20
    lines=[]
    for frame in frames:lines+=["data: "+json.dumps(frame),""]
    if mode!="transport":lines+=["data: [DONE]",""]
    return dict(started_unix=time.time(),ended_unix=time.time(),http_status=200,
        generation_header=None,lines=lines,line_count=len(lines),byte_count=sum(map(len,lines)),
        error_type=None,secret_redacted=False)


def fake(prepared,mode="valid"):
    requests=[];lookups=[];lock=threading.Lock();contexts={c["seed"]:c for c in [x["context"] for x in r.cases()]}
    def send(wire,secret):
        req=json.loads(wire);c=contexts[req["seed"]]
        with lock:requests.append(req);gid="fabricated-"+str(len(requests))
        if mode=="exception":raise RuntimeError("simulated")
        if c["kind"]=="numeric":
            value=dict(answer=(not c["expected"] if mode=="wrong_numeric" and type(c["expected"]) is bool else c["expected"]))
        else:
            value=dict(projects=c["dominant_projects"] or dict(A="A0",B="B0"),first="A",coalition=[6,0,2,4],message="fabricated")
            if mode=="wrong_control":value["projects"]=dict(A="A0",B="B0")
            if c["stage"]=="response":value["support"]=False
        answer="bad json" if mode=="invalid" and c["kind"]=="compound" else json.dumps(value)
        return trace(answer,gid,"transport" if mode=="one_failure" and c["id"]=="gate-0" else mode)
    def lookup(gid,secret):
        lookups.append(gid);missing=mode=="missing_receipt"
        return dict(http_status=404 if missing else 200,error_type="HTTPError" if missing else None,
            secret_redacted=False,started_unix=time.time(),ended_unix=time.time(),data=None if missing else dict(
                id=gid,model=r.MODELS[1],provider_name=r.PROVIDER,
                total_cost=.20 if mode=="high_cost" else (.0002 if mode=="cost_mismatch" else .0001)))
    terminal=r.execute(*prepared,secret="fixture-secret",send=send,lookup=lookup,sleep=lambda _:None)
    return terminal,requests,lookups


@pytest.mark.parametrize("mode",["valid","channel_only","bad_reasoning_count"])
def test_success_and_native_evidence(prepared,mode):
    terminal,requests,lookups=fake(prepared,mode);a=r.audit(*prepared)
    assert a["gate_passed"] and len(requests)==len(lookups)==16
    assert a["numeric_correct"]==8 and a["controls_correct"]==4 and a["valid_actions"]==16
    assert Decimal(a["accounted_usd"])==Decimal(".0016")
    assert all(q["seed"]<r.SEED+100 for q in requests[:8])
    if mode=="channel_only":
        assert all(x["result"]["native_reasoning"]["reported_tokens"] is None for x in a["assignments"])
    if mode=="bad_reasoning_count":
        assert all(not x["result"]["native_reasoning"]["count_consistent_with_completion"] for x in a["assignments"])
        assert all(x["result"]["native_reasoning"]["quantitative_reasoning_tokens"] is None for x in a["assignments"])
    with pytest.raises(ValueError,match="already started"):r.execute(*prepared)


def test_settings_prompts_choices_and_budget():
    cases=r.cases();assert len(cases)==16
    assert sum(Decimal(c["reserved_usd"]) for c in cases)<=r.CAP
    for i,c in enumerate(cases):
        q=c["request"]
        assert q["reasoning"]==dict(enabled=True,exclude=False) and q["max_tokens"]==16384
        assert q["temperature"]==.6 and q["response_format"]==dict(type="json_object")
        assert q["provider"]["only"]==[r.TAG] and not q["provider"]["allow_fallbacks"]
        original=r.f.predecessor.gate_cases()[i] if i<8 else r.f.contexts()[i-8]
        assert q["messages"]==original["messages"] and "expected" not in q
        assert c["input_token_bound"]+r.CONFIG["output_bound"]<=r.CONTEXT


@pytest.mark.parametrize("mode",["invalid","wrong_control"])
def test_compound_failure_not_resampled(prepared,mode):
    terminal,requests,_=fake(prepared,mode);a=r.audit(*prepared)
    assert terminal["numeric_gate_passed"] and len(requests)==16
    assert not a["gate_passed"] and not terminal["global_safety_stop"]


def test_numeric_failure_blocks_compound(prepared):
    terminal,requests,_=fake(prepared,"wrong_numeric");a=r.audit(*prepared)
    assert len(requests)==8 and not terminal["numeric_gate_passed"]
    assert len(a["assignments"])==16 and not a["gate_passed"]
    assert all(x["status"]=="not_started" for x in a["assignments"][8:])


@pytest.mark.parametrize("mode",["no_reasoning","tokens_only","identity","model","length","transport","missing_receipt","exception","cost_mismatch"])
def test_safety_failures_no_retry(prepared,mode):
    terminal,requests,_=fake(prepared,mode);a=r.audit(*prepared)
    assert terminal["global_safety_stop"] and 0<len(requests)<=8
    assert len(a["assignments"])==16 and not a["gate_passed"]
    assert all(x["status"]=="not_started" for x in a["assignments"][8:])
    if mode in ("missing_receipt","exception","cost_mismatch"):
        b=r.Ledger(prepared[1]).snapshot();assert b["pending"]+b["uncertified"]>0


def test_one_failure_preserved_not_global(prepared):
    terminal,requests,_=fake(prepared,"one_failure");a=r.audit(*prepared)
    assert len(requests)==8 and terminal["transport_failures"]==1
    assert not terminal["global_safety_stop"] and not a["gate_passed"]


def test_shared_budget_not_reset(prepared):
    ledger=r.Ledger(prepared[1]);ledger.allocate("earlier","10")
    ledger.reserve("earlier","old","9.999","0"*64)
    terminal,requests,_=fake(prepared);a=r.audit(*prepared)
    assert not requests and terminal["global_safety_stop"] and a["accounted_usd"]=="0"


@pytest.mark.parametrize("change",["answer","request","cost","manifest","source"])
def test_tampering_rejected(prepared,change):
    fake(prepared);root,budget=prepared;path=next((root/"calls").glob("*.json"));row=r.t.load(path)
    if change=="answer":row["result"]["action"]={};atomic(path,row)
    if change=="request":row["request"]["reasoning"]["enabled"]=False;atomic(path,row)
    if change=="cost":
        path=budget/"entries"/(r.STAGE+"-"+row["id"]+".json");row=r.t.load(path)
        row["accounted_usd"]="0";atomic(path,row)
    if change=="manifest":
        path=root/"manifest.json";row=r.t.load(path);row["protocol"]["max_calls"]=17;atomic(path,row)
    if change=="source":
        path=root/"sources.json";row=r.t.load(path);row[next(iter(row))]+="\n# changed\n";atomic(path,row)
    with pytest.raises(ValueError):r.audit(*prepared)


@pytest.mark.parametrize("field,value",[("provider_name","Wrong"),("context_length",1000),("max_completion_tokens",4000),("supported_parameters",[]),("status",1)])
def test_metadata_rejects_wrong_endpoint(field,value):
    data=metadata();data["data"]["endpoints"][0][field]=value
    with pytest.raises(ValueError):r.check_metadata(data)


def test_price_ceiling():
    data=metadata();data["data"]["endpoints"][0]["pricing"]["completion"]="0.01"
    with pytest.raises(ValueError,match="price"):r.check_metadata(data)


def test_above_reservation_charge_is_retained_and_stops(prepared):
    terminal,requests,_=fake(prepared,"high_cost")
    assert terminal["global_safety_stop"] and 0<len(requests)<=4
    ledger=r.Ledger(prepared[1]).snapshot()
    assert Decimal(ledger["accounted_usd"])==Decimal(".20")*len(requests)
    assert ledger["uncertified"]==len(requests)
    with pytest.raises(ValueError,match="stage cap"):r.audit(*prepared)


@pytest.mark.parametrize("corruption",["duplicate_done","after_done","multiple_models","bad_choice"])
def test_stream_rejects_ambiguous_or_malformed_evidence(corruption):
    stream=trace('{"answer":6}',"fake")
    if corruption=="duplicate_done":stream["lines"]+=["data: [DONE]",""]
    if corruption=="after_done":stream["lines"]+=['data: {"choices":[]}',""]
    if corruption=="multiple_models":stream["lines"][2:2]=['data: {"model":"different/model"}',""]
    if corruption=="bad_choice":stream["lines"]=[x.replace('"index": 0','"index": 1') for x in stream["lines"]]
    assert not r.service.stream_summary(stream,r.CONFIG)["complete"]


def test_seed_audit_covers_unexecuted(tmp_path):
    base=tmp_path/"results/paper3/old";base.mkdir(parents=True)
    atomic(base/"manifest.json",dict(seed_audit=dict(planned=[320107])))
    with pytest.raises(ValueError,match="overlap"):r.seed_audit(tmp_path)


def test_bounded_http_error_privacy_and_single_post(monkeypatch):
    secret="sk-or-v1-"+"q"*48;requests=[]
    raw=json.dumps(dict(error=dict(message="invalid request params",metadata=dict(provider_name="DeepInfra")),
        user_id="private-account",account_id="account-secret",user="user_private",
        credential=secret,note="Bearer private-token",padding="x"*5000)).encode()
    class Reject:
        def open(self,req,timeout):
            requests.append(req)
            raise urllib.error.HTTPError(req.full_url,400,"bad",{},io.BytesIO(raw))
    monkeypatch.setattr(r.t,"opener",lambda:Reject())
    out=r.service.transmit("{}",secret);text=json.dumps(out)
    assert len(requests)==1 and out["http_error_body_truncated"] and out["secret_redacted"]
    for value in (secret,"private-account","account-secret","user_private","private-token"):assert value not in text
    assert "invalid request params" in text and "DeepInfra" in text


@pytest.mark.parametrize("mode",["valid","wrong_numeric","invalid","missing_receipt","exception"])
def test_actual_isolated_archive_replay(prepared,tmp_path,mode):
    fake(prepared,mode);target=tmp_path/"portable";archive=tmp_path/"export.zip"
    info=r.export(*prepared,target,archive)
    fresh=tmp_path/"extracted"
    with zipfile.ZipFile(archive) as z:z.extractall(fresh)
    process=subprocess.run([sys.executable,"-I","-S",str(fresh/"code/experiments/paper3_qwen_channel_gate.py"),
        str(fresh),"--replay","--expected-protocol",info["protocol"]],env={},capture_output=True,text=True)
    assert process.returncode==0,process.stderr
    report=json.loads(process.stdout);assert report.pop("portable_replay")["exact_report_match"]
    assert report==r.audit(*prepared)

