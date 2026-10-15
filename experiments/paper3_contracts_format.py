"""Prospective B instrument diagnostic, not replacement institutional outcomes.

Eight fixed compound-action contexts crossed with plain/native JSON Schema.
Sixteen attempts, four workers, $0.50 within the SAME fresh B $10 ledger.
Imports predecessor transport/rules read-only. No repairs, retries or fallback.
"""
from __future__ import annotations

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
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import paper3_coalition_contracts as predecessor
from paper3 import coalition_contracts as game
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure

t = predecessor.transport
require, load, sha, canonical = game.require, t.load, t.sha, t.canonical
BUDGET = predecessor.BUDGET
STAGE = "pivot_b_format_v1"
CAP = Decimal("0.50")
WORKERS = 4
MODES = ("plain", "json_schema")
SEED = 317000


def action_schema(stage):
    require(stage in ("draft", "response", "final"), "compound stage required")
    props = dict(
        projects=dict(type="object", properties={k:dict(type="string", enum=list(v))
                      for k,v in game.PROJECTS.items()}, required=["A", "B"], additionalProperties=False),
        first=dict(type="string", enum=["A", "B"]),
        coalition=dict(type="array", items=dict(type="integer", enum=list(game.ACTORS)),
                       uniqueItems=True, anyOf=[dict(maxItems=0),dict(minItems=4,maxItems=4)]),
        message=dict(type="string", maxLength=600))
    if stage == "response": props["support"] = dict(type="boolean")
    # No utility optimum/expected answer is encoded. Both orders, every ordered
    # legal coalition (and no contract), every project and both support values.
    return dict(type="object", properties=props, required=list(props), additionalProperties=False)


def contexts():
    profiles = game.fixtures()
    reverse = deepcopy(profiles[2]); reverse["id"] = "reversed_aligned_control"
    reverse["utilities"] = [dict(A0=1,A1=5,B0=2,B1=4) for _ in game.ACTORS]
    profiles.append(reverse)
    result=[]
    draft_arms=("member_enforcement","universal_clearance","public_promise","member_enforcement")
    response_arms=("public_promise","member_enforcement","universal_clearance","public_promise")
    for stage,arms in (("draft",draft_arms),("response",response_arms)):
        for i,p in enumerate(profiles):
            events=[]
            if stage == "response":
                # Fixed synthetic history, not a convenient saved bad response.
                action=dict(projects=dict(A="A0",B="B0"),first="A",coalition=[0,1,3,4],message="Proposed terms.")
                game.parse_action(json.dumps(action),"draft")
                events=[dict(type="draft",actor=0,action=action)]
            actor=0 if stage == "draft" else (3,6,4,2)[i]
            expected=None if i<2 else dict(A="A0" if i==2 else "A1",B="B0" if i==2 else "B1")
            index=len(result)
            result.append(dict(id=f"context-{index}",profile=p,arm=arms[i],actor=actor,
                stage=stage,events=events,seed=SEED+index,
                dominant_projects=expected,messages=game.messages(p,arms[i],actor,stage,events)))
    return result


def request_for(context,mode):
    require(mode in MODES,"unknown format")
    request=predecessor.request_for(context["messages"],context["seed"])
    if mode == "json_schema":
        request["response_format"]=dict(type="json_schema",json_schema=dict(
            name="coalition_"+context["stage"],strict=True,schema=action_schema(context["stage"])))
    return request


def cases():
    order=list(range(8));random.Random(317999).shuffle(order)
    result=[]
    for wave in range(2):
        for pos,i in enumerate(order):
            c=contexts()[i];mode=MODES[(pos%2+wave)%2]
            request=request_for(c,mode);wire=canonical(request);bound=len(wire.encode())+1024
            require(bound<=65536,"input bound")
            reserve=(bound*t.PRICE_IN+t.OUTPUT_BOUND*t.PRICE_OUT)/Decimal(1000000)
            result.append(dict(id=c["id"]+"-"+mode,context=c,mode=mode,wave=wave,
                request=request,request_text=wire,request_sha256=sha(wire.encode()),
                input_token_bound=bound,reserved_usd=str(reserve)))
    require(len(result)==16 and sum(Decimal(c["reserved_usd"]) for c in result)<=CAP,"allocation bound")
    return result


