"""No-API execution, protocol, HTTP-error safety and portable replay tests."""
from decimal import Decimal
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
from experiments import paper3_contracts_json_mode as r
from paper3.pivot_b_budget import BUDGET_ID,atomic
from tests.test_paper3_coalition_contracts_runner import metadata,trace


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    data=metadata();data["data"]["endpoints"][0]["supported_parameters"].append("response_format")
    class Public:
        def open(self,url,timeout):
            assert url==r.t.METADATA_URL
            return io.BytesIO(json.dumps(data).encode())
    monkeypatch.setattr(r.t,"opener",lambda:Public())
    monkeypatch.setattr(r,"seed_audit",lambda:dict(planned=list(range(r.SEED,r.SEED+8)),overlap=[]))
    root=tmp_path/"run";r.prepare(root)
    budget=tmp_path/"budget";budget.mkdir()
    atomic(budget/"authority.json",dict(budget_id=BUDGET_ID,cap_usd="10.00",credit_purchases_authorized=False))
    return root,budget


def fake(prepared,mode="valid"):
    requests=[];guard=threading.Lock();lookups=[]
    def send(wire,secret):
        req=json.loads(wire);context=r.f.contexts()[req["seed"]-r.SEED]
        with guard:requests.append(req);gid="json-mode-"+str(len(requests))
        action=dict(projects=context["dominant_projects"] or dict(A="A0",B="B0"),
                    first="B",coalition=[6,0,2,4],message="fabricated")
        if context["stage"]=="response":action["support"]=False
        if mode=="wrong_control":action["projects"]=dict(A="A0",B="B0")
        raw=json.dumps(action) if mode!="invalid" else '{"coalition": [BAD]}'
        if mode=="exception":raise RuntimeError("failure")
        result=trace(raw,gid,time.time(),reasoning=0 if mode=="no_reasoning" else 80,finish="length" if mode=="length" else "stop")
        if mode=="transport" or (mode=="one_failure" and context["id"]=="context-0"):result["lines"]=result["lines"][:-2]
        if mode=="identity":result["lines"]=[line.replace(r.t.PROVIDER,"Wrong") for line in result["lines"]]
        return result
    def lookup(gid,secret):
        lookups.append(gid);missing=mode=="missing_receipt"
        return dict(http_status=404 if missing else 200,error_type="HTTPError" if missing else None,
            secret_redacted=False,started_unix=time.time(),ended_unix=time.time(),data=None if missing else dict(
                id=gid,model=r.t.MODELS[1],provider_name=r.t.PROVIDER,total_cost=.0001))
    terminal=r.execute(*prepared,secret="test-secret",send=send,lookup=lookup,sleep=lambda _:None)
    return terminal,requests,lookups


def test_complete_new_gate_and_no_restart(prepared):
    terminal,requests,lookups=fake(prepared);report=r.audit(*prepared)
    assert report["gate_passed"] and len(requests)==len(lookups)==8
    assert report["valid_actions"]==8 and report["controls_correct"]==4
    assert Decimal(report["accounted_usd"])==Decimal(".0008") and not terminal["global_safety_stop"]
    with pytest.raises(ValueError,match="already started"):r.execute(*prepared)


def test_contexts_and_native_settings_unchanged_except_format_seed():
    assert len(r.cases())==8 and len({c["id"] for c in r.cases()})==8
    assert sum(Decimal(c["reserved_usd"]) for c in r.cases())<=r.CAP
    for c in r.cases():
        request=dict(c["request"]);assert request.pop("response_format")=={"type":"json_object"}
        index=int(c["id"].split("-")[-1]);request["seed"]=r.f.SEED+index
        assert request==r.f.request_for(r.f.contexts()[index],"plain")
        assert request["reasoning"]==dict(enabled=True,exclude=False)


@pytest.mark.parametrize("mode",["invalid","wrong_control"])
def test_bad_content_or_wrong_controls_do_not_trigger_resampling(prepared,mode):
    terminal,requests,_=fake(prepared,mode);report=r.audit(*prepared)
    assert len(requests)==8 and not terminal["global_safety_stop"] and not report["gate_passed"]
    assert report["valid_actions"]==(0 if mode=="invalid" else 8)
    if mode=="wrong_control":assert report["controls_correct"]==2


@pytest.mark.parametrize("mode",["no_reasoning","length","transport","identity","missing_receipt","exception"])
def test_safety_failure_retains_all_assignments_and_reserves(prepared,mode):
    terminal,requests,_=fake(prepared,mode);report=r.audit(*prepared)
    assert terminal["global_safety_stop"] and len(requests)<8
    assert len(report["assignments"])==8 and not report["gate_passed"]
    if mode in ("exception","missing_receipt"):
        budget=r.Ledger(prepared[1]).snapshot()
        assert budget["pending"]+budget["uncertified"]>0


