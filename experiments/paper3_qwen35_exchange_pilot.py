"""Unfrozen candidate 24-episode reciprocal-exchange discovery pilot.

Its Qwen3.5/Darkbloom engineering prerequisite failed, so this runner cannot
freeze or run. Selected opportunity structures are not a representative sample.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import random
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import paper3_qwen35_darkbloom_gate as gate
from paper3 import coalition_contracts as game
from paper3 import coalition_exchange_analysis as analysis
from paper3 import coalition_exchange_design as design
from paper3 import hosted_reasoning_channel_calls as service
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure

t = gate.t
require, load, sha, canonical = t.require, t.load, t.sha, t.canonical
STAGE = "pivot_b_qwen35_exchange_pilot_v1"
CAP = Decimal("1.50")
WORKERS = 2
MAX_CALLS = 720
BUDGET = gate.BUDGET
GATE_ROOT = ROOT/"results/paper3/pivot_b_qwen35_darkbloom_gate_v1"
GATE_PROTOCOL = "58deae265a067fa66629bab867969a0d4b6afa9eecbeeeb53d81ed31f2b8cf4e"
request_for = gate.request_for
score = gate.score


class StopEpisode(Exception):
    pass


def schedule():
    rows = design.schedule()
    random.Random(353999).shuffle(rows)
    return rows


def prerequisite():
    require(gate.verify(GATE_ROOT)[1] == GATE_PROTOCOL, "gate protocol changed")
    report = gate.audit(GATE_ROOT)
    require(report["gate_passed"] and report["calls"] == 16, "Qwen3.5 gate did not pass")
    return dict(protocol=GATE_PROTOCOL, report=report,
                report_sha256=sha(canonical(report).encode()),
                native_template=request_for([], 0, "action", "draft"),
                limitation="An engineering gate is not a strategic-competence or publication result.")


def prerequisite_paths():
    paths = [ROOT/rel for rel in load(GATE_ROOT/"manifest.json")["sources"]]
    paths += [p for p in GATE_ROOT.rglob("*.json") if p.is_file()]
    paths += [p for p in (BUDGET/"entries").glob(gate.STAGE+"-*.json")]
    paths += [BUDGET/"stages"/(gate.STAGE+".json")]
    return paths


def make_case(assignment, actor, stage, messages, index):
    require(0 <= index < 30 and actor in game.ACTORS, "decision position")
    key = assignment["id"]+f"-{index:02d}"
    req = request_for(messages, assignment["seed_base"]+index, "action", stage)
    wire = canonical(req)
    bound = len(wire.encode())+1024
    require(bound+gate.CONFIG["output_bound"] <= gate.CONTEXT, "conservative context bound")
    reserve = (bound*gate.PRICE_IN+gate.CONFIG["output_bound"]*gate.PRICE_OUT)/Decimal(1000000)
    return dict(id=key, context=dict(kind="action", stage=stage, actor=actor,
                index=index, fixture_index=assignment["fixture_index"],
                form=assignment["form"], block=assignment["block"],
                arm=assignment["arm"], dominant_projects=None),
                request=req, request_text=wire, request_sha256=sha(wire.encode()),
                input_token_bound=bound, reserved_usd=str(reserve))


def seed_audit(root=ROOT):
    planned = {s["seed_base"]+j for s in schedule() for j in range(30)}
    observed, inventory = set(), []
    def walk(v, key=""):
        if isinstance(v, dict):
            for k, x in v.items(): walk(x, k)
        elif isinstance(v, list):
            for x in v: walk(x, key)
        elif type(v) is int and ("seed" in key.lower() or key in ("planned", "planned_unique")):
            observed.add(v)
    for base, dirs, files in os.walk(Path(root)/"results/paper3"):
        dirs[:] = [d for d in dirs if not any(x in d for x in
                    ("portable", "bundle", "export", "__pycache__", "code"))]
        for name in files:
            path = Path(base)/name
            if name == "manifest.json" or (path.parent.name == "calls" and name.endswith(".json")):
                row = load(path)
                walk(row.get("request", row) if path.parent.name == "calls" else row)
                inventory.append((str(path.relative_to(root)), sha(path.read_bytes())))
    expanded = {281000+1000*i+j for i in range(12) for j in range(25)}
    expanded |= {301000+1000*i+100*r+j for i in range(2) for r in range(2) for j in range(25)}
    expanded |= {311000+1000*i+j for i in range(4) for j in range(25)}
    expanded |= set(range(310000, 310008)) | set(range(315000, 315004))
    expanded |= {a["seed_base"]+j for a in
                 __import__("paper3.coalition_jurisdiction_design", fromlist=["schedule"]).schedule(
                     tuple(350000+100*i for i in range(8))) for j in range(30)}
    expanded |= set(range(gate.SEED, gate.SEED+16))
    overlap = planned & (observed | expanded)
    require(not overlap, "old seed overlap")
    return dict(planned_unique=sorted(planned), overlap=sorted(overlap),
                historical_files=len(inventory), inventory_sha256=sha(canonical(sorted(inventory)).encode()),
                pairing="Same requested stage seeds across forms and arms within each profile/repeat; determinism not guaranteed.")


def specification():
    profiles = design.fixtures()
    return dict(name=STAGE, max_calls=MAX_CALLS, new_gate_calls=0, workers=WORKERS,
        cap_usd=str(CAP), budget_cap_usd="10.00", assignments=schedule(),
        profiles=profiles,
        displayed_profiles=[[design.display_profile(p, f) for f in (0, 1)] for p in profiles],
        opportunities=[design.opportunities(p) for p in profiles],
        ex_ante_exposed=[list(x) for x in design.EX_ANTE_EXPOSED],
        native_template=request_for([], 0, "action", "draft"),
        prerequisite_protocol=GATE_PROTOCOL,
        reasoning_evidence=gate.specification()["reasoning_evidence"],
        inference_retries=0, receipt_offsets_seconds=[0, 20, 40, 60],
        failure_rule="Invalid/unusable content ends that episode. Two transport/accounting failures or any source/identity/credential/budget/instrument breach stop new admissions; already admitted calls finish. No restart, repair, retry, replacement or provider fallback. Preserve all prefixes and reservations.",
        feasibility_gate="All 24 episodes and eight three-arm blocks complete with no global safety stop. Engineering completion is not scientific success.",
        treatment_relevance_gate="In each profile at least one complete member-enforcement episode has an activated contract and a signer with negative second-project marginal utility whose ballot could be pivotal. Actual controller flips are outcomes, not required for relevance.",
        discovery_readout="All seven principals, draft/final offers, consent, requested/executed ballots, pivotal reneging, ordinary-vote bypass and finite missingness bounds. Public versus member and member versus universal contrasts reported for every block. No conditional-only-on-formed-contract estimand.",
        limitations="Two theory-selected payoff structures, two crossed label/role forms and two requested seed repeats, three authority rules. This is mechanism discovery, not population evidence or causal identification of intent. Seeds do not guarantee matched randomness; model/provider/quantization differ from Qwen3-32B. Mechanical enforcement alone is not an empirical finding. Any interesting pattern requires a separate frozen out-of-sample validation and independent model family before a paper claim.")


def prepare(root):
    root = Path(root)
    require(not root.exists(), "fresh directory required")
    inherited, seeds = prerequisite(), seed_audit()
    with t.opener().open(gate.METADATA_URL, timeout=20) as response:
        metadata = json.load(response)
    gate.check_metadata(metadata)
    budget = Ledger(BUDGET).snapshot()
    require(budget["pending"] == 0 and
            Decimal(budget["accounted_usd"])+CAP <= Decimal("10"), "budget baseline")
    paths = closure(ROOT, [Path(__file__), ROOT/"paper3/source_closure.py",
        ROOT/"analysis/paper3_contracts_archive.py",
        ROOT/"tests/test_paper3_qwen35_exchange_pilot.py",
        ROOT/"tests/test_paper3_coalition_exchange_analysis.py",
        ROOT/"tests/test_paper3_coalition_exchange_design.py",
        BUDGET/"authority.json", *prerequisite_paths()])
    snapshot = {str(p.relative_to(ROOT)): p.read_text() for p in paths}
    protocol = dict(**specification(), inherited_prerequisite=inherited,
        seed_audit=seeds, pre_stage_budget=budget,
        endpoint_metadata=metadata, metadata_observed_unix=time.time())
    manifest = dict(protocol=protocol, sources={p:sha(v.encode()) for p, v in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    for sub in ("calls", "decisions", "episodes", "sessions"):
        (root/sub).mkdir()
    atomic(root/"sources.json", snapshot)
    atomic(root/"manifest.json", manifest)
    return sha(canonical(manifest).encode())


def verify(root, code_root=ROOT):
    root = Path(root)
    m = load(root/"manifest.json")
    snap = load(root/"sources.json")
    require(set(snap) == set(m["sources"]), "source inventory")
    for rel, want in m["sources"].items():
        require(not Path(rel).is_absolute() and ".." not in Path(rel).parts, "unsafe source")
        require(sha((Path(code_root)/rel).read_bytes()) == sha(snap[rel].encode()) == want,
                "frozen source changed: "+rel)
    require(all(m["protocol"].get(k) == v for k, v in specification().items()),
            "specification changed")
    inherited = m["protocol"]["inherited_prerequisite"]
    require(inherited["protocol"] == GATE_PROTOCOL and inherited["report"]["gate_passed"] and
            inherited["report_sha256"] == sha(canonical(inherited["report"]).encode()),
            "gate prerequisite")
    require(inherited["native_template"] == request_for([], 0, "action", "draft"),
            "native configuration differs")
    require(m["protocol"]["seed_audit"]["planned_unique"] == sorted({
        s["seed_base"]+j for s in schedule() for j in range(30)}) and
        not m["protocol"]["seed_audit"]["overlap"], "seed audit")
    gate.check_metadata(m["protocol"]["endpoint_metadata"])
    return m, sha(canonical(m).encode())


def execute(root, ledger_root=BUDGET, secret=None, send=None, lookup=None,
            clock=time.time, sleep=time.sleep):
    root = Path(root)
    m, protocol = verify(root)
    require(prerequisite() == m["protocol"]["inherited_prerequisite"],
            "gate replay changed")
    require(0 <= clock()-m["protocol"]["metadata_observed_unix"] <= 3600,
            "stale endpoint metadata")
    with (root/"writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(all(not list((root/sub).iterdir()) for sub in
                    ("calls", "decisions", "episodes", "sessions")),
                "already started; no restart")
        ledger = Ledger(ledger_root)
        require(ledger.snapshot() == m["protocol"]["pre_stage_budget"],
                "pre-stage accounting changed")
        ledger.allocate(STAGE, CAP)
        atomic(root/"sessions/start.json", dict(protocol=protocol,
               pid=os.getpid(), started_unix=clock()))
        calls = service.Calls(root, ledger_root, STAGE, MAX_CALLS,
                              lambda:verify(root), score, gate.CONFIG,
                              secret, send, lookup, clock, sleep)
        def one(assignment):
            if calls.stop.is_set():
                result = dict(id=assignment["id"], status="not_started")
            else:
                try:
                    def ask(actor, stage, messages, index):
                        case = make_case(assignment, actor, stage, messages, index)
                        path = root/"decisions"/(case["id"]+".json")
                        atomic(path, dict(case=case, result=dict(id=case["id"], status="prepared")))
                        status = calls.one(case)
                        atomic(path, dict(case=case, result=status))
                        if status["status"] != "recorded":
                            raise StopEpisode("request not recorded")
                        row = load(root/"calls"/(case["id"]+".json"))
                        if not (row["result"]["usable"] and row["result"]["valid_action"]):
                            raise StopEpisode("unusable action")
                        return row["final_content"]
                    evidence = design.episode(
                        m["protocol"]["displayed_profiles"][assignment["fixture_index"]][assignment["form"]],
                        assignment["arm"], ask)
                    result = dict(id=assignment["id"], status="complete", **evidence)
                except StopEpisode as exc:
                    result = dict(id=assignment["id"], status="incomplete", error_type=type(exc).__name__)
                except Exception as exc:
                    calls.stop.set()
                    result = dict(id=assignment["id"], status="incomplete", error_type=type(exc).__name__)
            atomic(root/"episodes"/(assignment["id"]+".json"), result)
            print(json.dumps(dict(event="exchange_episode_terminal", id=assignment["id"],
                  status=result["status"], budget=ledger.snapshot())), flush=True)
            return dict(id=assignment["id"], status=result["status"])
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            episodes = list(pool.map(one, schedule()))
        terminal = dict(protocol=protocol, episodes=episodes,
            results=[load(p)["result"] for p in sorted((root/"decisions").glob("*.json"))],
            global_safety_stop=calls.stop.is_set(), transport_failures=calls.transport_failures,
            budget=ledger.snapshot(), ended_unix=clock())
        atomic(root/"sessions/terminal.json", terminal)
        return terminal


def audit(root, ledger_root=BUDGET):
    root = Path(root)
    m, protocol = verify(root)
    terminal = load(root/"sessions/terminal.json")
    require(terminal["protocol"] == load(root/"sessions/start.json")["protocol"] == protocol,
            "terminal protocol")
    require(prerequisite() == m["protocol"]["inherited_prerequisite"],
            "gate replay changed")
    rows = {p.stem:load(p) for p in (root/"calls").glob("*.json")}
    decisions = {p.stem:load(p) for p in (root/"decisions").glob("*.json")}
    require(len(rows) <= MAX_CALLS, "attempt ceiling")
    used, reports = set(), []
    for assignment in schedule():
        saved = load(root/"episodes"/(assignment["id"]+".json"))
        count = 0
        def ask(actor, stage, messages, index):
            nonlocal count
            case = make_case(assignment, actor, stage, messages, index)
            key = case["id"]
            if key not in decisions:
                raise StopEpisode("missing decision")
            used.add(key)
            require(decisions[key]["case"] == case, "episode request or role changed")
            if key not in rows:
                raise StopEpisode("request not admitted")
            count += 1
            result = score(rows[key], case)
            if not (result["usable"] and result["valid_action"]):
                raise StopEpisode("unusable action")
            return service.final_content(rows[key]["stream"])
        replay = None
        try:
            replay = design.episode(
                m["protocol"]["displayed_profiles"][assignment["fixture_index"]][assignment["form"]],
                assignment["arm"], ask)
        except StopEpisode:
            pass
        if replay is not None:
            require(saved == dict(id=assignment["id"], status="complete", **replay),
                    "episode replay differs")
        else:
            require(saved["status"] in ("incomplete", "not_started"),
                    "incomplete episode marked complete")
            require(not count or saved["status"] == "incomplete",
                    "admitted episode marked unstarted")
        reports.append(analysis.assignment_report(
            assignment, replay["events"] if replay else None,
            replay["outcome"] if replay else None))
        reports[-1]["observed_calls"] = count
        reports[-1]["saved_status"] = saved["status"]
    require(used == set(decisions) and set(rows) <= used,
            "unexpected or post-failure decisions")
    require({p.stem for p in (root/"episodes").glob("*.json")} ==
            {a["id"] for a in schedule()}, "episode inventory")
    require(terminal["episodes"] == [dict(id=r["assignment"]["id"],
            status=r["saved_status"]) for r in reports], "terminal episode inventory")
    cases = [decisions[k]["case"] for k in sorted(used)]
    require(terminal["results"] == [decisions[k]["result"] for k in sorted(used)],
            "decision status inventory")
    call_reports, cost = service.audit_records(root, ledger_root, STAGE,
        protocol, cases, terminal, score, gate.CONFIG)
    require(cost <= CAP, "stage cap exceeded")
    screen = analysis.pilot_screen(reports)
    screen["feasibility_passed"] &= not terminal["global_safety_stop"]
    screen["treatment_relevance_passed"] &= not terminal["global_safety_stop"]
    return dict(protocol=protocol, inherited_gate=GATE_PROTOCOL, new_gate_calls=0,
        assignments=reports, call_reports=call_reports, calls=len(rows),
        screen=screen, contrasts=analysis.contrasts(reports),
        accounted_usd=str(cost), global_safety_stop=terminal["global_safety_stop"],
        caveat=specification()["limitations"])


def archive_helpers():
    import importlib.util
    spec = importlib.util.spec_from_file_location("b_archive",
                ROOT/"analysis/paper3_contracts_archive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def export(root, ledger_root, target, destination, secret=None):
    h = archive_helpers()
    root, ledger_root, target = map(lambda p:Path(p).resolve(),
                                    (root, ledger_root, target))
    require((root/"sessions/terminal.json").is_file(), "not terminal")
    require(not target.exists() and not Path(destination).exists(), "archive exists")
    with (root/"writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        with Ledger(ledger_root).locked():
            report = audit(root, ledger_root)
            m, protocol = verify(root)
            content = {"code/"+p:v.encode() for p, v in load(root/"sources.json").items()}
            for prefix, directory in (("run", root), ("ledger", ledger_root)):
                for p in directory.rglob("*"):
                    require(not p.is_symlink(), "symlink in archive source")
                    if p.is_file() and p.suffix == ".json":
                        content[prefix+"/"+str(p.relative_to(directory))] = p.read_bytes()
            content["expected_report.json"] = (json.dumps(report, sort_keys=True, indent=2)+"\n").encode()
    content["README.md"] = ("# Qwen3.5 reciprocal-exchange pilot\n\nAll 24 selected institutional assignments, failed prefixes, all-principal outcomes, comparator sets and reservations retained. "
        "No old response is repaired or replaced. From a fresh extracted directory run:\n\n"
        "`python3 -I -S code/experiments/paper3_qwen35_exchange_pilot.py . --replay --expected-protocol "+protocol+"`\n\n"
        "Standard library, no key/network/weights/original checkout. Exact audit comparison. "
        "Review trusted code: hashes establish consistency, not provider authenticity or generalization.\n").encode()
    for rel, data in content.items():
        h.safe(target, rel)
        h.credentials(data, secret)
    metadata = dict(format=h.FORMAT, experiment_family=STAGE,
        protocol=protocol, files={rel:sha(data) for rel, data in sorted(content.items())})
    target.mkdir(parents=True, exist_ok=False)
    for rel, data in content.items():
        p = h.safe(target, rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("xb") as stream:
            stream.write(data)
    with (target/"bundle.json").open("x") as stream:
        json.dump(metadata, stream, sort_keys=True, indent=2)
    return dict(protocol=protocol, files=len(content), sha256=h.archive(target, destination))


def replay(root, expected):
    h = archive_helpers()
    root = Path(root).resolve()
    m = h.verify_bundle(root, expected)
    require(m["experiment_family"] == STAGE, "wrong archive")
    require(ROOT == root/"code", "run replay from bundled code")
    sys.addaudithook(h.offline_guard)
    require(verify(root/"run")[1] == expected, "frozen protocol changed")
    report = audit(root/"run", root/"ledger")
    require(report == load(root/"expected_report.json"), "original audit differs")
    report["portable_replay"] = dict(protocol=expected, exact_report_match=True)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    group = p.add_mutually_exclusive_group(required=True)
    for mode in ("prepare", "run", "audit", "export", "replay"):
        group.add_argument("--"+mode, action="store_true")
    p.add_argument("--expected-protocol")
    p.add_argument("--target", type=Path)
    p.add_argument("--archive", type=Path)
    args = p.parse_args()
    if args.prepare:
        print(prepare(args.root)); return
    if args.replay:
        require(args.expected_protocol, "expected protocol required")
        print(json.dumps(replay(args.root, args.expected_protocol), indent=2)); return
    require(verify(args.root)[1] == args.expected_protocol, "expected protocol required")
    if args.export:
        require(args.target and args.archive, "export paths required")
        print(json.dumps(export(args.root, BUDGET, args.target,
              args.archive, t.read_key()))); return
    print(json.dumps(audit(args.root) if args.audit else
          execute(args.root, secret=t.read_key()), indent=2))


if __name__ == "__main__":
    main()
