"""Offline transport, failure, native-reasoning and replay checks. No API key."""
import copy
from decimal import Decimal
import io
import json
from pathlib import Path
import threading
import time

import pytest

from experiments import paper3_coalition_contracts as r
from paper3.pivot_b_budget import BUDGET_ID, atomic


def metadata():
    t=r.transport
    return {"data":{"id":t.MODEL,"endpoints":[dict(tag="atlas-cloud/fp8",provider_name=t.PROVIDER,
        model_id=t.MODEL,quantization="fp8",name="AtlasCloud | "+t.MODELS[1],status=0,
        max_completion_tokens=147456,supported_parameters=["reasoning","max_tokens","temperature",
        "top_p","top_k","min_p","seed","presence_penalty","repetition_penalty"],
        pricing={"prompt":"0.00000026","completion":"0.00000038"})]}}


@pytest.fixture
def setup(tmp_path,monkeypatch):
    class Public:
        def open(self,url,timeout):
            assert url==r.transport.METADATA_URL
            return io.BytesIO(json.dumps(metadata()).encode())
    monkeypatch.setattr(r.transport,"opener",lambda:Public())
    monkeypatch.setattr(r,"seed_audit",lambda:dict(overlap=[],planned_unique=list(range(316000,316008))))
    run=tmp_path/"run"; r.prepare(run)
    budget=tmp_path/"budget";budget.mkdir()
    (budget/"authority.json").write_text(json.dumps(dict(budget_id=BUDGET_ID,cap_usd="10.00",credit_purchases_authorized=False)))
    return run,budget


def trace(answer,gid,now,reasoning=80,finish="stop"):
    frames=[dict(id=gid,model=r.transport.MODELS[1],provider=r.transport.PROVIDER,
                 choices=[dict(index=0,delta={"reasoning":"fabricated private reasoning"},finish_reason=None)]),
            dict(choices=[dict(index=0,delta={"content":answer},finish_reason=finish)]),
            dict(choices=[],usage=dict(prompt_tokens=100,completion_tokens=100,cost=.0001,
                                      completion_tokens_details={"reasoning_tokens":reasoning}))]
    lines=[]
    for f in frames: lines += ["data: "+json.dumps(f),""]
    lines += ["data: [DONE]",""]
    return dict(started_unix=now,ended_unix=now,http_status=200,generation_header=None,lines=lines,
        line_count=len(lines),byte_count=sum(len(x)+1 for x in lines),first_line_unix=now,
        last_line_unix=now,error_type=None,secret_redacted=False)


def fake(setup,mode="valid"):
    root,budget=setup
    guard=threading.Lock(); serial=[0]; requests=[]; lookups=[]
    def transmit(wire,secret):
        request=json.loads(wire)
        with guard:
            serial[0]+=1;gid="fixture-"+str(serial[0]);requests.append(request)
        is_gate=request["seed"] < r.EPISODE_SEED
        if is_gate:
            expected=next(c["expected"] for c in r.gate_cases() if c["seed"] == request["seed"])
            answer=json.dumps(dict(answer=("wrong" if mode=="gate_wrong" else expected)))
        else:
            text=request["messages"][1]["content"]
            if "Choose your opening" in text or "Choose your final" in text or "Respond to the draft" in text:
                value=dict(projects=dict(A="A0",B="B0"),first="A",coalition=[0,1,3,4],message="fixture")
                if "Respond to the draft" in text: value["support"]=True
            elif "Decide whether to consent" in text: value=dict(consent=True)
            else: value=dict(vote=False)
            answer=json.dumps(value)
        if not is_gate and mode=="content_invalid":answer="not-json"
        result=trace(answer,gid,time.time(),reasoning=0 if mode=="no_reasoning" else 80)
        if not is_gate and mode=="transport_fail": result["lines"]=result["lines"][:-2]
        if not is_gate and mode=="one_failure" and request["seed"]==r.EPISODE_SEED and "nonbinding agreement" in request["messages"][0]["content"]:
            result["lines"]=result["lines"][:-2]
        return result
    def lookup(gid,secret):
        lookups.append(gid)
        if mode=="receipt_missing":
            return dict(http_status=404,error_type="HTTPError",data=None,secret_redacted=False,
                        started_unix=time.time(),ended_unix=time.time())
        return dict(http_status=200,error_type=None,secret_redacted=False,
                    data=dict(id=gid,model=r.transport.MODELS[1],provider_name=r.transport.PROVIDER,total_cost=.0001),
                    started_unix=time.time(),ended_unix=time.time())
    obj=r.Runner(root,budget,secret="fixture_secret",transmit=transmit,lookup=lookup,sleep=lambda _:None)
    terminal=obj.run()
    return terminal,requests,lookups


def test_fully_fabricated_end_to_end_replay(setup):
    terminal,requests,lookups=fake(setup)
    result=r.audit(*setup)
    assert terminal["gate_passed"]
    assert len(requests)==len(lookups)==result["calls"]==278
    assert result["complete_episodes"]==9
    assert Decimal(result["accounted_usd"])==Decimal(".0278")
    assert all(c["paired_complete"] for c in result["contrasts"])
    assert all(not c["behavioral_and_distributional"]["final_projects_changed"] for c in result["contrasts"])
    assert r.Ledger(setup[1]).snapshot()["pending"]==0
    with pytest.raises(ValueError,match="already started"):
        r.Runner(setup[0],setup[1],secret="unused").run()


