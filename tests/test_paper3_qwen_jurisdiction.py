"""Offline full-institution execution, failure isolation and exact portable replay."""
from copy import deepcopy
from decimal import Decimal
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import zipfile

import pytest
from experiments import paper3_qwen_jurisdiction as r
from paper3.pivot_b_budget import BUDGET_ID,atomic
from tests.test_paper3_qwen_channel_gate import metadata,trace


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    class Public:
        def open(self,url,timeout):
            assert url==r.gate.METADATA_URL
            return io.BytesIO(json.dumps(metadata()).encode())
    monkeypatch.setattr(r.t,"opener",lambda:Public())
    monkeypatch.setattr(r,"seed_audit",lambda:dict(planned_unique=sorted({s["seed_base"]+j for s in r.schedule() for j in range(30)}),overlap=[]))
    root=tmp_path/"run";r.prepare(root)
    budget=tmp_path/"budget";budget.mkdir()
    atomic(budget/"authority.json",dict(budget_id=BUDGET_ID,cap_usd="10.00",credit_purchases_authorized=False))
    return root,budget


def fake(prepared,mode="valid"):
    requests=[];lookups=[];guard=threading.Lock()
    chosen=r.schedule()[0]
    def send(wire,secret):
        req=json.loads(wire)
        with guard:requests.append(req);gid="fixture-"+str(len(requests))
        record=json.loads(req["messages"][1]["content"].split("\n")[0])
        text=req["messages"][1]["content"]
        if "Choose your opening" in text or "Choose your final" in text or "Respond to the draft" in text:
            value=dict(projects=dict(A="A0",B="B0"),first="A",coalition=[0,1,3,4],message="fabricated")
            if "Respond to the draft" in text:value["support"]=True
        elif "Decide whether to consent" in text:value=dict(consent=True)
        else:value=dict(vote=False)
        if mode=="exception":raise RuntimeError("simulated")
        only_chosen=req["seed"]==chosen["seed_base"] and r.game.ARM_RULES[chosen["arm"]] in req["messages"][0]["content"]
        raw="invalid json" if mode=="one_invalid" and only_chosen else json.dumps(value)
        stream_mode="transport" if mode=="transport" or (mode=="one_transport" and only_chosen) else mode
        return trace(raw,gid,stream_mode)
    def lookup(gid,secret):
        lookups.append(gid);missing=mode=="missing_receipt"
        return dict(http_status=404 if missing else 200,error_type="HTTPError" if missing else None,
            secret_redacted=False,started_unix=time.time(),ended_unix=time.time(),
            data=None if missing else dict(id=gid,model=r.gate.MODELS[1],provider_name=r.gate.PROVIDER,total_cost=.0001))
    terminal=r.execute(*prepared,secret="fixture-secret",send=send,lookup=lookup,sleep=lambda _:None)
    return terminal,requests,lookups


def replay_archive(prepared,tmp_path):
    target=tmp_path/"portable";archive=tmp_path/"archive.zip"
    info=r.export(*prepared,target,archive);fresh=tmp_path/"extracted"
    with zipfile.ZipFile(archive) as z:z.extractall(fresh)
    process=subprocess.run([sys.executable,"-I","-S",str(fresh/"code/experiments/paper3_qwen_jurisdiction.py"),
        str(fresh),"--replay","--expected-protocol",info["protocol"]],env={},capture_output=True,text=True)
    assert process.returncode==0,process.stderr
    report=json.loads(process.stdout);assert report.pop("portable_replay")["exact_report_match"]
    assert report==r.audit(*prepared)


