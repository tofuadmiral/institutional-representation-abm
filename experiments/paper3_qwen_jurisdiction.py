"""Prospective 720-call structural-jurisdiction pilot; immutable prior evidence."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from fractions import Fraction
import argparse
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
from experiments import paper3_qwen_channel_gate as gate
from experiments import paper3_qwen_coalition_discovery as original
from experiments import paper3_qwen_mandate_diagnostic as factual
from paper3 import coalition_jurisdiction_design as design
from paper3 import coalition_contracts as game
from paper3 import hosted_reasoning_channel_calls as service
from paper3.pivot_b_budget import Ledger,atomic
from paper3.source_closure import closure

t=gate.t;require=t.require;sha=t.sha;load=t.load;canonical=t.canonical
STAGE="pivot_b_qwen_jurisdiction_v1";CAP=Decimal("1.00");WORKERS=4;MAX_CALLS=720
BUDGET=gate.BUDGET
GATE_ROOT=ROOT/"results/paper3/pivot_b_qwen_channel_gate_v1"
GATE_PROTOCOL="30585cdf44e1626620cab265d092432fe9aa585404e7f32376b13f5ac60f3388"
FACT_ROOT=ROOT/"results/paper3/pivot_b_qwen_mandate_v1"
FACT_PROTOCOL="caebf2b4040efdf82ef8a861f252903efa1621e6379982b2d53065624d953e80"
request_for=gate.request_for
score=gate.score


class StopEpisode(Exception):
    pass


def schedule():
    rows=design.schedule(tuple(350000+100*i for i in range(8)))
    random.Random(350999).shuffle(rows)
    return rows


def prerequisite():
    inherited=original.prerequisite()
    require(factual.verify(FACT_ROOT)[1]==FACT_PROTOCOL,"factual protocol changed")
    report=factual.audit(FACT_ROOT)
    require(report["calls"]==56 and report["by_encoding"]["principal_id_map"]["passed"],
            "explicit-ID factual prerequisite failed")
    require(factual.request_for([],0)==request_for([],0),"factual native configuration differs")
    return dict(channel=inherited,factual_protocol=FACT_PROTOCOL,factual_report=report,
                factual_report_sha256=sha(canonical(report).encode()),
                native_template=request_for([],0),
                limitation="Array gate failed; ID-map factual gate alone passed. No strategic/long-history competence claim.")


def prerequisite_paths():
    paths=original.prerequisite_paths()
    for root in (GATE_ROOT, FACT_ROOT):
        paths += [ROOT/rel for rel in load(root/"manifest.json")["sources"]]
    paths += [p for p in FACT_ROOT.rglob("*.json") if p.is_file()]
    paths += [p for p in (BUDGET/"entries").glob(factual.STAGE+"-*.json")]
    paths += [BUDGET/"stages"/(factual.STAGE+".json")]
    return paths


def make_case(assignment,actor,stage,messages,index):
    require(0<=index<30 and actor in game.ACTORS,"decision position")
    key=assignment["id"]+f"-{index:02d}"
    req=request_for(messages,assignment["seed_base"]+index);wire=canonical(req)
    bound=len(wire.encode())+1024
    require(bound+gate.CONFIG["output_bound"]<=gate.CONTEXT,"conservative context bound")
    reserve=(bound*gate.PRICE_IN+gate.CONFIG["output_bound"]*gate.PRICE_OUT)/Decimal(1000000)
    return dict(id=key,context=dict(kind="compound",stage=stage,actor=actor,index=index,
                    fixture_index=assignment["fixture_index"],form=assignment["form"],block=assignment["block"],arm=assignment["arm"],dominant_projects=None),
                request=req,request_text=wire,request_sha256=sha(wire.encode()),
                input_token_bound=bound,reserved_usd=str(reserve))


def specification():
    return dict(name=STAGE,max_calls=MAX_CALLS,new_gate_calls=0,workers=WORKERS,
        cap_usd=str(CAP),budget_cap_usd="10.00",assignments=schedule(),fixtures=design.fixtures(),
        displayed_fixtures=[[design.display_profile(p,f) for f in (0,1)] for p in design.fixtures()],
        role_maps=[list(x) for x in design.ROLE_MAPS],policy_maps=list(design.POLICY_MAPS),
        ex_ante_exposed=[list(x) for x in design.EX_ANTE_EXPOSED],
        fixture_inventories=[game.offer_inventory(p) for p in design.fixtures()],
        native_template=request_for([],0),prerequisite_protocol=GATE_PROTOCOL,
        factual_protocol=FACT_PROTOCOL,reasoning_evidence=gate.specification()["reasoning_evidence"],
        inference_retries=0,receipt_offsets_seconds=[0,20,40,60],
        failure_rule="Invalid content ends its episode; two transport/accounting failures or any source/identity/credential/budget/instrument breach stop admissions. Finish admitted calls; retain all24 assignments, failed prefixes and reservations. No restart/retry/repair/replacement/fallback.",
        feasibility_gate="All24 episodes and8 three-arm blocks complete; no global safety stop. Engineering success is not scientific success.",
        primary_screen="Universal-minus-member exposed-principal mean FINAL full-delivery utility strictly positive in BOTH four-signer blocks, and feasibility passes. Discovery only; nulls are retained. No substitute post-hoc success.",
        estimand="Paired selected-structure jurisdiction effects on draft/final terms and all7 realized outcomes. Explicit-ID display in all arms. Each role/label form has a different seed: those effects cannot be isolated. Four selected structures, two blocks each; not population evidence or confirmation. Membership is endogenous; scripted comparator is not equilibrium. Programmed enforcement alone is not a behavioral finding. Requested seeds do not ensure common random draws.")


def prepare(root):
    root=Path(root);require(not root.exists(),"fresh directory required")
    inherited=prerequisite();seeds=seed_audit()
    with t.opener().open(gate.METADATA_URL,timeout=20) as response:metadata=json.load(response)
    gate.check_metadata(metadata)
    paths=closure(ROOT,[Path(__file__),ROOT/"paper3/source_closure.py",
        ROOT/"analysis/paper3_contracts_archive.py",ROOT/"tests/test_paper3_qwen_jurisdiction.py",
        ROOT/"tests/test_paper3_coalition_contracts.py",ROOT/"tests/test_paper3_coalition_jurisdiction_design.py",ROOT/"tests/test_paper3_pivot_b_budget.py",
        BUDGET/"authority.json",*prerequisite_paths()])
    snapshot={str(p.relative_to(ROOT)):p.read_text() for p in paths}
    protocol=dict(**specification(),inherited_prerequisite=inherited,seed_audit=seeds,
                  endpoint_metadata=metadata,metadata_observed_unix=time.time())
    manifest=dict(protocol=protocol,sources={p:sha(v.encode()) for p,v in snapshot.items()})
    root.mkdir(parents=True,exist_ok=False)
    for sub in ("calls","decisions","episodes","sessions"):(root/sub).mkdir()
    atomic(root/"sources.json",snapshot);atomic(root/"manifest.json",manifest)
    return sha(canonical(manifest).encode())


def verify(root,code_root=ROOT):
    root=Path(root);m=load(root/"manifest.json");snap=load(root/"sources.json")
    require(set(snap)==set(m["sources"]),"source inventory")
    for rel,want in m["sources"].items():
        require(not Path(rel).is_absolute() and ".." not in Path(rel).parts,"unsafe source")
        require(sha((Path(code_root)/rel).read_bytes())==sha(snap[rel].encode())==want,"frozen source changed: "+rel)
    require(all(m["protocol"].get(k)==v for k,v in specification().items()),"specification changed")
    inherited=m["protocol"]["inherited_prerequisite"]
    require(inherited["channel"]["protocol"]==GATE_PROTOCOL and inherited["channel"]["report"]["gate_passed"],"channel prerequisite failed")
    require(inherited["channel"]["report_sha256"]==sha(canonical(inherited["channel"]["report"]).encode()),"channel prerequisite report")
    require(inherited["factual_protocol"]==FACT_PROTOCOL and inherited["factual_report"]["by_encoding"]["principal_id_map"]["passed"],"factual prerequisite failed")
    require(inherited["factual_report_sha256"]==sha(canonical(inherited["factual_report"]).encode()),"factual prerequisite report")
    require(inherited["native_template"]==request_for([],0),"prerequisite configuration")
    expected=sorted({s["seed_base"]+j for s in schedule() for j in range(30)})
    require(m["protocol"]["seed_audit"]["planned_unique"]==expected and not m["protocol"]["seed_audit"]["overlap"],"seed audit")
    gate.check_metadata(m["protocol"]["endpoint_metadata"])
    return m,sha(canonical(m).encode())


def execute(root,ledger_root=BUDGET,secret=None,send=None,lookup=None,clock=time.time,sleep=time.sleep):
    root=Path(root);m,protocol=verify(root)
    require(prerequisite()==m["protocol"]["inherited_prerequisite"],"prerequisite replay changed")
    require(0<=clock()-m["protocol"]["metadata_observed_unix"]<=3600,"stale metadata")
    with (root/"writer.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(all(not list((root/sub).iterdir()) for sub in ("calls","decisions","episodes","sessions")),"already started; no restart")
        ledger=Ledger(ledger_root);ledger.allocate(STAGE,CAP)
        atomic(root/"sessions/start.json",dict(protocol=protocol,pid=os.getpid(),started_unix=clock()))
        calls=service.Calls(root,ledger_root,STAGE,MAX_CALLS,lambda:verify(root),score,gate.CONFIG,
                            secret,send,lookup,clock,sleep)
        def one(assignment):
            if calls.stop.is_set():result=dict(id=assignment["id"],status="not_started")
            else:
                try:
                    def ask(actor,stage,messages,index):
                        case=make_case(assignment,actor,stage,messages,index)
                        path=root/"decisions"/(case["id"]+".json")
                        atomic(path,dict(case=case,result=dict(id=case["id"],status="prepared")))
                        status=calls.one(case);atomic(path,dict(case=case,result=status))
                        if status["status"]!="recorded":raise StopEpisode("request not recorded")
                        row=load(root/"calls"/(case["id"]+".json"))
                        if not (row["result"]["usable"] and row["result"]["valid_action"]):raise StopEpisode("unusable action")
                        return row["final_content"]
                    evidence=design.episode(m["protocol"]["displayed_fixtures"][assignment["fixture_index"]][assignment["form"]],assignment["arm"],ask)
                    result=dict(id=assignment["id"],status="complete",**evidence)
                except StopEpisode as exc:result=dict(id=assignment["id"],status="incomplete",error_type=type(exc).__name__)
                except Exception as exc:
                    calls.stop.set()
                    result=dict(id=assignment["id"],status="incomplete",error_type=type(exc).__name__)
            atomic(root/"episodes"/(assignment["id"]+".json"),result)
            print(json.dumps(dict(event="b_episode_terminal",id=assignment["id"],status=result["status"],budget=ledger.snapshot())),flush=True)
            return dict(id=assignment["id"],status=result["status"])
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:episodes=list(pool.map(one,schedule()))
        terminal=dict(protocol=protocol,episodes=episodes,
            results=[load(p)["result"] for p in sorted((root/"decisions").glob("*.json"))],
            global_safety_stop=calls.stop.is_set(),transport_failures=calls.transport_failures,
            budget=ledger.snapshot(),ended_unix=clock())
        atomic(root/"sessions/terminal.json",terminal);return terminal


def canonical_outcome(outcome,assignment):
    from copy import deepcopy
    out=deepcopy(outcome);form=assignment["form"]
    roles,policies=design.maps(form);inverse={v:k for k,v in policies.items()}
    for key in ("utility","regret","normalized_regret","best_outcome_utility","worst_outcome_utility",
                "final_full_delivery_utility","realized_minus_scripted_independent","consent"):
        out[key]=design.canonical_utilities(out[key],form)
    for key in ("draft_terms","final_terms"):
        out[key]=design.canonical_offer(out[key],form)
    out["final_offer"]=dict(out["final_terms"],message_display_text=outcome["final_offer"]["message"])
    out["passed"]=[inverse[p] for p in out["passed"]]
    out["invited_members"]=out["final_terms"]["coalition"]
    out["invited_member_utility"]=[out["utility"][i] for i in out["invited_members"]]
    out["nonmember_utility"]=[out["utility"][i] for i in game.ACTORS if i not in out["invited_members"]]
    out["status_quo_losers"]=[i for i,v in enumerate(out["utility"]) if v<0]
    out["scripted_independent"]["passed"]=[inverse[p] for p in out["scripted_independent"]["passed"]]
    out["scripted_independent"]["utility"]=design.canonical_utilities(out["scripted_independent"]["utility"],form)
    p=design.fixtures()[assignment["fixture_index"]]
    out["profile"]=p["id"]
    out["draft_full_delivery_utility"]=game.utility_vector(p,list(out["draft_terms"]["projects"].values()))
    return out


def contrasts(reports,fixtures):
    result=[]
    for block in range(8):
        selected=[r for r in reports if r["assignment"]["block"]==block]
        i=selected[0]["assignment"]["fixture_index"];p=fixtures[i]
        found={r["assignment"]["arm"]:r["outcome"] for r in selected}
        universe=[game.utility_vector(p,o) for o in game.all_outcomes()]
        full=[game.utility_vector(p,[a,b]) for a in game.PROJECTS["A"] for b in game.PROJECTS["B"]]
        feasible=lambda xs:[(min(v[j] for v in xs),max(v[j] for v in xs)) for j in game.ACTORS]
        for left_arm,right_arm in (("member_enforcement","universal_clearance"),
                                   ("public_promise","member_enforcement"),
                                   ("public_promise","universal_clearance")):
            left,right=found[left_arm],found[right_arm];paired=left is not None and right is not None
            def bounds(field,space):
                values=[[(v,v) for v in out[field]] if out else feasible(space) for out in (left,right)]
                return [[y[0]-x[1],y[1]-x[0]] for x,y in zip(*values)]
            utility_bounds=bounds("utility",universe)
            final_bounds=bounds("final_full_delivery_utility",full)
            exposed=design.EX_ANTE_EXPOSED[i]
            exposed_bounds=([str(sum(Fraction(final_bounds[j][k]) for j in exposed)/len(exposed))
                             for k in (0,1)] if exposed else None)
            regret=[(Fraction(out["mean_normalized_regret"]),)*2 if out else (Fraction(0),Fraction(1))
                    for out in (left,right)]
            behavior=None
            if paired:
                behavior=dict(final_projects_changed=left["final_terms"]["projects"]!=right["final_terms"]["projects"],
                    final_coalition_changed=left["final_terms"]["coalition"]!=right["final_terms"]["coalition"],
                    final_order_changed=left["final_terms"]["first"]!=right["final_terms"]["first"],
                    consent_changed=left["consent"]!=right["consent"],
                    all_principal_utility_difference=[y-x for x,y in zip(left["utility"],right["utility"])],
                    proposed_full_delivery_difference=[y-x for x,y in zip(left["final_full_delivery_utility"],right["final_full_delivery_utility"])])
            result.append(dict(block=block,fixture_index=i,fixture=p["id"],contrast=right_arm+" minus "+left_arm,
                paired_complete=paired,regret_difference_bounds=[str(regret[1][0]-regret[0][1]),str(regret[1][1]-regret[0][0])],
                all_principal_utility_difference_bounds=utility_bounds,
                final_proposed_utility_difference_bounds=final_bounds,
                draft_proposed_utility_difference_bounds=bounds("draft_full_delivery_utility",full),
                exposed_final_mean_difference_bounds=exposed_bounds,
                behavioral_and_distributional=behavior))
    return result


def audit(root,ledger_root=BUDGET):
    root=Path(root);m,protocol=verify(root);terminal=load(root/"sessions/terminal.json")
    require(terminal["protocol"]==load(root/"sessions/start.json")["protocol"]==protocol,"terminal protocol")
    require(prerequisite()==m["protocol"]["inherited_prerequisite"],"prerequisite replay changed")
    rows={p.stem:load(p) for p in (root/"calls").glob("*.json")}
    decisions={p.stem:load(p) for p in (root/"decisions").glob("*.json")}
    used=set();reports=[]
    require(len(rows)<=MAX_CALLS,"attempt limit")
    for assignment in schedule():
        saved=load(root/"episodes"/(assignment["id"]+".json"));count=0
        def ask(actor,stage,messages,index):
            nonlocal count
            case=make_case(assignment,actor,stage,messages,index);key=case["id"]
            if key not in decisions:raise StopEpisode("missing decision")
            used.add(key)
            if decisions[key]["case"]!=case:raise RuntimeError("episode request or role changed")
            if key not in rows:raise StopEpisode("request not admitted")
            count+=1;result=score(rows[key],case)
            if not (result["usable"] and result["valid_action"]):raise StopEpisode("unusable action")
            return service.final_content(rows[key]["stream"])
        replay=None
        try:replay=design.episode(m["protocol"]["displayed_fixtures"][assignment["fixture_index"]][assignment["form"]],assignment["arm"],ask)
        except StopEpisode:pass
        if replay is not None:require(saved==dict(id=assignment["id"],status="complete",**replay),"episode replay differs")
        else:
            require(saved["status"] in ("incomplete","not_started"),"incomplete episode marked complete")
            require(not count or saved["status"]=="incomplete","admitted episode marked unstarted")
        reports.append(dict(assignment=assignment,status=saved["status"],observed_calls=count,
                            display_outcome=replay["outcome"] if replay else None,
                            outcome=canonical_outcome(replay["outcome"],assignment) if replay else None))
    require(used==set(decisions) and set(rows)<=used,"unexpected or post-failure decisions")
    require({p.stem for p in (root/"episodes").glob("*.json")}=={s["id"] for s in schedule()},"episode inventory")
    require(terminal["episodes"]==[dict(id=r["assignment"]["id"],status=r["status"]) for r in reports],"terminal episode inventory")
    cases=[decisions[key]["case"] for key in sorted(used)]
    require(terminal["results"]==[decisions[key]["result"] for key in sorted(used)],"decision status inventory")
    call_reports,cost=service.audit_records(root,ledger_root,STAGE,protocol,cases,terminal,score,gate.CONFIG)
    require(cost<=CAP,"stage cap exceeded")
    complete=sum(r["status"]=="complete" for r in reports)
    comparisons=contrasts(reports,m["protocol"]["fixtures"])
    primary=[c for c in comparisons if c["fixture_index"]==0 and c["contrast"]=="universal_clearance minus member_enforcement"]
    feasible=complete==24 and not terminal["global_safety_stop"]
    primary_passed=feasible and len(primary)==2 and all(c["paired_complete"] and
        Fraction(c["exposed_final_mean_difference_bounds"][0])>0 for c in primary)
    return dict(protocol=protocol,inherited_prerequisite_protocol=GATE_PROTOCOL,new_gate_calls=0,
        assignments=reports,call_reports=call_reports,calls=len(rows),complete_episodes=complete,
        contrasts=comparisons,primary_discovery_screen_passed=primary_passed,accounted_usd=str(cost),
        global_safety_stop=terminal["global_safety_stop"],
        feasibility_passed=feasible,
        caveat=specification()["estimand"]+" Missingness bounds are finite-outcome bounds, not confidence intervals.")


def seed_audit(root=ROOT):
    planned = {s["seed_base"]+j for s in schedule() for j in range(30)}
    observed, inventory = set(), []
    def walk(value, key=""):
        if isinstance(value, dict):
            for k,v in value.items(): walk(v,k)
        elif isinstance(value, list):
            for item in value: walk(item,key)
        elif type(value) is int and ("seed" in key.lower() or key in ("planned","planned_unique")):
            observed.add(value)
    for base, dirs, files in os.walk(Path(root)/"results/paper3"):
        dirs[:] = [d for d in dirs if not any(x in d for x in ("portable", "bundle", "export", "__pycache__", "code"))]
        for name in files:
            p = Path(base)/name
            if name == "manifest.json" or (p.parent.name == "calls" and name.endswith(".json")):
                row = load(p)
                walk(row.get("request", row) if p.parent.name == "calls" else row)
                inventory.append((str(p.relative_to(root)), sha(p.read_bytes())))
    # Also preserve old unexecuted recent institutional schedules. Their reserved
    # positions cannot be reused merely because calls were never admitted.
    expanded = {281000+1000*i+j for i in range(12) for j in range(25)}
    expanded |= {301000+1000*i+100*r+j for i in range(2) for r in range(2) for j in range(25)}
    expanded |= {311000+1000*i+j for i in range(4) for j in range(25)}
    expanded |= set(range(310000,310008)) | set(range(315000,315004))
    overlap = planned & (observed | expanded)
    require(not overlap, "old seed overlap; do not silently replace seeds")
    return dict(planned_unique=sorted(planned), overlap=sorted(overlap),
                matched_reuse="Same requested stage seeds across three arms within each fixture; not guaranteed determinism.",
                historical_files=len(inventory), inventory_sha256=sha(canonical(sorted(inventory)).encode()),
                expanded_previous_schedules=sorted(expanded))



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
    content["README.md"]=("# Qwen structural-jurisdiction pilot\n\nAll24 institutional assignments with an exactly inherited prerequisite; all failures, controls and cost reservations retained. "
        "No old response is repaired/replaced; no institutional effect claimed. From a fresh extracted directory run:\n\n"
        "`python3 -I -S code/experiments/paper3_qwen_jurisdiction.py . --replay --expected-protocol "+protocol+"`\n\n"
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