def test_one_transport_failure_no_global_stop_or_replacement(prepared):
    terminal,requests,_=fake(prepared,"one_failure");report=r.audit(*prepared)
    assert terminal["transport_failures"]==1 and not terminal["global_safety_stop"]
    assert len(requests)==8 and report["valid_actions"]==7 and not report["gate_passed"]


def test_global_budget_not_reset(prepared):
    ledger=r.Ledger(prepared[1]);ledger.allocate("earlier","10")
    ledger.reserve("earlier","earlier-request","9.99","0"*64)
    terminal,requests,_=fake(prepared)
    assert not requests and terminal["global_safety_stop"] and r.audit(*prepared)["accounted_usd"]=="0"


@pytest.mark.parametrize("change",["native","answer","cost"])
def test_provenance_tampering_detected(prepared,change):
    fake(prepared);path=next((prepared[0]/"calls").glob("*.json"));row=r.t.load(path)
    if change=="native":row["request"]["reasoning"]["enabled"]=False;atomic(path,row)
    elif change=="answer":row["result"]["action"]["first"]="A";atomic(path,row)
    else:
        path=prepared[1]/"entries"/(r.STAGE+"-"+row["id"]+".json");entry=r.t.load(path)
        entry["accounted_usd"]="0";atomic(path,entry)
    with pytest.raises(ValueError):r.audit(*prepared)


def test_seed_inventory_includes_unexecuted(prepared,tmp_path):
    base=tmp_path/"history/results/paper3/old";base.mkdir(parents=True)
    atomic(base/"manifest.json",dict(seed_audit=dict(planned=[r.SEED])))
    # Fixture patches module-level seed_audit; inspect the original function
    # in a separately loaded module, without changing any frozen source.
    import importlib.util
    spec=importlib.util.spec_from_file_location("seedtest",Path(r.__file__))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with pytest.raises(ValueError,match="overlap"):module.seed_audit(tmp_path/"history")


def test_http_body_capture_is_bounded_redacted_and_single_post(monkeypatch):
    secret="sk-or-v1-"+"q"*48;calls=[]
    body=('error: '+secret+' Bearer other-private-value '+('z'*5000)).encode()
    class Reject:
        def open(self,request,timeout):
            calls.append(request);assert request.method=="POST" and timeout==900
            raise urllib.error.HTTPError(request.full_url,400,"bad",{},io.BytesIO(body))
    monkeypatch.setattr(r.t,"opener",lambda:Reject())
    result=r.service.transmit('{}',secret)
    assert len(calls)==1 and result["http_status"]==400 and result["http_error_body_truncated"]
    assert secret not in json.dumps(result) and "other-private-value" not in json.dumps(result)
    assert result["secret_redacted"] and result["error_body_redacted"]
    assert "authorization" not in json.dumps(result).lower()


def test_http_body_unreadable_is_still_preserved_as_failure(monkeypatch):
    class Broken(io.BytesIO):
        def read(self,*args):raise OSError("unsafe details")
    class Reject:
        def open(self,request,timeout):raise urllib.error.HTTPError(request.full_url,400,"bad",{},Broken())
    monkeypatch.setattr(r.t,"opener",lambda:Reject())
    out=r.service.transmit('{}','test-secret')
    assert out["http_error_body_read_error"]=="OSError" and "unsafe" not in json.dumps(out)


def test_successful_sse_transport_is_unchanged(monkeypatch):
    data=trace('{"answer":true}',"trace-id",time.time());wire="\n".join(data["lines"]).encode()
    class Response(io.BytesIO):
        status=200;headers={"X-Generation-Id":"trace-id"}
    class Good:
        def open(self,request,timeout):return Response(wire)
    monkeypatch.setattr(r.t,"opener",lambda:Good())
    out=r.service.transmit('{}','test-secret')
    assert r.t.stream_summary(out)["complete"] and out["http_error_body"] is None


@pytest.mark.parametrize("mode",["valid","invalid","transport","missing_receipt","exception"])
def test_actual_isolated_archive_replay(prepared,tmp_path,mode):
    fake(prepared,mode);target=tmp_path/"portable";archive=tmp_path/"export.zip"
    info=r.export(*prepared,target,archive)
    fresh=tmp_path/"extracted"
    with zipfile.ZipFile(archive) as z:z.extractall(fresh)
    proc=subprocess.run([sys.executable,"-I","-S","code/experiments/paper3_contracts_json_mode.py",".",
        "--replay","--expected-protocol",info["protocol"]],cwd=fresh,env={},capture_output=True,text=True,check=True)
    report=json.loads(proc.stdout);assert report.pop("portable_replay")["exact_report_match"]
    assert report==r.audit(*prepared) and not list(fresh.rglob("*.pyc"))
    with pytest.raises(ValueError,match="exists"):r.export(*prepared,target,archive)


def test_live_archive_refused(prepared,tmp_path):
    with pytest.raises(ValueError,match="not terminal"):r.export(*prepared,tmp_path/"target",tmp_path/"out.zip")