def test_failed_gate_never_launches_institutions(setup):
    terminal,requests,lookups=fake(setup,"gate_wrong")
    result=r.audit(*setup)
    assert not terminal["gate_passed"] and len(requests)==8
    assert result["complete_episodes"]==0 and result["gate_correct"]==0
    assert len(result["assignments"])==9
    assert all(x["regret_difference_bounds"]==["-1","1"] for x in result["contrasts"])


def test_invalid_content_keeps_all_assignments_without_retry(setup):
    terminal,requests,lookups=fake(setup,"content_invalid")
    result=r.audit(*setup)
    assert len(requests)==17 and result["complete_episodes"]==0
    assert not terminal["global_safety_stop"]
    assert all(a["status"]=="incomplete" and a["observed_calls"]==1 for a in result["assignments"])


def test_one_transport_failure_does_not_kill_other_episodes(setup):
    terminal,requests,lookups=fake(setup,"one_failure")
    result=r.audit(*setup)
    assert terminal["transport_failures"]==1 and not terminal["global_safety_stop"]
    assert result["complete_episodes"]==8 and result["calls"]==249
    assert sum(not c["paired_complete"] for c in result["contrasts"])==1


def test_repeated_transport_failure_stops_new_calls(setup):
    terminal,requests,lookups=fake(setup,"transport_fail")
    result=r.audit(*setup)
    assert terminal["transport_failures"]>=2 and terminal["global_safety_stop"]
    assert result["complete_episodes"]==0 and len(requests)<=12
    assert all(a["observed_calls"]<=1 for a in result["assignments"])


@pytest.mark.parametrize("mode",["receipt_missing","no_reasoning"])
def test_uncertified_or_nonreasoning_gate_stops(mode,setup):
    terminal,requests,lookups=fake(setup,mode)
    result=r.audit(*setup)
    assert not terminal["gate_passed"] and terminal["global_safety_stop"]
    assert len(requests)<=8 and result["complete_episodes"]==0
    if mode=="receipt_missing":assert r.Ledger(setup[1]).snapshot()["uncertified"]>0


def test_gate_types_are_not_coerced():
    assert not r.gate_correct('{"answer":1}',True)
    assert not r.gate_correct('{"answer":true,"answer":false}',False)
    assert not r.gate_correct('```json\n{"answer":true}\n```',True)
    assert r.gate_correct('{"answer":true}',True)


def test_reasoning_not_mixed_into_final_content():
    stream=trace('{"answer":true}',"gen-x",time.time())
    assert r.final_content(stream)=='{"answer":true}'


def test_source_or_manifest_tampering_rejected(setup):
    root,_=setup
    m=r.load(root/"manifest.json");m["protocol"]["stage_cap_usd"]="5"
    atomic(root/"manifest.json",m)
    with pytest.raises(ValueError,match="budget"):
        r.verify(root)


def test_paired_seeds_and_neutral_common_rules():
    planned=r.schedule()
    assert len(planned)==9 and len({x["id"] for x in planned})==9
    for i in range(3):
        pair=[x for x in planned if x["fixture_index"]==i]
        assert len({x["seed_base"] for x in pair})==1
        assert {x["arm"] for x in pair}==set(r.game.ARMS)
    assert len(r.gate_cases())==8
    assert all(r.request_for(c["messages"],c["seed"])["reasoning"]["enabled"] for c in r.gate_cases())


def test_gate_native_reasoning_cannot_be_falsely_reported(setup):
    fake(setup)
    root,budget=setup
    path=root/"calls/gate-0.json"
    row=r.load(path);row["native_reasoning_present"]=False;atomic(path,row)
    entry=budget/"entries"/(r.STAGE+"-gate-0.json")
    value=r.load(entry);value["evidence_sha256"]=r.sha(path.read_bytes());atomic(entry,value)
    with pytest.raises(ValueError,match="reasoning report"):
        r.audit(*setup)


def test_failed_prefix_request_tampering_not_accepted_as_parse_error(setup):
    fake(setup,"content_invalid")
    root,budget=setup
    key=r.schedule()[0]["id"]+"-00"
    path=root/"calls"/(key+".json")
    row=r.load(path);row["request"]["messages"][1]["content"] += " changed"
    wire=r.canonical(row["request"]);bound=len(wire.encode())+1024
    reserve=(bound*r.transport.PRICE_IN+r.transport.OUTPUT_BOUND*r.transport.PRICE_OUT)/Decimal(1000000)
    row.update(request_text=wire,request_sha256=r.sha(wire.encode()),input_token_bound=bound,reserved_usd=str(reserve))
    atomic(path,row)
    entry=budget/"entries"/(r.STAGE+"-"+key+".json")
    value=r.load(entry);value.update(request_sha256=row["request_sha256"],reserved_usd=str(reserve),evidence_sha256=r.sha(path.read_bytes()));atomic(entry,value)
    with pytest.raises(RuntimeError,match="episode request changed"):
        r.audit(*setup)