def seed_audit(root=ROOT):
    planned=set(range(SEED,SEED+8));observed=set();inventory=[]
    def walk(v,k=""):
        if isinstance(v,dict):
            for key,x in v.items():walk(x,key)
        elif isinstance(v,list):
            for x in v:walk(x,k)
        elif type(v) is int and ("seed" in k.lower() or k in ("planned_unique","planned")):
            observed.add(v)
    for base,dirs,files in os.walk(Path(root)/"results/paper3"):
        dirs[:]=[d for d in dirs if not any(x in d for x in ("portable","bundle","export","__pycache__","code"))]
        for name in files:
            path=Path(base)/name
            if name=="manifest.json" or (path.parent.name=="calls" and name.endswith(".json")):
                row=load(path);walk(row.get("request",row))
                inventory.append((str(path.relative_to(root)),sha(path.read_bytes())))
    # Include the previous B allocation's unexecuted decisions, not only calls.
    observed |= {a["seed_base"]+j for a in predecessor.schedule() for j in range(30)}
    require(not planned&observed,"historical seed overlap")
    return dict(planned=sorted(planned),overlap=sorted(planned&observed),historical_files=len(inventory),
                inventory_sha256=sha(canonical(sorted(inventory)).encode()),
                pairing="Same requested seed within context, not guaranteed matched random draws.")


def check_metadata(metadata):
    t.check_metadata(metadata)
    endpoint=next(e for e in metadata["data"]["endpoints"] if e["tag"]=="atlas-cloud/fp8")
    require({"response_format","structured_outputs"}<=set(endpoint["supported_parameters"]),
            "native structured output not advertised; do not substitute endpoint")


def specification():
    return dict(name=STAGE,cases=cases(),workers=WORKERS,max_calls=16,stage_cap_usd=str(CAP),
        budget_cap_usd="10.00",inference_retries=0,receipt_offsets_seconds=[0,20,40,60],
        stop_receipt_reads_after_first_certified_match=True,transport_failure_global_threshold=2,
        global_failure_rule="Identity/source/budget/credential/instrument failure or two transport failures stops admissions. Invalid content alone is retained and does not stop other fixed contexts. No repair, fallback, restart or case replacement.",
        gate="Each format passes only if all eight contexts have complete certified native-reasoning valid actions and all four aligned/reversed controls select dominant projects. This is selected instrument feasibility, not strategic competence, causal institutional evidence or long-run reliability.",
        selection_rule="If both pass, retain plain to minimize interface change; otherwise use the sole passing format. If neither passes, no full B successor on this configuration.")


def prepare(root):
    root=Path(root);require(not root.exists(),"fresh directory required")
    seedcheck=seed_audit()
    with t.opener().open(t.METADATA_URL,timeout=20) as response:metadata=json.load(response)
    check_metadata(metadata)
    paths=closure(ROOT,[Path(__file__),ROOT/"paper3/source_closure.py",BUDGET/"authority.json",
                       ROOT/"tests/test_paper3_contracts_format.py"])
    snapshot={str(p.relative_to(ROOT)):p.read_text() for p in paths}
    protocol=dict(**specification(),endpoint_metadata=metadata,metadata_observed_unix=time.time(),seed_audit=seedcheck)
    manifest=dict(protocol=protocol,sources={p:sha(v.encode()) for p,v in snapshot.items()})
    root.mkdir(parents=True,exist_ok=False)
    for sub in ("calls","sessions"):(root/sub).mkdir()
    atomic(root/"sources.json",snapshot);atomic(root/"manifest.json",manifest)
    return sha(canonical(manifest).encode())


def verify(root,code_root=ROOT):
    root=Path(root);m=load(root/"manifest.json");snap=load(root/"sources.json")
    require(set(m["sources"])==set(snap),"source inventory")
    for rel,want in m["sources"].items():
        require(not Path(rel).is_absolute() and ".." not in Path(rel).parts,"unsafe source path")
        require(sha((Path(code_root)/rel).read_bytes())==sha(snap[rel].encode())==want,"frozen source changed: "+rel)
    require(all(m["protocol"].get(k)==v for k,v in specification().items()),"specification changed")
    require(m["protocol"]["seed_audit"]["planned"]==list(range(SEED,SEED+8)) and not m["protocol"]["seed_audit"]["overlap"],"seed audit")
    check_metadata(m["protocol"]["endpoint_metadata"])
    return m,sha(canonical(m).encode())


def score(row,case):
    if row.get("instrument_error") or "assessment" not in row:
        return dict(usable=False,valid_action=False,dominant_projects_correct=None,action=None,failure="instrument_or_unfinished")
    assessment=t.assess(row);stream=assessment["stream"]
    usage=stream.get("usage") or {};n=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    native=type(n) is int and 0<n<=usage.get("completion_tokens",0)
    usable=assessment["passed"] and stream["finish_reasons"]==["stop"] and native
    result=dict(usable=usable,valid_action=False,dominant_projects_correct=None,action=None,
                failure=None if usable else "transport_reasoning_or_completion")
    if not usable:return result
    try:
        action=game.parse_action(predecessor.final_content(row["stream"]),case["context"]["stage"])
        result.update(valid_action=True,action=action)
        expected=case["context"]["dominant_projects"]
        if expected is not None:result["dominant_projects_correct"]=action["projects"]==expected
    except (ValueError,TypeError,KeyError) as exc:result["failure"]=type(exc).__name__
    return result


