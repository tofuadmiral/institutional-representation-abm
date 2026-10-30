"""Offline fabricated tests for the compound-action interface diagnostic."""
from copy import deepcopy
from decimal import Decimal
import io
import itertools
import json
import threading
import time

import jsonschema
import pytest

from experiments import paper3_contracts_format as r
from tests.test_paper3_coalition_contracts_runner import metadata, trace
from paper3.pivot_b_budget import BUDGET_ID, atomic


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    data=metadata();data["data"]["endpoints"][0]["supported_parameters"] += ["structured_outputs","response_format"]
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


def fabricated(prepared,mode="valid"):
    requests=[];guard=threading.Lock();lookups=[]
    def transmit(wire,secret):
        req=json.loads(wire);context=r.contexts()[req["seed"]-r.SEED]
        with guard:requests.append(req);gid="format-test-"+str(len(requests))
        answer=dict(projects=context["dominant_projects"] or dict(A="A0",B="B0"),
                    first="B",coalition=[6,4,2,0],message="test")
        if context["stage"]=="response":answer["support"]=False
        if mode=="wrong_control":answer["projects"]=dict(A="A0",B="B0")
        raw=json.dumps(answer)
        if mode=="bad_all" or (mode=="bad_plain" and "response_format" not in req):raw="invalid JSON"
        if mode=="exception":raise RuntimeError("fabricated failure")
        result=trace(raw,gid,time.time(),reasoning=0 if mode=="no_reasoning" else 80,
                     finish="length" if mode=="length" else "stop")
        if mode=="transport" or (mode=="one_transport" and context["id"]=="context-0" and "response_format" not in req):
            result["lines"]=result["lines"][:-2]
        if mode=="identity":
            result["lines"]=[line.replace(r.t.PROVIDER,"WrongProvider") for line in result["lines"]]
        return result
    def lookup(gid,secret):
        lookups.append(gid)
        missing=mode=="missing_receipt"
        return dict(http_status=404 if missing else 200,error_type="HTTPError" if missing else None,
            secret_redacted=False,started_unix=time.time(),ended_unix=time.time(),data=None if missing else dict(
                id=gid,model=r.t.MODELS[1],provider_name=r.t.PROVIDER,total_cost=.0001))
    obj=r.Runner(*prepared,secret="fabricated_secret",transmit=transmit,lookup=lookup,sleep=lambda _:None)
    return obj.run(),requests,lookups


@pytest.mark.parametrize("stage",["draft","response","final"])
def test_schema_preserves_every_legal_offer_and_order(stage):
    schema=r.action_schema(stage);jsonschema.Draft202012Validator.check_schema(schema)
    validator=jsonschema.Draft202012Validator(schema)
    for a,b,first in itertools.product(("A0","A1"),("B0","B1"),("A","B")):
        for coalition in itertools.chain([()],itertools.permutations(range(7),4)):
            value=dict(projects=dict(A=a,B=b),first=first,coalition=list(coalition),message="")
            if stage=="response":value["support"]=False
            validator.validate(value)
            assert r.game.parse_action(json.dumps(value),stage)==value
    if stage=="response":
        value["support"]=True;validator.validate(value)


@pytest.mark.parametrize("coalition",[[0],[0,1,2],[0,1,2,3,4],[0,1,2,25],[0,1,2,True],[0,1,2,2]])
def test_schema_rejects_illegal_coalitions(coalition):
    action=dict(projects=dict(A="A0",B="B0"),first="A",coalition=coalition,message="")
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(action,r.action_schema("draft"))
    with pytest.raises(ValueError):r.game.parse_action(json.dumps(action),"draft")


def test_only_format_differs_within_pair_and_order_is_balanced():
    assigned=r.cases()
    assert len(assigned)==16 and len({c["id"] for c in assigned})==16
    assert sum(Decimal(c["reserved_usd"]) for c in assigned)<=Decimal(".50")
    for ctx in r.contexts():
        p=r.request_for(ctx,"plain");s=r.request_for(ctx,"json_schema")
        assert s.pop("response_format")["json_schema"]["schema"]==r.action_schema(ctx["stage"])
        assert s==p and p["reasoning"]==dict(enabled=True,exclude=False)
        assert p["plugins"]==[] and not p["provider"]["allow_fallbacks"]
    for wave in range(2):
        rows=[c for c in assigned if c["wave"]==wave]
        assert len(rows)==8 and sum(c["mode"]=="plain" for c in rows)==4
    for i in range(8):assert assigned[i]["context"]==assigned[i+8]["context"] and assigned[i]["mode"]!=assigned[i+8]["mode"]


def test_contexts_have_eight_fixed_compound_cases_and_four_independent_controls():
    ctx=r.contexts()
    assert [c["stage"] for c in ctx]==["draft"]*4+["response"]*4
    assert len([c for c in ctx if c["dominant_projects"] is not None])==4
    assert set(c["arm"] for c in ctx)==set(r.game.ARMS)
    for c in ctx:
        assert c["messages"]==r.game.messages(c["profile"],c["arm"],c["actor"],c["stage"],c["events"])
        if c["dominant_projects"]:
            for principal in c["profile"]["utilities"]:
                for category,project in c["dominant_projects"].items():
                    assert all(principal[project]>principal[other] for other in r.game.PROJECTS[category] if other!=project)
        # Gate answers live in metadata, never in the response schema.
        assert "dominant" not in json.dumps(r.action_schema(c["stage"]))


