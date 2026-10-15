"""Prospective Pivot B discovery: 8 gate calls, nine 30-call episodes, $1.50.

Uses the completed transport diagnostic's low-level instrument read-only, but
NONE of its historical cases, budgets, launch logic, retries, or gate decisions.
All B spending shares the new $10 ledger. No process restart is supported.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
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
from experiments import paper3_transport_diagnostic as transport
from paper3 import coalition_contracts as game
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure

STAGE = "pivot_b_discovery_v1"
STAGE_CAP = Decimal("1.50")
BUDGET = ROOT/"results/paper3/pivot_b_budget"
GATE_SEED = 316000
EPISODE_SEED = 316100
WORKERS = 4
require = game.require
sha = transport.sha
canonical = transport.canonical
load = transport.load


def request_for(messages, seed):
    return dict(model=transport.MODEL, messages=messages, seed=seed,
        max_tokens=65536, temperature=1, top_p=.95, top_k=20, min_p=0,
        presence_penalty=0, repetition_penalty=1,
        reasoning=dict(enabled=True, exclude=False), stream=True, plugins=[],
        usage=dict(include=True),
        provider=dict(only=["atlas-cloud/fp8"], order=["atlas-cloud/fp8"],
                      allow_fallbacks=False, require_parameters=True, quantizations=["fp8"],
                      max_price=dict(prompt=.269, completion=.4, request=0)))


def gate_cases():
    """Numerical/explicit-rule checks, not a strategic rationality gate."""
    prompts = [
        ("public_promise", "Your principal receives +9 if A0 passes and -3 if B0 passes. Both pass. What is its total utility? Return {\"answer\":integer}.", 6),
        ("member_enforcement", "Is a guaranteed total of 6 strictly better for your principal than a guaranteed alternative total of 4? Return {\"answer\":boolean}.", True),
        ("member_enforcement", "Is a guaranteed total of 3 strictly better for your principal than a guaranteed alternative total of 5? Return {\"answer\":boolean}.", False),
        ("member_enforcement", "Final coalition [0,1,3,4]; all four consented. Actor0 requests no on the FIRST project. Is actor0's EXECUTED vote yes? Return {\"answer\":boolean}.", True),
        ("public_promise", "Final coalition [0,1,3,4]; all four consented. Actor0 requests no on the FIRST project. Is actor0's EXECUTED vote yes? Return {\"answer\":boolean}.", False),
        ("universal_clearance", "Final coalition [0,1,3,4]; actors0 through5 consent, actor6 refuses. Does the agreement activate? Return {\"answer\":boolean}.", False),
        ("universal_clearance", "Final coalition [0,1,3,4]; all SEVEN consent. Nonmember2 requests no on the FIRST project. Is actor2's EXECUTED vote yes? Return {\"answer\":boolean}.", False),
        ("public_promise", "Final coalition [0,1,3,4]; all four consented. FIRST project passed and all four members' executed first votes were yes. Is member0's promised SECOND yes now due (even though unenforced)? Return {\"answer\":boolean}.", True),
    ]
    return [dict(id=f"gate-{i}", seed=GATE_SEED+i, expected=answer,
                 messages=[dict(role="system",content=game.COMMON_RULES+"\n"+game.ARM_RULES[arm]),
                           dict(role="user",content=prompt)])
            for i,(arm,prompt,answer) in enumerate(prompts)]


def schedule():
    result = [dict(id=f"fixture-{i}-{arm}", fixture_index=i, arm=arm,
                   seed_base=EPISODE_SEED+100*i)
              for i in range(3) for arm in game.ARMS]
    random.Random(316999).shuffle(result)
    return result


def seed_audit(root=ROOT):
    planned = {GATE_SEED+i for i in range(8)}
    planned |= {s["seed_base"]+j for s in schedule() for j in range(30)}
    observed, inventory = set(), []
    def walk(value, key=""):
        if isinstance(value, dict):
            for k,v in value.items(): walk(v,k)
        elif isinstance(value, list):
            for item in value: walk(item,key)
        elif type(value) is int and "seed" in key.lower():
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


def sources():
    entries = [Path(__file__).resolve(), ROOT/"paper3/source_closure.py",
               ROOT/"tests/test_paper3_coalition_contracts.py",
               ROOT/"tests/test_paper3_pivot_b_budget.py",
               ROOT/"tests/test_paper3_coalition_contracts_runner.py",
               BUDGET/"authority.json"]
    return closure(ROOT, entries)


def prepare(root):
    root = Path(root)
    require(not root.exists(), "fresh directory required")
    check = seed_audit()
    with transport.opener().open(transport.METADATA_URL, timeout=20) as response:
        metadata = json.load(response)
    transport.check_metadata(metadata)
    snapshots = {str(p.relative_to(ROOT)):p.read_text() for p in sources()}
    protocol = dict(name=STAGE, max_calls=278, gate=gate_cases(), assignments=schedule(),
        fixtures=game.fixtures(), fixture_inventories=[game.offer_inventory(p) for p in game.fixtures()],
        stage_cap_usd=str(STAGE_CAP), fresh_budget_cap_usd="10.00", workers=WORKERS,
        request_template=request_for([],0), gate_all_correct_required=True,
        seed_audit=check, endpoint_metadata=metadata, metadata_observed_unix=time.time(),
        receipt_offsets_seconds=[0,20,40,60], stop_receipt_reads_after_first_certified_match=True,
        transport_failure_global_threshold=2, inference_retries=0,
        failure_rule="Invalid content or one transport failure ends its episode. Two transport failures or any source/identity/credential/budget/instrument failure stop new admissions. Retain every assigned case and reservation.",
        estimand="Discovery: ex-ante rule effects on endogenous offers, consent and all-seven-principal outcomes. Nine selected-fixture episodes, no population claim; controller compliance is mechanical.")
    manifest = dict(protocol=protocol, sources={p:sha(v.encode()) for p,v in snapshots.items()})
    root.mkdir(parents=True, exist_ok=False)
    for sub in ("calls","episodes","sessions"): (root/sub).mkdir()
    atomic(root/"sources.json",snapshots); atomic(root/"manifest.json",manifest)
    return sha(canonical(manifest).encode())


def verify(root, code_root=ROOT):
    root = Path(root); manifest = load(root/"manifest.json"); snapshots = load(root/"sources.json")
    require(set(manifest["sources"]) == set(snapshots), "source inventory")
    for rel, expected in manifest["sources"].items():
        require(not Path(rel).is_absolute() and ".." not in Path(rel).parts, "unsafe source path")
        require(sha((Path(code_root)/rel).read_bytes()) == sha(snapshots[rel].encode()) == expected,
                "frozen source changed: "+rel)
    p = manifest["protocol"]
    require(p["name"] == STAGE and p["gate"] == gate_cases() and p["assignments"] == schedule(), "schedule changed")
    require(p["fixtures"] == game.fixtures() and p["request_template"] == request_for([],0), "task or model changed")
    require(p["stage_cap_usd"] == str(STAGE_CAP) and p["fresh_budget_cap_usd"] == "10.00", "budget changed")
    require(p["max_calls"] == 278 and p["workers"] == WORKERS and p["inference_retries"] == 0, "allocation changed")
    require(p["receipt_offsets_seconds"] == [0,20,40,60] and p["stop_receipt_reads_after_first_certified_match"] is True, "receipt policy")
    require(p["transport_failure_global_threshold"] == 2 and p["gate_all_correct_required"] is True, "failure policy")
    require(p["fixture_inventories"] == [game.offer_inventory(f) for f in game.fixtures()], "benchmark changed")
    require(not p["seed_audit"]["overlap"], "seed audit failed")
    transport.check_metadata(p["endpoint_metadata"])
    return manifest, sha(canonical(manifest).encode())


def final_content(stream):
    pending, pieces = [], []
    for line in [*stream["lines"], ""]:
        if line.startswith("data:"):
            pending.append(line[5:].lstrip(" "))
        elif not line and pending:
            raw = "\n".join(pending); pending = []
            if raw == "[DONE]": continue
            value = json.loads(raw)
            for choice in value.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("content") is not None:
                    require(type(delta["content"]) is str, "nontext final content")
                    pieces.append(delta["content"])
    return "".join(pieces)


def gate_correct(raw, expected):
    def unique(pairs):
        d = {}
        for k,v in pairs:
            require(k not in d,"duplicate gate key"); d[k] = v
        return d
    try:
        value = json.loads(raw, object_pairs_hook=unique)
        return (type(value) is dict and set(value) == {"answer"}
                and type(value["answer"]) is type(expected) and value["answer"] == expected)
    except (ValueError, TypeError):
        return False


class StopEpisode(Exception):
    pass


class Runner:
    def __init__(self, root, ledger_root=BUDGET, secret=None, transmit=None,
                 lookup=None, clock=time.time, sleep=time.sleep):
        self.root = Path(root)
        self.manifest, self.protocol = verify(root)
        self.ledger = Ledger(ledger_root)
        self.secret = secret
        self.transmit = transmit or transport.transmit
        self.lookup = lookup or transport.receipt_lookup
        self.clock, self.sleep = clock, sleep
        self.guard = threading.Lock()
        self.stop = threading.Event()
        self.transport_failures = 0

    def call(self, request_id, messages, seed):
        request = request_for(messages,seed)
        wire = canonical(request)
        bound = len(wire.encode())+1024
        require(bound <= 65536,"input bound exceeded")
        reserve = (bound*transport.PRICE_IN+transport.OUTPUT_BOUND*transport.PRICE_OUT)/Decimal(1000000)
        path = self.root/"calls"/(request_id+".json")
        with self.guard:
            if self.stop.is_set(): raise StopEpisode("global safety stop")
            try:
                verify(self.root)
                require(len(list((self.root/"calls").glob("*.json"))) < 278,"call ceiling")
                self.ledger.reserve(STAGE,STAGE+"-"+request_id,reserve,sha(wire.encode()))
                row = dict(id=request_id, protocol=self.protocol, status="admitted", attempt=1,
                           request=request, request_text=wire, request_sha256=sha(wire.encode()),
                           input_token_bound=bound,reserved_usd=str(reserve),admitted_unix=self.clock())
                atomic(path,row)
            except Exception:
                self.stop.set()
                raise
        try:
            row["stream"] = self.transmit(wire,self.secret)
            row["stream"],hit = transport.redact(row["stream"],self.secret)
            row["stream"]["secret_redacted"] = hit or row["stream"].get("secret_redacted",False)
            row.update(status="stream_ended",receipts=[])
            atomic(path,row)
            summary = transport.stream_summary(row["stream"])
            identity_breach = ((summary["models"] and not set(summary["models"]) <= set(transport.MODELS))
                or (summary["providers"] and summary["providers"] != [transport.PROVIDER])
                or len(summary["models"]) > 1 or len(summary["ids"]) > 1
                or row["stream"].get("secret_redacted"))
            if identity_breach: self.stop.set()
            if summary["generation_id"]:
                for offset in (0,20,40,60):
                    self.sleep(max(0,row["stream"]["ended_unix"]+offset-self.clock()))
                    observation = self.lookup(summary["generation_id"],self.secret)
                    observation,hit = transport.redact(observation,self.secret)
                    observation["secret_redacted"] = hit or observation.get("secret_redacted",False)
                    observation["scheduled_offset_seconds"] = offset
                    row["receipts"].append(observation)
                    atomic(path,row)
                    current = transport.assess(row)
                    if current["receipt_certified"]: break
                    if observation.get("http_status") == 200: self.stop.set(); break
            row["assessment"] = transport.assess(row)
            s = row["assessment"]["stream"]
            details = (s.get("usage") or {}).get("completion_tokens_details") or {}
            native_reasoning = details.get("reasoning_tokens")
            valid_reasoning = (type(native_reasoning) is int and native_reasoning > 0
                               and native_reasoning <= (s.get("usage") or {}).get("completion_tokens",0))
            row.update(status="recorded",final_content=final_content(row["stream"]) if s["complete"] else None,
                       native_reasoning_present=valid_reasoning,ended_unix=self.clock())
            atomic(path,row)
            a = row["assessment"]
            self.ledger.settle(STAGE+"-"+request_id,a["accounted_usd"],a["receipt_certified"],sha(path.read_bytes()))
            if Decimal(a["accounted_usd"]) > reserve or (s["complete"] and not valid_reasoning):
                self.stop.set()
            if not a["passed"]:
                with self.guard:
                    self.transport_failures += 1
                    if self.transport_failures >= 2: self.stop.set()
            if not a["passed"] or not valid_reasoning or a["stream"]["finish_reasons"] != ["stop"]:
                raise StopEpisode("transport, accounting, reasoning, or output-completion failure")
            return row["final_content"]
        except StopEpisode:
            raise
        except Exception as exc:
            self.stop.set()
            row.update(instrument_error=type(exc).__name__)
            atomic(path,row)
            raise StopEpisode("instrument failure") from None

    def run(self):
        p = self.manifest["protocol"]
        require(0 <= self.clock()-p["metadata_observed_unix"] <= 3600,"metadata stale; no launch")
        with (self.root/"writer.lock").open("a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
            require(not list((self.root/"sessions").iterdir()) and not list((self.root/"calls").iterdir()),
                    "already started; do not restart")
            self.ledger.allocate(STAGE,STAGE_CAP)
            atomic(self.root/"sessions/start.json",dict(protocol=self.protocol,started_unix=self.clock(),pid=os.getpid()))
            def gate(case):
                try:
                    answer = self.call(case["id"],case["messages"],case["seed"])
                    return dict(id=case["id"],correct=gate_correct(answer,case["expected"]))
                except Exception as exc:
                    return dict(id=case["id"],correct=False,error_type=type(exc).__name__)
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                gates = list(pool.map(gate,p["gate"]))
            gate_passed = all(r["correct"] for r in gates) and not self.stop.is_set()
            atomic(self.root/"sessions/gate.json",dict(protocol=self.protocol,cases=gates,passed=gate_passed))
            print(json.dumps(dict(event="gate_terminal",passed=gate_passed,correct=sum(r["correct"] for r in gates),budget=self.ledger.snapshot())),flush=True)
            def one(case):
                if not gate_passed or self.stop.is_set():
                    result = dict(id=case["id"],status="not_started")
                else:
                    try:
                        def ask(actor,stage,messages,index):
                            return self.call(case["id"]+f"-{index:02d}",messages,case["seed_base"]+index)
                        evidence = game.episode(p["fixtures"][case["fixture_index"]],case["arm"],ask)
                        result = dict(id=case["id"],status="complete",**evidence)
                    except Exception as exc:
                        result = dict(id=case["id"],status="incomplete",error_type=type(exc).__name__)
                atomic(self.root/"episodes"/(case["id"]+".json"),result)
                print(json.dumps(dict(event="episode_terminal",id=case["id"],status=result["status"],budget=self.ledger.snapshot())),flush=True)
                return dict(id=case["id"],status=result["status"])
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                episodes = list(pool.map(one,p["assignments"]))
            terminal = dict(protocol=self.protocol,gate_passed=gate_passed,episodes=episodes,
                            global_safety_stop=self.stop.is_set(),transport_failures=self.transport_failures,
                            budget=self.ledger.snapshot(),ended_unix=self.clock())
            atomic(self.root/"sessions/terminal.json",terminal)
            return terminal


def audit(root,ledger_root=BUDGET):
    """Offline replay of every assigned episode, failed prefixes and accounting."""
    from fractions import Fraction
    root = Path(root); manifest,protocol = verify(root); p = manifest["protocol"]
    terminal = load(root/"sessions/terminal.json")
    require(terminal["protocol"] == protocol,"terminal protocol")
    require(not list(root.rglob("*.partial")),"partial writes remain")
    rows = {f.stem:load(f) for f in (root/"calls").glob("*.json")}
    require(len(rows) <= 278,"attempt limit")
    accounted = Decimal(0); valid = {}; ledger_keys=set()
    for key,row in rows.items():
        require(row["id"] == key and row["protocol"] == protocol and row["attempt"] == 1,"call provenance")
        wire = canonical(row["request"])
        require(wire == row["request_text"] and sha(wire.encode()) == row["request_sha256"],"wire changed")
        require(row["request"] == request_for(row["request"]["messages"],row["request"]["seed"]),"native config changed")
        bound=len(wire.encode())+1024
        reserve=(bound*transport.PRICE_IN+transport.OUTPUT_BOUND*transport.PRICE_OUT)/Decimal(1000000)
        require(row["input_token_bound"] == bound and Decimal(row["reserved_usd"]) == reserve,"reservation changed")
        entry=load(Path(ledger_root)/"entries"/(STAGE+"-"+key+".json")); ledger_keys.add(entry["request_id"])
        require(entry["request_sha256"] == row["request_sha256"] and Decimal(entry["reserved_usd"]) == reserve,"ledger request mismatch")
        if "assessment" in row and not row.get("instrument_error"):
            a=transport.assess(row)
            require(a == row["assessment"],"billing assessment changed")
            require(entry["status"] == "settled" and entry["evidence_sha256"] == sha((root/"calls"/(key+".json")).read_bytes()),"settlement evidence")
            require(entry["accounted_usd"] == a["accounted_usd"] and entry["certified"] == a["receipt_certified"],"settlement mismatch")
            final=final_content(row["stream"]) if a["stream"]["complete"] else None
            require(final == row["final_content"],"final content mismatch")
            usage=a["stream"].get("usage") or {}
            n=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
            native=(type(n) is int and 0 < n <= usage.get("completion_tokens",0))
            require(row["native_reasoning_present"] == native,"reasoning report changed")
            valid[key]=a["passed"] and a["stream"]["finish_reasons"] == ["stop"] and native
        else:
            valid[key]=False
        accounted += Decimal(entry.get("accounted_usd",entry["reserved_usd"]))
    entries=[load(f) for f in (Path(ledger_root)/"entries").glob("*.json")]
    require({e["request_id"] for e in entries if e["stage"] == STAGE} == ledger_keys,"unmatched stage reservation")
    require(accounted <= STAGE_CAP,"stage cap exceeded")
    used=set(); gate_results=[]
    for case in p["gate"]:
        key=case["id"]
        if key in rows:
            used.add(key); require(rows[key]["request"] == request_for(case["messages"],case["seed"]),"gate request changed")
        gate_results.append(dict(id=key,correct=bool(valid.get(key) and gate_correct(rows[key]["final_content"],case["expected"]))))
    gate_record=load(root/"sessions/gate.json")
    require(gate_record["protocol"] == protocol and gate_record["passed"] == terminal["gate_passed"],"gate protocol/status")
    require([{k:r[k] for k in ("id","correct")} for r in gate_record["cases"]] == gate_results,"gate readout mismatch")
    require(not terminal["gate_passed"] or all(r["correct"] for r in gate_results),"failed gate bypass")
    reports=[]
    for case in p["assignments"]:
        saved=load(root/"episodes"/(case["id"]+".json")); count=0
        def ask(actor,stage,messages,index):
            nonlocal count
            key=case["id"]+f"-{index:02d}"
            if key not in rows: raise StopEpisode("missing decision")
            used.add(key);count+=1
            if rows[key]["request"] != request_for(messages,case["seed_base"]+index):
                raise RuntimeError("episode request changed")
            if not valid[key]: raise StopEpisode("failed call")
            return rows[key]["final_content"]
        replay=None
        try: replay=game.episode(p["fixtures"][case["fixture_index"]],case["arm"],ask)
        except StopEpisode: pass
        except (ValueError,TypeError,KeyError):
            require(saved["status"] == "incomplete","unexpected parse failure")
        if replay is not None:
            require(saved == dict(id=case["id"],status="complete",**replay),"episode replay mismatch")
        else:
            require(saved["status"] != "complete","missing episode marked complete")
            require(not count or saved["status"] == "incomplete","admitted episode marked not started")
        require(terminal["gate_passed"] or count == 0,"institutional call after failed gate")
        reports.append(dict(assignment=case,status=saved["status"],observed_calls=count,
                            outcome=replay["outcome"] if replay else None))
    require(used == set(rows),"unexpected or post-failure call")
    require(terminal["episodes"] == [dict(id=r["assignment"]["id"],status=r["status"]) for r in reports],"terminal episode inventory")
    require({f.stem for f in (root/"episodes").glob("*.json")} == {c["id"] for c in p["assignments"]},"episode file inventory")
    contrasts=[]
    for i,fixture in enumerate(p["fixtures"]):
        found={r["assignment"]["arm"]:r for r in reports if r["assignment"]["fixture_index"] == i}
        for a,b in (("public_promise","member_enforcement"),("member_enforcement","universal_clearance")):
            intervals=[]
            for arm in (a,b):
                outcome=found[arm]["outcome"]
                value=Fraction(outcome["mean_normalized_regret"]) if outcome else None
                intervals.append((value,value) if value is not None else (Fraction(0),Fraction(1)))
            paired=all(found[x]["outcome"] is not None for x in (a,b))
            behavioral=None
            if paired:
                left,right=found[a]["outcome"],found[b]["outcome"]
                behavioral=dict(final_projects_changed=left["final_terms"]["projects"] != right["final_terms"]["projects"],
                    final_coalition_changed=left["final_terms"]["coalition"] != right["final_terms"]["coalition"],
                    final_order_changed=left["final_terms"]["first"] != right["final_terms"]["first"],
                    consent_changed=left["consent"] != right["consent"],
                    all_principal_utility_difference=[y-x for x,y in zip(left["utility"],right["utility"])],
                    proposed_full_delivery_difference=[y-x for x,y in zip(left["final_full_delivery_utility"],right["final_full_delivery_utility"])])
            contrasts.append(dict(fixture=fixture["id"],contrast=b+" minus "+a,
                regret_difference_bounds=[str(intervals[1][0]-intervals[0][1]),str(intervals[1][1]-intervals[0][0])],
                paired_complete=paired,behavioral_and_distributional=behavioral))
    return dict(protocol=protocol,gate_correct=sum(r["correct"] for r in gate_results),
                complete_episodes=sum(r["status"] == "complete" for r in reports),assignments=reports,
                calls=len(rows),accounted_usd=str(accounted),contrasts=contrasts,
                caveat="Nine selected-fixture discovery episodes. Bounds are finite-outcome missingness bounds, not confidence intervals. Enforcement is mechanical, not observed compliance.")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("root",type=Path)
    parser.add_argument("--prepare",action="store_true")
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--audit",action="store_true")
    parser.add_argument("--expected-protocol")
    args=parser.parse_args()
    require(sum((args.prepare,args.run,args.audit)) == 1,"choose one mode")
    if args.prepare:
        print(prepare(args.root));return
    require(verify(args.root)[1] == args.expected_protocol,"expected protocol required")
    if args.audit:
        print(json.dumps(audit(args.root),indent=2));return
    result=Runner(args.root,secret=transport.read_key()).run()
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