def test_full_720_call_institution_and_actual_isolated_replay(prepared,tmp_path):
    terminal,requests,lookups=fake(prepared);report=r.audit(*prepared)
    assert report["feasibility_passed"] and report["complete_episodes"]==24 and report["new_gate_calls"]==0
    assert not report["primary_discovery_screen_passed"]  # Equal final offers are not a scientific success.
    assert len(requests)==len(lookups)==720 and not terminal["global_safety_stop"]
    assert len(report["contrasts"])==24 and all(c["paired_complete"] for c in report["contrasts"])
    assert Decimal(report["accounted_usd"])==Decimal(".0720")
    for assignment in report["assignments"]:
        out=assignment["outcome"];assert len(out["utility"])==len(out["normalized_regret"])==7
        assert out["utility"]==r.design.canonical_utilities(assignment["display_outcome"]["utility"], assignment["assignment"]["form"])
        if assignment["assignment"]["arm"]=="public_promise":
            assert out["enforcement_changes"]==0 and out["passed"]==[]
        else:assert out["enforcement_changes"]==8 and len(out["passed"])==2
    # All agents see the same public history within a sealed decision stage.
    for q in requests:
        record=json.loads(q["messages"][1]["content"].split("\n")[0])
        assert "Respond to the draft" not in q["messages"][1]["content"] or len(record["events"])==1
        assert q["reasoning"]==dict(enabled=True,exclude=False)
        assert q["seed"]>=350000 and q["max_tokens"]==16384
    replay_archive(prepared,tmp_path)
    with pytest.raises(ValueError,match="already started"):r.execute(*prepared)
    # Tamper only with a fabricated outcome, then restore the test artifact.
    path=next((prepared[0]/"episodes").glob("*.json"));saved=r.load(path);changed=deepcopy(saved)
    changed["outcome"]["utility"][0]+=1;atomic(path,changed)
    with pytest.raises(ValueError,match="replay"):r.audit(*prepared)
    atomic(path,saved)
    decision=next((prepared[0]/"decisions").glob("*.json"));saved=r.load(decision);changed=deepcopy(saved)
    changed["case"]["context"]["actor"]=99;atomic(decision,changed)
    with pytest.raises(RuntimeError,match="role changed"):r.audit(*prepared)


@pytest.mark.parametrize("mode",["one_invalid","one_transport"])
def test_one_episode_failure_is_not_resampled_or_global(prepared,mode):
    terminal,requests,_=fake(prepared,mode);report=r.audit(*prepared)
    assert len(requests)==691 and report["complete_episodes"]==23
    assert not terminal["global_safety_stop"] and not report["feasibility_passed"]
    failed=[x for x in report["assignments"] if x["status"]!="complete"]
    assert len(failed)==1 and failed[0]["observed_calls"]==1 and failed[0]["outcome"] is None
    for c in report["contrasts"]:
        if not c["paired_complete"]:
            assert c["behavioral_and_distributional"] is None
            assert len(c["all_principal_utility_difference_bounds"])==7


@pytest.mark.parametrize("mode",["transport","missing_receipt","exception","identity","no_reasoning"])
def test_global_failures_preserve_all_assignments_and_archive(prepared,tmp_path,mode):
    terminal,requests,_=fake(prepared,mode);report=r.audit(*prepared)
    assert terminal["global_safety_stop"] and not report["feasibility_passed"]
    assert 0<len(requests)<30 and len(report["assignments"])==24
    assert all(x["outcome"] is None for x in report["assignments"])
    assert all(c["regret_difference_bounds"]==["-1","1"] for c in report["contrasts"])
    if mode in ("missing_receipt","exception"):assert r.Ledger(prepared[1]).snapshot()["pending"]+r.Ledger(prepared[1]).snapshot()["uncertified"]>0
    replay_archive(prepared,tmp_path)


def test_existing_budget_is_not_reset(prepared):
    ledger=r.Ledger(prepared[1]);ledger.allocate("old","10")
    ledger.reserve("old","already-reserved","9.999","0"*64)
    terminal,requests,_=fake(prepared);a=r.audit(*prepared)
    assert not requests and terminal["global_safety_stop"] and a["accounted_usd"]=="0"