def test_complete_fake_run_and_no_restart(prepared):
    terminal,requests,lookups=fabricated(prepared)
    audit=r.audit(*prepared)
    assert len(requests)==len(lookups)==audit["calls"]==16
    assert not terminal["global_safety_stop"]
    assert audit["selected_format"]=="plain" and all(g["passed"] for g in audit["format_gate"].values())
    assert Decimal(audit["accounted_usd"])==Decimal(".0016")
    with pytest.raises(ValueError,match="already started"):r.Runner(*prepared).run()


def test_invalid_plain_retained_no_retries_and_schema_selected(prepared):
    terminal,requests,_=fabricated(prepared,"bad_plain")
    audit=r.audit(*prepared)
    assert len(requests)==16 and not terminal["global_safety_stop"]
    assert audit["format_gate"]["plain"]["valid"]==0
    assert audit["selected_format"]=="json_schema"
    assert len(audit["assignments"])==16


@pytest.mark.parametrize("mode",["bad_all","wrong_control"])
def test_syntax_or_control_failure_cannot_pass(prepared,mode):
    terminal,requests,_=fabricated(prepared,mode)
    audit=r.audit(*prepared)
    assert len(requests)==16 and not terminal["global_safety_stop"]
    assert audit["selected_format"] is None
    if mode=="wrong_control":
        assert all(v["valid"]==8 and v["controls_correct"]==2 for v in audit["format_gate"].values())


@pytest.mark.parametrize("mode",["no_reasoning","length","identity","transport","missing_receipt","exception"])
def test_safety_failures_stop_admissions_keep_assignments(prepared,mode):
    terminal,requests,_=fabricated(prepared,mode)
    report=r.audit(*prepared)
    assert terminal["global_safety_stop"] and len(requests)<16
    assert len(report["assignments"])==16 and report["selected_format"] is None
    if mode in ("missing_receipt","exception"):
        snapshot=r.Ledger(prepared[1]).snapshot()
        assert snapshot["pending"]+snapshot["uncertified"]>0
        assert Decimal(snapshot["accounted_usd"])>Decimal(".025")


def test_single_transport_failure_keeps_rest_without_replacement(prepared):
    terminal,requests,_=fabricated(prepared,"one_transport")
    report=r.audit(*prepared)
    assert len(requests)==16 and terminal["transport_failures"]==1 and not terminal["global_safety_stop"]
    assert report["format_gate"]["plain"]["valid"]==7
    assert report["selected_format"]=="json_schema"


def test_new_stage_cannot_reset_shared_budget(prepared):
    ledger=r.Ledger(prepared[1]);ledger.allocate("other_stage","10")
    ledger.reserve("other_stage","other-request","9.99","0"*64)
    terminal,requests,_=fabricated(prepared)
    report=r.audit(*prepared)
    assert not requests and terminal["global_safety_stop"]
    assert report["accounted_usd"]=="0" and r.Ledger(prepared[1]).snapshot()["accounted_usd"]=="9.99"


@pytest.mark.parametrize("mutation",["request","result","ledger"])
def test_evidence_tamper_rejected(prepared,mutation):
    fabricated(prepared)
    path=next((prepared[0]/"calls").glob("*.json"));row=r.load(path)
    if mutation=="request":row["request"]["max_tokens"]=10;atomic(path,row)
    elif mutation=="result":row["result"]["action"]["first"]="A";atomic(path,row)
    else:
        entry=prepared[1]/"entries"/(r.STAGE+"-"+row["id"]+".json")
        data=r.load(entry);data["accounted_usd"]="0";atomic(entry,data)
    with pytest.raises(ValueError):r.audit(*prepared)


def test_freeze_and_metadata_tampering_rejected(prepared):
    m=r.load(prepared[0]/"manifest.json");m["protocol"]["max_calls"]=20
    atomic(prepared[0]/"manifest.json",m)
    with pytest.raises(ValueError,match="specification"):r.verify(prepared[0])
    with pytest.raises(ValueError,match="structured"):r.check_metadata(metadata())


def test_old_or_unexecuted_seed_is_not_reused(tmp_path):
    target=tmp_path/"results/paper3/old";target.mkdir(parents=True)
    atomic(target/"manifest.json",dict(seed_audit=dict(planned_unique=[r.SEED])))
    with pytest.raises(ValueError,match="overlap"):r.seed_audit(tmp_path)


def test_score_keeps_duplicate_keys_and_bad_member_invalid():
    c=r.cases()[0]
    for raw in ('{"first":"A","first":"B"}', '{"projects":{"A":"A0","B":"B0"},"first":"A","coalition":[0,1,2,25],"message":""}'):
        stream=trace(raw,"fake",time.time())
        row=dict(stream=stream,receipts=[dict(http_status=200,error_type=None,secret_redacted=False,
            data=dict(id="fake",model=r.t.MODELS[1],provider_name=r.t.PROVIDER,total_cost=.0001))],
            input_token_bound=1000,reserved_usd=".03")
        row["assessment"]=r.t.assess(row)
        assert not r.score(row,c)["valid_action"]