class Runner:
    def __init__(self,root,ledger_root=BUDGET,secret=None,transmit=None,lookup=None,clock=time.time,sleep=time.sleep):
        self.root=Path(root);self.manifest,self.protocol=verify(root)
        self.ledger=Ledger(ledger_root);self.secret=secret
        self.transmit=transmit or t.transmit;self.lookup=lookup or t.receipt_lookup
        self.clock,self.sleep=clock,sleep;self.guard=threading.Lock();self.stop=threading.Event()
        self.transport_failures=0

    def one(self,case):
        key=case["id"];path=self.root/"calls"/(key+".json");reserve=Decimal(case["reserved_usd"])
        with self.guard:
            if self.stop.is_set():return dict(id=key,status="not_started")
            try:
                verify(self.root)
                require(len(list((self.root/"calls").glob("*.json")))<16,"call limit")
                self.ledger.reserve(STAGE,STAGE+"-"+key,reserve,case["request_sha256"])
                row=dict(**case,protocol=self.protocol,status="admitted",attempt=1,admitted_unix=self.clock())
                atomic(path,row)
            except Exception as exc:
                self.stop.set()
                return dict(id=key,status="admission_failed",error_type=type(exc).__name__)
        try:
            row["stream"]=self.transmit(case["request_text"],self.secret)
            row["stream"],hit=t.redact(row["stream"],self.secret)
            row["stream"]["secret_redacted"]=hit or row["stream"].get("secret_redacted",False)
            row.update(status="stream_ended",receipts=[]);atomic(path,row)
            s=t.stream_summary(row["stream"])
            if ((s["models"] and not set(s["models"])<=set(t.MODELS)) or
                (s["providers"] and s["providers"]!=[t.PROVIDER]) or len(s["models"])>1 or
                len(s["ids"])>1 or row["stream"]["secret_redacted"]):self.stop.set()
            if s["generation_id"]:
                for offset in (0,20,40,60):
                    self.sleep(max(0,row["stream"]["ended_unix"]+offset-self.clock()))
                    observation=self.lookup(s["generation_id"],self.secret)
                    observation,hit=t.redact(observation,self.secret)
                    observation["secret_redacted"]=hit or observation.get("secret_redacted",False)
                    observation["scheduled_offset_seconds"]=offset
                    row["receipts"].append(observation);atomic(path,row)
                    current=t.assess(row)
                    if current["receipt_certified"]:break
                    if observation.get("http_status")==200:self.stop.set();break
            row["assessment"]=t.assess(row)
            row.update(status="recorded",ended_unix=self.clock())
            row["result"]=score(row,case)
            row["final_content"]=predecessor.final_content(row["stream"]) if row["assessment"]["stream"]["complete"] else None
            atomic(path,row)
            a=row["assessment"]
            self.ledger.settle(STAGE+"-"+key,a["accounted_usd"],a["receipt_certified"],sha(path.read_bytes()))
            if Decimal(a["accounted_usd"])>reserve:self.stop.set()
            if a["passed"] and not row["result"]["usable"]:self.stop.set()
            if not a["passed"]:
                with self.guard:
                    self.transport_failures+=1
                    if self.transport_failures>=2:self.stop.set()
            print(json.dumps(dict(event="format_case_terminal",id=key,result=row["result"],budget=self.ledger.snapshot())),flush=True)
            return dict(id=key,status="recorded")
        except Exception as exc:
            self.stop.set();row.update(status="instrument_error",instrument_error=type(exc).__name__)
            atomic(path,row)
            return dict(id=key,status="instrument_error")

    def run(self):
        require(0<=self.clock()-self.manifest["protocol"]["metadata_observed_unix"]<=3600,"stale metadata")
        with (self.root/"writer.lock").open("a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            require(not list((self.root/"sessions").iterdir()) and not list((self.root/"calls").iterdir()),"already started; no restart")
            self.ledger.allocate(STAGE,CAP)
            atomic(self.root/"sessions/start.json",dict(protocol=self.protocol,pid=os.getpid(),started_unix=self.clock()))
            results=[]
            # Balance which format comes first; barrier keeps both modes in
            # each wave. This does not isolate a randomized population effect.
            for wave in range(2):
                selected=[c for c in self.manifest["protocol"]["cases"] if c["wave"]==wave]
                with ThreadPoolExecutor(max_workers=WORKERS) as pool:results.extend(pool.map(self.one,selected))
            terminal=dict(protocol=self.protocol,results=results,global_safety_stop=self.stop.is_set(),
                          transport_failures=self.transport_failures,budget=self.ledger.snapshot(),ended_unix=self.clock())
            atomic(self.root/"sessions/terminal.json",terminal)
            return terminal


def audit(root,ledger_root=BUDGET):
    root=Path(root);m,protocol=verify(root);terminal=load(root/"sessions/terminal.json")
    require(terminal["protocol"]==load(root/"sessions/start.json")["protocol"]==protocol,"terminal protocol")
    require(not list(root.rglob("*.partial")),"partial write")
    assigned=m["protocol"]["cases"];reports=[];cost=Decimal(0);matched=set()
    require([r["id"] for r in terminal["results"]]==[c["id"] for c in assigned],"terminal inventory")
    for c,saved in zip(assigned,terminal["results"]):
        path=root/"calls"/(c["id"]+".json");entry_path=Path(ledger_root)/"entries"/(STAGE+"-"+c["id"]+".json")
        if not path.exists():
            require(saved["status"] in ("not_started","admission_failed"),"missing admitted record")
            if entry_path.exists():
                e=load(entry_path);require(e["status"]=="reserved" and e["request_sha256"]==c["request_sha256"],"orphan reservation")
                cost+=Decimal(e["reserved_usd"]);matched.add(e["request_id"])
            reports.append(dict(id=c["id"],mode=c["mode"],status=saved["status"],result=None));continue
        row=load(path);e=load(entry_path);matched.add(e["request_id"])
        require(all(row.get(k)==v for k,v in c.items()) and row["protocol"]==protocol and row["attempt"]==1,"call provenance")
        require(row["status"]==saved["status"],"terminal status")
        require(e["request_sha256"]==c["request_sha256"] and e["reserved_usd"]==c["reserved_usd"],"ledger provenance")
        result=score(row,c)
        if not row.get("instrument_error"):
            require(row["assessment"]==t.assess(row) and row["result"]==result,"assessment changed")
            a=row["assessment"]
            require(row["final_content"]==(predecessor.final_content(row["stream"]) if a["stream"]["complete"] else None),"final content changed")
            require(e["status"]=="settled" and e["evidence_sha256"]==sha(path.read_bytes()),"settlement evidence")
            require(e["accounted_usd"]==a["accounted_usd"] and e["certified"]==a["receipt_certified"],"settlement changed")
        cost+=Decimal(e.get("accounted_usd",e["reserved_usd"]))
        reports.append(dict(id=c["id"],mode=c["mode"],status=row["status"],result=result))
    require({f.stem for f in (root/"calls").glob("*.json")}<={c["id"] for c in assigned},"unexpected call")
    entries=[load(p) for p in (Path(ledger_root)/"entries").glob("*.json")]
    require({e["request_id"] for e in entries if e["stage"]==STAGE}==matched,"unmatched stage spending")
    require(cost<=CAP,"stage over cap")
    modes={}
    for mode in MODES:
        rows=[r for r in reports if r["mode"]==mode];results=[r["result"] or {} for r in rows]
        valid=sum(bool(r.get("usable") and r.get("valid_action")) for r in results)
        correct=sum(r.get("dominant_projects_correct") is True for r in results)
        modes[mode]=dict(assigned=8,valid=valid,controls_correct=correct,
                         passed=valid==8 and correct==4 and not terminal["global_safety_stop"])
    selected=next((mode for mode in MODES if modes[mode]["passed"]),None)
    return dict(protocol=protocol,assignments=reports,format_gate=modes,selected_format=selected,
                calls=len(list((root/"calls").glob("*.json"))),accounted_usd=str(cost),
                global_safety_stop=terminal["global_safety_stop"],
                caveat="Selected engineering contexts, not full institutions, independent population samples or a causal institutional comparison. Invalid actions and controls remain; no old output is replaced.")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path)
    modes=parser.add_mutually_exclusive_group(required=True)
    for name in ("prepare","run","audit"):modes.add_argument("--"+name,action="store_true")
    parser.add_argument("--expected-protocol");args=parser.parse_args()
    if args.prepare:print(prepare(args.root));return
    require(verify(args.root)[1]==args.expected_protocol,"expected protocol required")
    print(json.dumps(audit(args.root) if args.audit else Runner(args.root,secret=t.read_key()).run(),indent=2))


if __name__=="__main__":main()
