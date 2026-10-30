"""Fresh 56-case factual mandate diagnostic; no strategic or institutional claim."""
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
from paper3 import hosted_reasoning_channel_calls as service
from paper3.pivot_b_budget import Ledger,atomic
from paper3.source_closure import closure
from paper3 import coalition_mandate_diagnostic as design
from fractions import Fraction

t=f.t;require=t.require;STAGE="pivot_b_qwen_mandate_v1";CAP=Decimal("0.30");SEED_BASES=(324000,324100);WORKERS=4
SHUFFLE_SEED=324999
MODEL="qwen/qwen3-32b";MODELS=[MODEL,MODEL+"-04-28"];PROVIDER="DeepInfra";TAG="deepinfra/fp8"
CONFIG=dict(models=MODELS,provider=PROVIDER,output_bound=16400)
PRICE_IN=Decimal("0.08");PRICE_OUT=Decimal("0.28");CONTEXT=40960
METADATA_URL="https://openrouter.ai/api/v1/models/qwen/qwen3-32b/endpoints"
BUDGET=f.BUDGET



def request_for(messages,seed):
    return dict(model=MODEL,messages=messages,seed=seed,max_tokens=16384,
        temperature=.6,top_p=.95,top_k=20,min_p=0,presence_penalty=0,repetition_penalty=1,
        reasoning=dict(enabled=True,exclude=False),response_format=dict(type="json_object"),
        stream=True,usage=dict(include=True),plugins=[],
        provider=dict(only=[TAG],order=[TAG],allow_fallbacks=False,require_parameters=True,
            quantizations=["fp8"],max_price=dict(prompt=.08,completion=.28,request=0)))


def check_metadata(metadata):
    data=metadata["data"];require(data["id"]==MODEL,"metadata model")
    selected=[e for e in data["endpoints"] if e.get("tag")==TAG]
    require(len(selected)==1,"endpoint missing/ambiguous");e=selected[0]
    require(e["provider_name"]==PROVIDER and e["model_id"]==MODEL and e["quantization"]=="fp8","routing metadata")
    require(e["name"].split(" | ")[-1]==MODELS[1],"dated identity")
    require(e["status"]==0 and e["max_completion_tokens"]>=16384 and e["context_length"]>=CONTEXT,"endpoint capacity/status")
    required={"reasoning","max_tokens","temperature","top_p","top_k","min_p","seed","presence_penalty","repetition_penalty","response_format"}
    require(required<=set(e["supported_parameters"]),"native parameters unsupported")
    for key,bound in (("prompt",PRICE_IN),("completion",PRICE_OUT)):
        amount=Decimal(e["pricing"][key])*1000000
        require(amount.is_finite() and 0<=amount<=bound,"price ceiling")
    return e


def cases():
    contexts=design.cases(SEED_BASES)
    random.Random(SHUFFLE_SEED).shuffle(contexts)
    result=[]
    for context in contexts:
        request=request_for(context["messages"],context["seed"]);wire=t.canonical(request)
        bound=len(wire.encode())+1024
        require(bound+CONFIG["output_bound"]<=CONTEXT,"conservative context bound")
        reserve=(bound*PRICE_IN+CONFIG["output_bound"]*PRICE_OUT)/Decimal(1000000)
        result.append(dict(id=context["id"],context=context,request=request,request_text=wire,
            request_sha256=t.sha(wire.encode()),input_token_bound=bound,reserved_usd=str(reserve)))
    require(len(result)==56 and sum(Decimal(c["reserved_usd"]) for c in result)<=CAP,"stage reservation")
    return result


def score(row,case):
    result=dict(usable=False,valid_action=False,all_facts_correct=False,factual_fields=None,
                action=None,native_reasoning=None,failure=None)
    if row.get("instrument_error") or "assessment" not in row:
        result["failure"]="instrument_or_unfinished";return result
    a=service.assess(row,CONFIG);s=a["stream"];native=service.native_evidence(s)
    requested=row["request"].get("reasoning")==dict(enabled=True,exclude=False)
    usable=a["passed"] and s["finish_reasons"]==["stop"] and native["present"] and requested
    result.update(usable=usable,native_reasoning=native)
    if not usable:result["failure"]="transport_reasoning_or_completion";return result
    raw=service.final_content(row["stream"])
    content=design.score_content(raw,case["context"]["expected"])
    result.update(valid_action=content["valid"],all_facts_correct=content["correct"],
                  factual_fields=content["fields"],failure=content["failure"])
    if content["valid"]:result["action"]=json.loads(raw)
    return result


