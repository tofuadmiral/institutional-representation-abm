"""Prospective strict-schema feasibility gate; no previous output is repaired."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import random
import sys
import time

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments import paper3_contracts_format as f
from experiments import paper3_qwen_channel_gate as predecessor
from paper3 import coalition_contracts as game
from paper3 import coalition_mandate_diagnostic as factual
from paper3 import coalition_jurisdiction_design as jurisdiction
from paper3 import hosted_reasoning_channel_calls as service
from paper3.pivot_b_budget import Ledger,atomic
from paper3.source_closure import closure

t=f.t;require=t.require;STAGE="pivot_b_qwen_schema_gate_v1";CAP=Decimal("0.10");SEED=351000;WORKERS=4
MODEL="qwen/qwen3-32b";MODELS=[MODEL,MODEL+"-04-28"];PROVIDER="DeepInfra";TAG="deepinfra/fp8"
CONFIG=dict(models=MODELS,provider=PROVIDER,output_bound=16400)
PRICE_IN=Decimal("0.08");PRICE_OUT=Decimal("0.28");CONTEXT=40960
METADATA_URL="https://openrouter.ai/api/v1/models/qwen/qwen3-32b/endpoints"
BUDGET=f.BUDGET



def action_schema(stage):
    if stage in ("draft","response","final"):
        schema=f.action_schema(stage)
        schema["properties"]["coalition"]={"type":"array", "enum":[[],*[list(c) for c in game.COALITIONS]]}
        return schema
    if stage in ("consent","first_vote","second_vote"):
        key="consent" if stage=="consent" else "vote"
        return dict(type="object",properties={key:dict(type="boolean")},required=[key],additionalProperties=False)
    raise ValueError("unknown action stage")


def fact_schema():
    utilities={k:dict(type="integer") for k in ("A0","A1","B0","B1")}
    props=dict(own_utilities=dict(type="object",properties=utilities,
                                  required=list(utilities),additionalProperties=False),
               package_utility=dict(type="integer"),
               member_active=dict(type="boolean"),universal_active=dict(type="boolean"),
               bound_if_active=dict(type="boolean"))
    return dict(type="object",properties=props,required=list(props),additionalProperties=False)


def request_for(messages,seed,kind,stage=None):
    request=predecessor.request_for(messages,seed)
    schema=fact_schema() if kind=="fact" else action_schema(stage)
    request["response_format"]=dict(type="json_schema",json_schema=dict(
        name="paper3_"+("fact" if kind=="fact" else stage),strict=True,schema=schema))
    return request


def check_metadata(metadata):
    data=metadata["data"];require(data["id"]==MODEL,"metadata model")
    selected=[e for e in data["endpoints"] if e.get("tag")==TAG]
    require(len(selected)==1,"endpoint missing/ambiguous");e=selected[0]
    require(e["provider_name"]==PROVIDER and e["model_id"]==MODEL and e["quantization"]=="fp8","routing metadata")
    require(e["name"].split(" | ")[-1]==MODELS[1],"dated identity")
    require(e["status"]==0 and e["max_completion_tokens"]>=16384 and e["context_length"]>=CONTEXT,"endpoint capacity/status")
    required={"reasoning","max_tokens","temperature","top_p","top_k","min_p","seed","presence_penalty","repetition_penalty","response_format","structured_outputs"}
    require(required<=set(e["supported_parameters"]),"native parameters unsupported")
    for key,bound in (("prompt",PRICE_IN),("completion",PRICE_OUT)):
        amount=Decimal(e["pricing"][key])*1000000
        require(amount.is_finite() and 0<=amount<=bound,"price ceiling")
    return e


def action_contexts():
    """Fixed cases: two historical failures, two controls, and four later stages."""
    history_root=ROOT/"results/paper3/pivot_b_qwen_jurisdiction_v1/calls"
    source_ids=("fixture-1-block-0-member_enforcement-00",
                "fixture-0-block-1-member_enforcement-02")
    contexts=[]
    for key in source_ids:
        row=t.load(history_root/(key+".json"))
        require(row["context"]["stage"] in ("draft","response"),"historical stage")
        contexts.append(dict(id="historical-"+key,kind="action",stage=row["context"]["stage"],
            messages=row["request"]["messages"],dominant_projects=None,history_source=key))
    old=f.contexts()
    for i in (2,3):
        c=old[i]
        contexts.append(dict(id="aligned-control-"+str(i),kind="action",stage=c["stage"],
            messages=jurisdiction.labelled_messages(c["messages"]),
            dominant_projects=c["dominant_projects"],history_source=None))
    p=jurisdiction.fixtures()[0];arm="member_enforcement";actor=1
    offer=dict(projects=dict(A="A0",B="B0"),first="A",coalition=[0,1,2,3],message="Proposed exchange.")
    draft=dict(type="draft",actor=p["proposer"],action=offer)
    response_action=dict(**offer,support=True)
    responses=dict(type="response",responses=[dict(actor=i,action=response_action) for i in game.ACTORS])
    final=dict(type="final",actor=p["proposer"],action=offer)
    consent=dict(type="consent",approvals=[True]*7)
    first=dict(type="first_vote",project="A0",requested=[True]*7,executed=[True]*7,
               passed=True,due_members=[0,1,2,3],enforced_members=[0,1,2,3],changed_ballots=[])
    contexts += [
        dict(id="final-offer",kind="action",stage="final",messages=jurisdiction.labelled_messages(
            game.messages(p,arm,p["proposer"],"final",[draft,responses])),dominant_projects=None,history_source=None),
        dict(id="consent",kind="action",stage="consent",messages=jurisdiction.labelled_messages(
            game.messages(p,arm,actor,"consent",[draft,responses,final])),dominant_projects=None,history_source=None),
        dict(id="first-vote",kind="action",stage="first_vote",messages=jurisdiction.labelled_messages(
            game.messages(p,arm,actor,"first_vote",[draft,responses,final,consent])),dominant_projects=None,history_source=None),
        dict(id="second-vote",kind="action",stage="second_vote",messages=jurisdiction.labelled_messages(
            game.messages(p,arm,actor,"second_vote",[draft,responses,final,consent,first])),dominant_projects=None,history_source=None),
    ]
    require(len(contexts)==8,"eight action cases")
    return contexts


def cases():
    facts=[(0,0),(0,1),(0,2),(0,6),(1,0),(1,1),(1,2),(1,6)]
    contexts=[]
    for i,(profile,actor) in enumerate(facts):
        c=factual.context(profile,actor,"principal_id_map")
        contexts.append(dict(id="fact-"+str(i),kind="fact",stage=None,seed=SEED+i,
                             messages=c["messages"],expected=c["expected"],dominant_projects=None))
    for i,c in enumerate(action_contexts()):
        contexts.append(dict(**c,seed=SEED+8+i))
    random.Random(351999).shuffle(contexts)
    result=[]
    for context in contexts:
        request=request_for(context["messages"],context["seed"],context["kind"],context["stage"]);wire=t.canonical(request)
        bound=len(wire.encode())+1024
        require(bound+CONFIG["output_bound"]<=CONTEXT,"conservative context bound")
        reserve=(bound*PRICE_IN+CONFIG["output_bound"]*PRICE_OUT)/Decimal(1000000)
        result.append(dict(id=context["id"],context=context,request=request,request_text=wire,
            request_sha256=t.sha(wire.encode()),input_token_bound=bound,reserved_usd=str(reserve)))
    require(len(result)==16 and sum(Decimal(c["reserved_usd"]) for c in result)<=CAP,"stage reservation")
    return result


def score(row,case):
    result=dict(usable=False,valid_action=False,facts_correct=None,factual_fields=None,
                dominant_projects_correct=None,action=None,native_reasoning=None,failure=None)
    if row.get("instrument_error") or "assessment" not in row:
        result["failure"]="instrument_or_unfinished";return result
    a=service.assess(row,CONFIG);s=a["stream"];native=service.native_evidence(s)
    requested=row["request"].get("reasoning")==dict(enabled=True,exclude=False)
    usable=a["passed"] and s["finish_reasons"]==["stop"] and native["present"] and requested
    result.update(usable=usable,native_reasoning=native)
    if not usable:result["failure"]="transport_reasoning_or_completion";return result
    raw=f.predecessor.final_content(row["stream"]);context=case["context"]
    try:
        if context["kind"]=="fact":
            content=factual.score_content(raw,context["expected"])
            result.update(valid_action=content["valid"],facts_correct=content["correct"],
                          factual_fields=content["fields"],failure=content["failure"])
            if content["valid"]:result["action"]=json.loads(raw)
        else:
            action=game.parse_action(raw,context["stage"])
            result.update(valid_action=True,action=action)
            if context["dominant_projects"] is not None:result["dominant_projects_correct"]=action["projects"]==context["dominant_projects"]
    except (ValueError,TypeError,KeyError) as exc:result["failure"]=type(exc).__name__
    return result


def seed_audit(root=ROOT):
    planned=set(range(SEED,SEED+16));observed=set();inventory=[]
    def walk(v,k=""):
        if isinstance(v,dict):
            for key,x in v.items():walk(x,key)
        elif isinstance(v,list):
            for x in v:walk(x,k)
        elif type(v) is int and ("seed" in k.lower() or k in ("planned","planned_unique")):observed.add(v)
    for base,dirs,files in os.walk(Path(root)/"results/paper3"):
        dirs[:]=[d for d in dirs if not any(x in d for x in ("portable","bundle","export","__pycache__","code"))]
        for name in files:
            path=Path(base)/name
            if name=="manifest.json" or (path.parent.name=="calls" and name.endswith(".json")):
                row=t.load(path);walk(row.get("request",row))
                inventory.append((str(path.relative_to(root)),t.sha(path.read_bytes())))
    # Enumerate unstarted schedules as well as saved requests. These are not new admissions.
    expanded={a["seed_base"]+j for a in jurisdiction.schedule(tuple(350000+100*i for i in range(8))) for j in range(30)}
    expanded|={281000+1000*i+j for i in range(12) for j in range(25)}
    expanded|={301000+1000*i+100*r+j for i in range(2) for r in range(2) for j in range(25)}
    expanded|={311000+1000*i+j for i in range(4) for j in range(25)}
    expanded|=set(range(310000,310008))|set(range(315000,315004))
    require(not planned&(observed|expanded),"seed overlap")
    return dict(planned=sorted(planned),overlap=sorted(planned&observed),historical_files=len(inventory),inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()))


def specification():
    return dict(name=STAGE,cases=cases(),workers=4,max_calls=16,cap_usd=str(CAP),budget_cap_usd="10.00",
        pre_stage_accounted_usd="0.801122991",cumulative_ceiling_usd="0.901122991",model_configuration=CONFIG,
        reasoning_evidence="Enabled request AND nonempty native reasoning channel; matching bounded charges and receipts. Inconsistent reported reasoning counts are flagged, never summed.",
        predecessor_protocol="2662df0588dab7ec6cbc77edca12148cfad27e8f02bb616ba46333d90ea6bc67",
        instrumentation_change="Strict stage-specific JSON Schema on the same endpoint; all35 four-person coalitions plus empty remain available. Historical failed prompt histories are engineering contexts, not repaired old episodes.",
        inference_retries=0,receipt_offsets_seconds=[0,20,40,60],http_error_body_max_bytes=4096,
        failure_rule="Any invalid content, unsupported schema/HTTP400, two transport/accounting failures or identity/source/budget/instrument breach stops NEW admissions; already admitted requests finish. No restart, repair, retry, replacement or fallback. Retain all assignments and reservations.",
        gate="All16 assigned calls complete, certified and native-reasoning; all8 actions locally valid, all8 factual answers exact, both aligned controls dominant. Engineering gate only, no institutional or causal inference.",
        limitations="One selected serialization form, eight factual and eight selected action histories, no population evidence. A pass cannot rescue earlier failed runs or authorize the separate720-call pilot.")


def prepare(root):
    root=Path(root);require(not root.exists(),"fresh directory required")
    seeds=seed_audit()
    with t.opener().open(METADATA_URL,timeout=20) as response:metadata=json.load(response)
    endpoint=check_metadata(metadata);require("response_format" in endpoint["supported_parameters"],"JSON format unsupported")
    history=ROOT/"results/paper3/pivot_b_qwen_jurisdiction_v1/calls"
    paths=closure(ROOT,[Path(__file__),ROOT/"paper3/source_closure.py",ROOT/"analysis/paper3_contracts_archive.py",BUDGET/"authority.json",
                       ROOT/"tests/test_paper3_qwen_schema_gate.py",
                       history/"fixture-1-block-0-member_enforcement-00.json",
                       history/"fixture-0-block-1-member_enforcement-02.json"])
    snapshot={str(p.relative_to(ROOT)):p.read_text() for p in paths}
    protocol=dict(**specification(),seed_audit=seeds,endpoint_metadata=metadata,metadata_observed_unix=time.time())
    m=dict(protocol=protocol,sources={k:t.sha(v.encode()) for k,v in snapshot.items()})
    root.mkdir(parents=True,exist_ok=False)
    for name in ("calls","sessions"):(root/name).mkdir()
    atomic(root/"sources.json",snapshot);atomic(root/"manifest.json",m)
    return t.sha(t.canonical(m).encode())


def verify(root,code_root=ROOT):
    root=Path(root);m=t.load(root/"manifest.json");snap=t.load(root/"sources.json")
    require(set(snap)==set(m["sources"]),"source inventory")
    for rel,want in m["sources"].items():
        require(not Path(rel).is_absolute() and ".." not in Path(rel).parts,"unsafe source")
        require(t.sha((Path(code_root)/rel).read_bytes())==t.sha(snap[rel].encode())==want,"frozen source changed: "+rel)
    require(all(m["protocol"].get(k)==v for k,v in specification().items()),"specification changed")
    require(m["protocol"]["seed_audit"]["planned"]==list(range(SEED,SEED+16)) and not m["protocol"]["seed_audit"]["overlap"],"seed audit")
    require("response_format" in check_metadata(m["protocol"]["endpoint_metadata"])["supported_parameters"],"metadata format")
    return m,t.sha(t.canonical(m).encode())


def execute(root,ledger_root=BUDGET,secret=None,send=None,lookup=None,clock=time.time,sleep=time.sleep):
    root=Path(root);m,protocol=verify(root)
    require(0<=clock()-m["protocol"]["metadata_observed_unix"]<=3600,"stale metadata")
    with (root/"writer.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(not list((root/"sessions").iterdir()) and not list((root/"calls").iterdir()),"already started; no restart")
        ledger=Ledger(ledger_root)
        require(Decimal(ledger.snapshot()["accounted_usd"])==Decimal("0.801122991"),"pre-stage accounting changed")
        ledger.allocate(STAGE,CAP)
        atomic(root/"sessions/start.json",dict(protocol=protocol,pid=os.getpid(),started_unix=clock()))
        calls=service.Calls(root,ledger_root,STAGE,16,lambda:verify(root),score,CONFIG,secret,send,lookup,clock,sleep)
        assigned=m["protocol"]["cases"]
        def one(case):
            status=calls.one(case)
            if status["status"]=="recorded":
                row=t.load(root/"calls"/(case["id"]+".json"))
                result=row["result"]
                if (row["stream"].get("http_status")==400 or not result["usable"] or
                    not result["valid_action"] or result["facts_correct"] is False or
                    result["dominant_projects_correct"] is False):
                    calls.stop.set()
            return status
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results=list(pool.map(one,assigned))
        terminal=dict(protocol=protocol,results=results,global_safety_stop=calls.stop.is_set(),transport_failures=calls.transport_failures,
                      budget=ledger.snapshot(),ended_unix=clock())
        atomic(root/"sessions/terminal.json",terminal);return terminal


def audit(root,ledger_root=BUDGET):
    root=Path(root);m,protocol=verify(root);terminal=t.load(root/"sessions/terminal.json")
    require(t.load(root/"sessions/start.json")["protocol"]==terminal["protocol"]==protocol,"terminal protocol")
    reports,cost=service.audit_records(root,ledger_root,STAGE,protocol,m["protocol"]["cases"],terminal,score,CONFIG)
    require(cost<=CAP,"stage cap exceeded")
    require(Decimal("0.801122991")+cost<=Decimal("0.901122991"),"cumulative ceiling exceeded")
    results=[r["result"] or {} for r in reports]
    valid=sum(bool(r.get("usable") and r.get("valid_action")) for r in results)
    correct=sum(r.get("dominant_projects_correct") is True for r in results)
    facts=sum(r.get("facts_correct") is True for r in results)
    gate=valid==16 and facts==8 and correct==2 and not terminal["global_safety_stop"] and all(r["status"]=="recorded" for r in reports)
    return dict(protocol=protocol,assignments=reports,calls=len(list((root/"calls").glob("*.json"))),
        valid_actions=valid,facts_correct=facts,controls_correct=correct,gate_passed=gate,accounted_usd=str(cost),
        global_safety_stop=terminal["global_safety_stop"],
        caveat=specification()["limitations"])


def archive_helpers():
    import importlib.util
    spec=importlib.util.spec_from_file_location("b_archive",ROOT/"analysis/paper3_contracts_archive.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def export(root,ledger_root,target,destination,secret=None):
    h=archive_helpers();root,ledger_root,target=map(lambda p:Path(p).resolve(),(root,ledger_root,target))
    require((root/"sessions/terminal.json").is_file(),"not terminal")
    require(not target.exists() and not Path(destination).exists(),"archive destination exists")
    with (root/"writer.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with Ledger(ledger_root).locked():
            report=audit(root,ledger_root);m,protocol=verify(root)
            content={"code/"+p:v.encode() for p,v in t.load(root/"sources.json").items()}
            for prefix,directory in (("run",root),("ledger",ledger_root)):
                for p in directory.rglob("*"):
                    require(not p.is_symlink(),"symlink in source")
                    if p.is_file() and p.suffix==".json":content[prefix+"/"+str(p.relative_to(directory))]=p.read_bytes()
            content["expected_report.json"]=(json.dumps(report,sort_keys=True,indent=2)+"\n").encode()
    content["README.md"]=("# Qwen strict-schema gate\n\nEight factual and eight selected stage-specific action contexts; all failures, controls and cost reservations retained. "
        "No old response is repaired/replaced; no institutional effect claimed. From a fresh extracted directory run:\n\n"
        "`python3 -I -S code/experiments/paper3_qwen_schema_gate.py . --replay --expected-protocol "+protocol+"`\n\n"
        "Standard library, no key/network/weights/original checkout. Every original audit field is compared. "
        "Review trusted code; hashes prove consistency, not authenticity or generalization. Ledger is an archival snapshot.\n").encode()
    for rel,data in content.items():h.safe(target,rel);h.credentials(data,secret)
    metadata=dict(format=h.FORMAT,experiment_family=STAGE,protocol=protocol,
                  files={rel:t.sha(data) for rel,data in sorted(content.items())})
    target.mkdir(parents=True,exist_ok=False)
    for rel,data in content.items():
        p=h.safe(target,rel);p.parent.mkdir(parents=True,exist_ok=True)
        with p.open("xb") as stream:stream.write(data)
    with (target/"bundle.json").open("x") as stream:json.dump(metadata,stream,sort_keys=True,indent=2)
    return dict(protocol=protocol,files=len(content),sha256=h.archive(target,destination))


def replay(root,expected):
    h=archive_helpers();root=Path(root).resolve();m=h.verify_bundle(root,expected)
    require(m["experiment_family"]==STAGE,"wrong archive")
    require(ROOT==root/"code","run replay from extracted bundled code")
    sys.addaudithook(h.offline_guard)
    require(verify(root/"run")[1]==expected,"frozen protocol changed")
    report=audit(root/"run",root/"ledger")
    require(report==t.load(root/"expected_report.json"),"original audit differs")
    report["portable_replay"]=dict(protocol=expected,exact_report_match=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("root",type=Path)
    group=p.add_mutually_exclusive_group(required=True)
    for mode in ("prepare","run","audit","export","replay"):group.add_argument("--"+mode,action="store_true")
    p.add_argument("--expected-protocol");p.add_argument("--target",type=Path);p.add_argument("--archive",type=Path);args=p.parse_args()
    if args.prepare:print(prepare(args.root));return
    if args.replay:
        require(args.expected_protocol,"expected protocol required")
        print(json.dumps(replay(args.root,args.expected_protocol),indent=2));return
    require(verify(args.root)[1]==args.expected_protocol,"expected protocol required")
    if args.export:
        require(args.target and args.archive,"export paths required")
        print(json.dumps(export(args.root,BUDGET,args.target,args.archive,t.read_key())));return
    print(json.dumps(audit(args.root) if args.audit else execute(args.root,secret=t.read_key()),indent=2))


if __name__=="__main__":main()
