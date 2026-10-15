"""Offline-only tests for the prospective structured-output gate."""
from decimal import Decimal
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from experiments import paper3_qwen35_darkbloom_gate as r
from paper3.pivot_b_budget import BUDGET_ID,Ledger,atomic


def metadata():
    return dict(data=dict(id=r.MODEL,endpoints=[dict(tag=r.TAG,provider_name=r.PROVIDER,
        model_id=r.MODEL,quantization="fp4",name=r.PROVIDER+" | "+r.MODELS[1],status=0,
        max_completion_tokens=32768,context_length=262144,
        supported_parameters=["reasoning","max_tokens","temperature","top_p","top_k",
            "seed","presence_penalty","repetition_penalty","response_format","structured_outputs"],
        pricing=dict(prompt="0.00000008",completion="0.00000075"))]))


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    class Public:
        def open(self,url,timeout):
            assert url==r.METADATA_URL
            return io.BytesIO(json.dumps(metadata()).encode())
    monkeypatch.setattr(r.t,"opener",lambda:Public())
    monkeypatch.setattr(r,"seed_audit",lambda:dict(planned=list(range(r.SEED,r.SEED+16)),overlap=[]))
    root=tmp_path/"run";r.prepare(root)
    budget=tmp_path/"budget";budget.mkdir()
    atomic(budget/"authority.json",dict(budget_id=BUDGET_ID,cap_usd="10.00",credit_purchases_authorized=False))
    ledger=Ledger(budget);ledger.allocate("prior",Decimal("10"))
    ledger.reserve("prior","prior-case",Decimal("0.827387951"),"0"*64)
    ledger.settle("prior-case",Decimal("0.827387951"),True,"1"*64)
    return root,budget


def trace(answer,gid,mode="valid"):
    frames=[dict(id=gid,model=r.MODELS[1],provider=r.PROVIDER,
        choices=[dict(index=0,delta=dict(reasoning="fabricated reasoning"),finish_reason=None)]),
        dict(choices=[dict(index=0,delta=dict(content=answer),finish_reason="stop")]),
        dict(choices=[],usage=dict(prompt_tokens=100,completion_tokens=100,cost=.0001,
            completion_tokens_details=dict(reasoning_tokens=80)))]
    if mode=="no_reasoning":frames[0]["choices"][0]["delta"]={}
    if mode=="wrong_provider":frames[0]["provider"]="wrong"
    lines=[]
    for frame in frames:lines += ["data: "+json.dumps(frame),""]
    lines += ["data: [DONE]",""]
    return dict(started_unix=time.time(),ended_unix=time.time(),http_status=200,
        generation_header=None,lines=lines,line_count=len(lines),byte_count=sum(map(len,lines)),
        error_type=None,secret_redacted=False)


def fake(prepared,mode="valid"):
    requests=[];lock=threading.Lock()
    contexts={c["context"]["seed"]:c["context"] for c in r.cases()}
    def send(wire,secret):
        request=json.loads(wire);c=contexts[request["seed"]]
        with lock:
            requests.append(request);gid="fabricated-"+str(len(requests))
        if mode=="http400":
            return dict(started_unix=time.time(),ended_unix=time.time(),http_status=400,
                generation_header=None,lines=[],line_count=0,byte_count=0,error_type="HTTPError",
                secret_redacted=False,http_error_body="unsupported schema")
        if c["kind"]=="fact":
            value=dict(c["expected"])
            if mode=="wrong_fact":value["package_utility"]+=1
        else:
            stage=c["stage"]
            if stage in ("draft","response","final"):
                value=dict(projects=c["dominant_projects"] or dict(A="A0",B="B0"),
                           first="A",coalition=[0,1,2,3],message="fabricated")
                if stage=="response":value["support"]=True
                if mode=="short_coalition":value["coalition"]=[0,1,2]
                if mode=="wrong_control" and c["dominant_projects"]:
                    value["projects"]=dict(A="A0",B="B0") if c["dominant_projects"]!=dict(A="A0",B="B0") else dict(A="A1",B="B1")
            else:value={"consent" if stage=="consent" else "vote":True}
        return trace(json.dumps(value),gid,mode)
    def lookup(gid,secret):
        return dict(http_status=200,error_type=None,secret_redacted=False,
            started_unix=time.time(),ended_unix=time.time(),
            data=dict(id=gid,model=r.MODELS[1],provider_name=r.PROVIDER,total_cost=.0001))
    terminal=r.execute(*prepared,secret="fabricated-secret",send=send,lookup=lookup,sleep=lambda _:None)
    return terminal,requests


