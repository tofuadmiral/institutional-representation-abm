"""Eight-context/$0.25 JSON-object B instrument gate; no institutional outcome."""
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
from paper3 import hosted_b_calls as service
from paper3.pivot_b_budget import Ledger,atomic
from paper3.source_closure import closure

t=f.t;require=t.require;STAGE="pivot_b_json_mode_v1";CAP=Decimal("0.25");SEED=318000;WORKERS=4
BUDGET=f.BUDGET


def cases():
    contexts=deepcopy(f.contexts());random.Random(318999).shuffle(contexts);result=[]
    for context in contexts:
        index=int(context["id"].split("-")[-1]);context["seed"]=SEED+index
        request=f.request_for(context,"plain");request["response_format"]={"type":"json_object"}
        wire=t.canonical(request);bound=len(wire.encode())+1024
        require(bound<=65536,"input bound")
        reserve=(bound*t.PRICE_IN+t.OUTPUT_BOUND*t.PRICE_OUT)/Decimal(1000000)
        result.append(dict(id=context["id"],context=context,request=request,request_text=wire,
            request_sha256=t.sha(wire.encode()),input_token_bound=bound,reserved_usd=str(reserve)))
    require(sum(Decimal(c["reserved_usd"]) for c in result)<=CAP,"total reservation exceeds stage")
    return result


def seed_audit(root=ROOT):
    planned=set(range(SEED,SEED+8));observed=set();inventory=[]
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
    require(not planned&observed,"seed overlap")
    return dict(planned=sorted(planned),overlap=sorted(planned&observed),historical_files=len(inventory),inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()))


def specification():
    return dict(name=STAGE,cases=cases(),workers=4,max_calls=8,cap_usd=str(CAP),budget_cap_usd="10.00",
        inference_retries=0,receipt_offsets_seconds=[0,20,40,60],http_error_body_max_bytes=4096,
        failure_rule="Two transport/accounting failures or any identity/source/credential/budget/instrument breach stop admissions; invalid content alone does not. No restart, repair, retry or fallback; preserve all assignments/reservations.",
        gate="All eight complete, certified, native-reasoning, strict-action-valid; all four aligned/reversed dominant-project controls correct; no safety stop. Engineering feasibility only, not strategic/population evidence or replacement of previous failed calls.")


def prepare(root):
    root=Path(root);require(not root.exists(),"fresh directory required")
    seeds=seed_audit()
    with t.opener().open(t.METADATA_URL,timeout=20) as response:metadata=json.load(response)
    endpoint=t.check_metadata(metadata);require("response_format" in endpoint["supported_parameters"],"JSON format unsupported")
    paths=closure(ROOT,[Path(__file__),ROOT/"paper3/source_closure.py",ROOT/"analysis/paper3_contracts_archive.py",BUDGET/"authority.json",
                       ROOT/"tests/test_paper3_contracts_json_mode.py"])
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
    require(m["protocol"]["seed_audit"]["planned"]==list(range(SEED,SEED+8)) and not m["protocol"]["seed_audit"]["overlap"],"seed audit")
    require("response_format" in t.check_metadata(m["protocol"]["endpoint_metadata"])["supported_parameters"],"metadata format")
    return m,t.sha(t.canonical(m).encode())


def execute(root,ledger_root=BUDGET,secret=None,send=None,lookup=None,clock=time.time,sleep=time.sleep):
    root=Path(root);m,protocol=verify(root)
    require(0<=clock()-m["protocol"]["metadata_observed_unix"]<=3600,"stale metadata")
    with (root/"writer.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(not list((root/"sessions").iterdir()) and not list((root/"calls").iterdir()),"already started; no restart")
        ledger=Ledger(ledger_root);ledger.allocate(STAGE,CAP)
        atomic(root/"sessions/start.json",dict(protocol=protocol,pid=os.getpid(),started_unix=clock()))
        calls=service.Calls(root,ledger_root,STAGE,8,lambda:verify(root),f.score,secret,send,lookup,clock,sleep)
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:results=list(pool.map(calls.one,m["protocol"]["cases"]))
        terminal=dict(protocol=protocol,results=results,global_safety_stop=calls.stop.is_set(),transport_failures=calls.transport_failures,
                      budget=ledger.snapshot(),ended_unix=clock())
        atomic(root/"sessions/terminal.json",terminal);return terminal


def audit(root,ledger_root=BUDGET):
    root=Path(root);m,protocol=verify(root);terminal=t.load(root/"sessions/terminal.json")
    require(t.load(root/"sessions/start.json")["protocol"]==terminal["protocol"]==protocol,"terminal protocol")
    reports,cost=service.audit_records(root,ledger_root,STAGE,protocol,m["protocol"]["cases"],terminal,f.score)
    require(cost<=CAP,"stage cap exceeded")
    results=[r["result"] or {} for r in reports]
    valid=sum(bool(r.get("usable") and r.get("valid_action")) for r in results)
    correct=sum(r.get("dominant_projects_correct") is True for r in results)
    gate=valid==8 and correct==4 and not terminal["global_safety_stop"]
    return dict(protocol=protocol,assignments=reports,calls=len(list((root/"calls").glob("*.json"))),
        valid_actions=valid,controls_correct=correct,gate_passed=gate,accounted_usd=str(cost),
        global_safety_stop=terminal["global_safety_stop"],
        caveat="Eight selected diagnostic contexts. Control gaps are not wrong answers; passing does not demonstrate institutional effects or general reliability. Old failed outputs remain unchanged.")


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
    content["README.md"]=("# B JSON-object diagnostic\n\nEight selected engineering contexts; all failures, controls and cost reservations retained. "
        "No old response is repaired/replaced; no institutional effect claimed. From a fresh extracted directory run:\n\n"
        "`python3 -I -S code/experiments/paper3_contracts_json_mode.py . --replay --expected-protocol "+protocol+"`\n\n"
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