def seed_audit(root=ROOT):
    planned={c["context"]["seed"] for c in cases()};observed=set();inventory=[]
    def walk(v,k=""):
        if isinstance(v,dict):
            for key,x in v.items():walk(x,key)
        elif isinstance(v,list):
            for x in v:walk(x,k)
        elif type(v) is int and ("seed" in k.lower() or k in ("planned","planned_unique")):
            observed.add(v)
    for base,dirs,files in os.walk(Path(root)/"results/paper3"):
        dirs[:]=[d for d in dirs if not any(x in d for x in ("portable","bundle","export","__pycache__","code"))]
        for name in files:
            path=Path(base)/name
            if name=="manifest.json" or (path.parent.name=="calls" and name.endswith(".json")):
                row=t.load(path);walk(row.get("request",row))
                inventory.append((str(path.relative_to(root)),t.sha(path.read_bytes())))
    expanded={281000+1000*i+j for i in range(12) for j in range(25)}
    expanded|={301000+1000*i+100*r+j for i in range(2) for r in range(2) for j in range(25)}
    expanded|={311000+1000*i+j for i in range(4) for j in range(25)}
    expanded|=set(range(310000,310008))|set(range(315000,315004))
    overlap=planned&(observed|expanded)
    require(not overlap,"seed overlap")
    return dict(planned=sorted(planned),overlap=sorted(overlap),historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()),
                expanded_previous_schedules=sorted(expanded))


def specification():
    return dict(name=STAGE,cases=cases(),workers=WORKERS,max_calls=56,cap_usd=str(CAP),
        budget_cap_usd="10.00",model_configuration=CONFIG,seed_bases=list(SEED_BASES),
        shuffle_seed=SHUFFLE_SEED,inference_retries=0,receipt_offsets_seconds=[0,20,40,60],
        predecessor_protocol="c8a2cb6ad70e38567707cf9fe3c34b6b319cc44f8c4044ccc0599806eb778d53",
        design="Two selected conflict fixtures x seven principals x two table encodings x two requested seeds. Factual questions only; no inherited answers, new institutional trajectories or retrospective rescue.",
        content_rule="Strict complete JSON schema, exact integer utilities and boolean rules, no repair. Invalid and incorrect content retained without stopping other independent cases.",
        pass_rule="Each encoding passes only with all28 assigned responses usable, valid and entirely correct, with no global safety stop. Retain all56 assignments and per-field errors. Factual success is not strategic competence.",
        reasoning_rule="Require enabled request AND nonempty native channel. Retain inconsistent reported token counts as quantitatively unknown; require bounded matching stream/receipt charges.",
        failure_rule="Two transport/accounting failures or any identity/source/credential/budget/instrument breach stop admissions; finish already admitted calls. No restart, inference retry, replacement, repair or fallback.",
        bounds="Strict all-assigned accuracy treats failures as failures. Also report finite correctness bounds leaving unusable/invalid content unscored; these are not confidence intervals.",
        limitations="Identical payoff rows limit within-group identity tests; short factual questions differ from bargaining histories. Paired requested seeds do not guarantee common random draws. No institutional or population effect is established.")


def prepare(root):
    root=Path(root);require(not root.exists(),"fresh directory required")
    seeds=seed_audit()
    with t.opener().open(METADATA_URL,timeout=20) as response:metadata=json.load(response)
    endpoint=check_metadata(metadata);require("response_format" in endpoint["supported_parameters"],"JSON format unsupported")
    paths=closure(ROOT,[Path(__file__),ROOT/"paper3/source_closure.py",ROOT/"analysis/paper3_contracts_archive.py",BUDGET/"authority.json",
                       ROOT/"tests/test_paper3_qwen_mandate_diagnostic.py",ROOT/"tests/test_paper3_coalition_mandate_diagnostic.py",ROOT/"tests/test_paper3_qwen_channel_gate.py"])
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
    require(m["protocol"]["seed_audit"]["planned"]==sorted({c["context"]["seed"] for c in cases()}) and not m["protocol"]["seed_audit"]["overlap"],"seed audit")
    require("response_format" in check_metadata(m["protocol"]["endpoint_metadata"])["supported_parameters"],"metadata format")
    return m,t.sha(t.canonical(m).encode())