def test_fresh_seed_schedule_and_exact_native_configuration():
    assignments=r.schedule()
    assert len(assignments)==len({s["id"] for s in assignments})==24
    for block in range(8):
        subset=[s for s in assignments if s["block"]==block]
        assert {s["arm"] for s in subset}==set(r.game.ARMS)
        assert {s["seed_base"] for s in subset}=={350000+100*block}
    for assignment in assignments:
        profile=r.design.display_profile(r.design.fixtures()[assignment["fixture_index"]],assignment["form"])
        messages=r.design.labelled_messages(r.game.messages(profile,assignment["arm"],profile["proposer"],"draft",[]))
        c=r.make_case(assignment,profile["proposer"],"draft",messages,0)
        assert c["request"]==r.gate.request_for(messages,assignment["seed_base"])
        assert c["input_token_bound"]+r.gate.CONFIG["output_bound"]<=r.gate.CONTEXT


def test_inherited_gate_is_replayed_not_assumed():
    evidence=r.prerequisite()
    assert evidence["channel"]["report"]["gate_passed"] and evidence["channel"]["report"]["calls"]==16
    assert evidence["factual_report"]["by_encoding"]["principal_id_map"]["passed"]
    assert not evidence["factual_report"]["both_presentations_passed"]
    assert evidence["channel"]["protocol"]==r.GATE_PROTOCOL
    assert evidence["native_template"]==r.request_for([],0)


@pytest.mark.parametrize("change",["native","source","schedule","cap"])
def test_freeze_tampering_before_any_call(prepared,change):
    root,_=prepared
    if change=="source":
        p=root/"sources.json";x=r.load(p);x[next(iter(x))]+="\nchanged\n"
    else:
        p=root/"manifest.json";x=r.load(p)
        if change=="native":x["protocol"]["native_template"]["max_tokens"]=10
        if change=="schedule":x["protocol"]["assignments"][0]["seed_base"]=1
        if change=="cap":x["protocol"]["cap_usd"]="2"
    atomic(p,x)
    with pytest.raises(ValueError):r.verify(root)
    assert not list((root/"calls").iterdir())


def test_seed_inventory_includes_unexecuted_positions(tmp_path):
    base=tmp_path/"results/paper3/old";base.mkdir(parents=True)
    atomic(base/"manifest.json",dict(seed_audit=dict(planned_unique=[350029])))
    with pytest.raises(ValueError,match="overlap"):r.seed_audit(tmp_path)


def test_missingness_bounds_cover_all_finite_utilities():
    reports=[dict(assignment=s,status="not_started",outcome=None) for s in r.schedule()]
    for contrast in r.contrasts(reports,r.design.fixtures()):
        p=next(p for p in r.design.fixtures() if p["id"]==contrast["fixture"])
        possible=[r.game.utility_vector(p,o) for o in r.game.all_outcomes()]
        for x in possible:
            for y in possible:
                assert all(low<=b-a<=high for a,b,(low,high) in zip(x,y,contrast["all_principal_utility_difference_bounds"]))


def test_stale_metadata_fails_before_admission(prepared):
    root,budget=prepared
    when=r.load(root/"manifest.json")["protocol"]["metadata_observed_unix"]
    with pytest.raises(ValueError,match="stale"):
        r.execute(root,budget,clock=lambda:when+3601)
    assert not list((root/"calls").iterdir()) and not list((root/"sessions").iterdir())


def test_stage_limit_not_only_global_limit(prepared):
    root,budget=prepared; ledger=r.Ledger(budget)
    ledger.allocate(r.STAGE,r.CAP)
    # Reserve nearly the whole stage under an unrelated simulated request id.
    # The execution must not send; no audit claim is made for this synthetic extra reservation.
    ledger.reserve(r.STAGE,r.STAGE+"-reserved-fixture",".9999","0"*64)
    terminal,requests,_=fake(prepared)
    assert not requests and terminal["global_safety_stop"]
    assert r.Ledger(budget).snapshot()["accounted_usd"]=="0.9999"