def test_schema_exhaustive_and_settings():
    import jsonschema
    cases=r.cases();assert len(cases)==16
    assert sum(Decimal(c["reserved_usd"]) for c in cases)<=r.CAP
    assert {c["context"]["stage"] for c in cases if c["context"]["kind"]=="action"}=={
        "draft","response","final","consent","first_vote","second_vote"}
    assert sum(c["context"]["dominant_projects"] is not None for c in cases)==2
    coalition=r.action_schema("draft")["properties"]["coalition"]["enum"]
    assert len(coalition)==36 and [] in coalition and [0,1,2,3] in coalition
    assert all(len(x)==4 and x==sorted(x) for x in coalition if x)
    for case in cases:
        request=case["request"]
        assert request["response_format"]["type"]=="json_schema"
        assert request["response_format"]["json_schema"]["strict"] is True
        assert request["reasoning"]==dict(enabled=True,exclude=False)
        assert request["provider"]["only"]==[r.TAG] and not request["provider"]["allow_fallbacks"]
        assert request["plugins"]==[] and request["max_tokens"]==16384
        assert "min_p" not in request and request["temperature"]==1.0
        assert request["presence_penalty"]==1.5 and request["provider"]["quantizations"]==["fp4"]
        assert case["input_token_bound"]+r.CONFIG["output_bound"]<=r.CONTEXT
    assert all(r.game.parse_action(json.dumps({"projects":dict(A="A0",B="B0"),"first":"A",
        "coalition":c,"message":""}),"draft") for c in coalition)
    for stage in ("draft","response","final"):
        schema=r.action_schema(stage)
        jsonschema.Draft202012Validator.check_schema(schema)
        for members in coalition:
            for a in r.game.PROJECTS["A"]:
                for b in r.game.PROJECTS["B"]:
                    for first in ("A","B"):
                        value=dict(projects=dict(A=a,B=b),first=first,coalition=members,message="")
                        if stage=="response":value["support"]=False
                        jsonschema.validate(value,schema)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(dict(projects=dict(A="A0",B="B0"),first="A",
                coalition=[0,1,2],message="",**({"support":False} if stage=="response" else {})),schema)
    for stage,key in (("consent","consent"),("first_vote","vote"),("second_vote","vote")):
        schema=r.action_schema(stage)
        jsonschema.Draft202012Validator.check_schema(schema)
        for value in (True,False):jsonschema.validate({key:value},schema)
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate({key:1},schema)


def test_fabricated_success_and_no_restart(prepared):
    terminal,requests=fake(prepared)
    report=r.audit(*prepared)
    assert len(requests)==16 and report["gate_passed"]
    assert report["facts_correct"]==8 and report["valid_actions"]==16 and report["controls_correct"]==2
    assert Decimal(report["accounted_usd"])==Decimal(".0016")
    assert not terminal["global_safety_stop"]
    with pytest.raises(ValueError,match="already started"):r.execute(*prepared)


@pytest.mark.parametrize("mode",["wrong_fact","short_coalition","wrong_control","no_reasoning","wrong_provider","http400"])
def test_failure_stops_new_admissions_preserves_assignments(prepared,mode):
    terminal,requests=fake(prepared,mode);report=r.audit(*prepared)
    assert terminal["global_safety_stop"] and not report["gate_passed"]
    assert 0<len(requests)<=16 and len(report["assignments"])==16
    assert all(x["status"] in ("recorded","not_started") for x in report["assignments"])


@pytest.mark.parametrize("mode",["valid","http400","wrong_fact"])
def test_actual_isolated_archive_replay(prepared,tmp_path,mode):
    fake(prepared,mode)
    target=tmp_path/"portable";archive=tmp_path/"export.zip"
    info=r.export(*prepared,target,archive)
    fresh=tmp_path/"extracted"
    with zipfile.ZipFile(archive) as z:z.extractall(fresh)
    process=subprocess.run([sys.executable,"-I","-S",str(fresh/"code/experiments/paper3_qwen35_darkbloom_gate.py"),
        str(fresh),"--replay","--expected-protocol",info["protocol"]],
        env={},capture_output=True,text=True)
    assert process.returncode==0,process.stderr
    report=json.loads(process.stdout)
    assert report.pop("portable_replay")["exact_report_match"]
    assert report==r.audit(*prepared)


def test_seed_overlap_including_unstarted(tmp_path):
    base=tmp_path/"results/paper3/old";base.mkdir(parents=True)
    atomic(base/"manifest.json",dict(protocol=dict(cases=[dict(seed=355000)])))
    with pytest.raises(ValueError,match="overlap"):r.seed_audit(tmp_path)


def test_source_and_request_tampering_rejected(prepared):
    root,budget=prepared
    manifest=r.t.load(root/"manifest.json")
    manifest["protocol"]["cases"][0]["request"]["reasoning"]["enabled"]=False
    atomic(root/"manifest.json",manifest)
    with pytest.raises(ValueError):r.verify(root)


def test_shared_budget_baseline_is_exact(prepared):
    root,budget=prepared
    ledger=Ledger(budget);ledger.allocate("other",Decimal("1"))
    ledger.reserve("other","other-case",Decimal(".001"),"2"*64)
    ledger.settle("other-case",Decimal(".001"),True,"3"*64)
    with pytest.raises(ValueError,match="pre-stage accounting changed"):
        r.execute(root,budget,secret="fixture-secret")
    assert not list((root/"calls").glob("*.json"))


def test_endpoint_must_advertise_structured_outputs():
    value=metadata();value["data"]["endpoints"][0]["supported_parameters"].remove("structured_outputs")
    with pytest.raises(ValueError,match="parameters unsupported"):r.check_metadata(value)