def execute(root,ledger_root=BUDGET,secret=None,send=None,lookup=None,clock=time.time,sleep=time.sleep):
    root=Path(root);m,protocol=verify(root)
    require(0<=clock()-m["protocol"]["metadata_observed_unix"]<=3600,"stale metadata")
    with (root/"writer.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(not list((root/"sessions").iterdir()) and not list((root/"calls").iterdir()),"already started; no restart")
        ledger=Ledger(ledger_root);ledger.allocate(STAGE,CAP)
        atomic(root/"sessions/start.json",dict(protocol=protocol,pid=os.getpid(),started_unix=clock()))
        calls=service.Calls(root,ledger_root,STAGE,56,lambda:verify(root),score,CONFIG,secret,send,lookup,clock,sleep)
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results=list(pool.map(calls.one,m["protocol"]["cases"]))
        terminal=dict(protocol=protocol,results=results,global_safety_stop=calls.stop.is_set(),
                      transport_failures=calls.transport_failures,budget=ledger.snapshot(),ended_unix=clock())
        atomic(root/"sessions/terminal.json",terminal);return terminal


def audit(root,ledger_root=BUDGET):
    root=Path(root);m,protocol=verify(root);terminal=t.load(root/"sessions/terminal.json")
    require(t.load(root/"sessions/start.json")["protocol"]==terminal["protocol"]==protocol,"terminal protocol")
    assignments=m["protocol"]["cases"]
    reports,cost=service.audit_records(root,ledger_root,STAGE,protocol,assignments,terminal,score,CONFIG)
    require(cost<=CAP,"stage cap exceeded")
    indexed={case["id"]:(case,row) for case,row in zip(assignments,reports)}
    summaries={}
    for encoding in design.ENCODINGS:
        selected=[(c,row) for c,row in indexed.values() if c["context"]["encoding"]==encoding]
        values=[row["result"] or {} for c,row in selected]
        valid=sum(bool(v.get("usable") and v.get("valid_action")) for v in values)
        correct=sum(v.get("all_facts_correct") is True for v in values)
        unscored=28-valid
        summaries[encoding]=dict(assigned=28,valid=valid,correct=correct,unscored=unscored,
            strict_all_assigned_accuracy=str(Fraction(correct,28)),
            factual_correctness_bounds=[str(Fraction(correct,28)),str(Fraction(correct+unscored,28))],
            component_correct={key:sum((v.get("factual_fields") or {}).get(key) is True for v in values)
                               for key in sorted(design.KEYS)},
            passed=correct==28 and not terminal["global_safety_stop"])
    pairs=[]
    for profile in (0,1):
        for actor in range(7):
            for repeat in (0,1):
                pair=[indexed[f"profile-{profile}-actor-{actor}-{encoding}-repeat-{repeat}"][1]
                      for encoding in design.ENCODINGS]
                known=all((row["result"] or {}).get("usable") and
                          (row["result"] or {}).get("valid_action") for row in pair)
                delta=(int(pair[1]["result"]["all_facts_correct"])-int(pair[0]["result"]["all_facts_correct"])) if known else None
                pairs.append(dict(profile_index=profile,actor=actor,repeat=repeat,both_scored=bool(known),
                                  id_map_minus_array=delta,statuses=[row["status"] for row in pair]))
    return dict(protocol=protocol,assignments=reports,calls=len(list((root/"calls").glob("*.json"))),
        by_encoding=summaries,paired_comparisons=pairs,both_presentations_passed=all(x["passed"] for x in summaries.values()),
        accounted_usd=str(cost),global_safety_stop=terminal["global_safety_stop"],
        caveat=specification()["limitations"]+" "+specification()["bounds"])


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
    content["README.md"]=("# Qwen mandate factual diagnostic\n\nAll56 factual assignments, failures, paired encodings and cost reservations retained. "
        "No old response is repaired/replaced; no institutional effect claimed. From a fresh extracted directory run:\n\n"
        "`python3 -I -S code/experiments/paper3_qwen_mandate_diagnostic.py . --replay --expected-protocol "+protocol+"`\n\n"
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
