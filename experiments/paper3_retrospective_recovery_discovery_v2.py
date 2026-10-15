"""Full accountability discovery, prospectively assigned in two budget batches.

No new qualification calls after the fresh dual-channel gate passes. Immutable portable qualification, sixteen episodes,
two matched frames, all four arms, bounded pre-answer429 reissue only; no content repair or automatic next
batch. A selected-case screen is not publication evidence.
"""
# ruff: noqa: E402
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import fcntl
from functools import cache
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import paper3_transport_diagnostic as t
from experiments import paper3_retrospective_contract_gate_v2 as gate
from paper3 import hosted_reasoning_channel_calls as service
from paper3 import hosted_reasoning_calls as transport
from paper3 import retrospective_contract_calls as coordinator
from paper3 import retrospective_contract_recovery as recovery
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_action_contract_v2 as interface
from paper3 import retrospective_recovery_discovery_v2_requests as requests
from paper3 import retrospective_contract_route_v2 as route
from paper3.retrospective_serial_execution import StopLedger, jsonable, prior_inventory
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure

NAME = "pivot_b_retrospective_recovery_discovery_v2"
CAP = recovery.PROPOSED_STAGE_CAP
TOTAL_STOP = Decimal("10")
WORKERS = 1
MAX_CALLS = 240
BUDGET = ROOT / "results/paper3/pivot_b_budget"
QUALIFICATION = ROOT / "paper3/data/pivot_b_retrospective_contract_gate_v2.zip"
QUALIFICATION_PROTOCOL = "f98c173121fc69ea3b993e05b47ed27b25788dcdb34b6ab846d99011c52111ca"
QUALIFICATION_SHA = None  # Explicit actual archive hash required after a fresh gate pass.
CONFIG = dict(models=[route.MODEL, route.MODEL_ALIAS], provider=route.PROVIDER,
              output_bound=route.OUTPUT_BOUND)
require = t.require


class EpisodeFailure(ValueError):
    pass


def batch_stage(index):
    require(type(index) is int and index in (0, 1), "two batch indices")
    return NAME + f"-b{index}"


def batch_root(root, index):
    batch_stage(index)
    return Path(root) / "batches" / f"batch-{index}"


def scheduled(index):
    batch_stage(index)
    return tuple(r for r in requests.assignments() if r["seed"] == requests.FRAME_SEEDS[index])


def qualification_proof(archive, protocol, expected_sha):
    """Replay unchanged qualified audit against a fresh local extraction.

Before executing, require every embedded source to equal current repository
code and reject extra code/path entries. The archive hash pins all evidence.
    No inference or credentials are used. The complete parent archive's actual
    -I -S replay applies its network/child-process guard to this nested audit.
"""
    archive = Path(archive)
    require(t.sha(archive.read_bytes()) == expected_sha, "qualification archive changed")
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)), "duplicate qualification entries")
        manifest = json.loads(z.read("run/manifest.json"))
        require(t.sha(t.canonical(manifest).encode()) == protocol, "qualification protocol changed")
        require({n for n in names if n.startswith("code/")} ==
                {"code/" + n for n in manifest["sources"]}, "qualification code inventory")
        for name, digest in manifest["sources"].items():
            p = Path(name)
            require(not p.is_absolute() and ".." not in p.parts, "unsafe qualification source")
            require(t.sha(z.read("code/" + name)) == digest == t.sha((ROOT / p).read_bytes()),
                    "qualified source/configuration changed: " + name)
        require(manifest["protocol"]["configuration"] == CONFIG, "qualified native configuration")
        # Also pin the actual sampling/envelope and action schemas, not just model ID.
        envelope = {k: v for k, v in route.request(dict(messages=[], tools=[{}], tool_choice="auto"), 0).items()
                    if k not in ("messages", "tools", "seed")}
        for row in gate.qualification.requests():
            require({k: v for k, v in row["request"].items() if k not in ("messages", "tools", "seed")} ==
                    envelope, "qualified sampling/envelope mismatch")
        for case in gate.qualification.cases():
            fragment = gate.qualification.structured(case)
            require(fragment["messages"][0]["content"] == interface.SYSTEM, "qualified system mismatch")
            if case["kind"] == "action":
                parameters = interface.structured(fragment["messages"], case["game"], case["stage"])[
                    "tools"][0]["function"]["parameters"]
                require(case["parameters"] == parameters, "qualified action schema mismatch")
        with tempfile.TemporaryDirectory(prefix="paper3-qualification-proof-") as directory:
            fresh = Path(directory).resolve()
            helper = gate.archive_helper()
            for info in z.infolist():
                helper.safe(fresh, info.filename)
                require((info.external_attr >> 16) & 0o170000 != 0o120000, "qualification symlink")
            z.extractall(fresh)
            helper.verify_bundle(fresh, protocol)
            report = gate.audit(fresh / "run", fresh / "ledger")
            require(t.canonical(report) == t.canonical(t.load(fresh / "expected_report.json")),
                    "qualification saved-record replay mismatch")
    require(report["gate_passed"] is True and report["calls"] == 18 and len(report["assignments"]) == 18 and
            report["publication_evidence"] is False,
            "qualification was not an exact substantive pass")
    return dict(protocol=protocol, archive_sha256=expected_sha,
                report_sha256=t.sha(t.canonical(report).encode()),
                exact_offline_replay=True, new_gate_calls=0, native_configuration_equal=True,
                calls=report["calls"], recovery_count=0,
                source_hashes=manifest["sources"])


def action_call(assignment, actor, identity, term, stage, context, index):
    request = requests.action_request(assignment, actor, identity, term, stage, context, index)
    bounded = route.reservation(request)
    maximum = next(r for r in requests.legal_history_bounds()["assignments"]
                   if r["id"] == assignment["id"])["input_bounds"][index]
    require(bounded["input_token_bound"] <= maximum, "history exceeds frozen bound")
    return dict(id=assignment["id"] + f"-{index:02d}", request=request, **bounded,
                request_sha256=t.sha(bounded["request_text"].encode()),
                context=dict(assignment_id=assignment["id"], actor=actor, identity=identity,
                             term=term, stage=stage, index=index))


def score(row, case):
    result = dict(usable=False, valid_action=False, exact=False, native_reasoning=None,
                  action=None, failure="instrument_or_unfinished")
    if row.get("instrument_error") or "assessment" not in row:
        return result
    assessed = service.assess(row, CONFIG)
    native = service.native_evidence(assessed["stream"])
    usable = (assessed["passed"] and assessed["stream"]["finish_reasons"] in (["tool_calls"], ["stop"]) and
              native["present"] and row["request"]["reasoning"] == dict(enabled=True, exclude=False))
    result.update(usable=usable, native_reasoning=native)
    if usable:
        try:
            assignment = next(a for a in requests.assignments() if a["id"] == case["context"]["assignment_id"])
            action = interface.decode(assignment["game"], case["context"]["stage"], row["stream"])
            result.update(valid_action=True, exact=True, action=action,
                          channel=interface.decision(row["stream"])["channel"], failure=None)
        except (ValueError, TypeError, KeyError) as exc:
            result["failure"] = str(exc)
    else:
        result["failure"] = "transport_reasoning_or_action_completion"
    return result


def verify_prior_allowed(ledger_root, expected):
    current = {p.name: p for p in (Path(ledger_root) / "entries").glob("*.json")}
    require(set(expected) <= set(current), "prior ledger deleted")
    for name, digest in expected.items():
        require(t.sha(current[name].read_bytes()) == digest, "prior ledger changed")
    require(all(t.load(p)["stage"] in {batch_stage(0), batch_stage(1)}
                for name, p in current.items() if name not in expected), "unrelated spending")


def seed_audit(root=ROOT):
    planned = {requests.ORDER_SEED, *requests.FRAME_SEEDS,
               *(a["seed_base"] + i for a in requests.assignments() for i in range(30))}
    observed, files = set(), []

    def walk(value, key=""):
        if type(value) is dict:
            for k, v in value.items():
                walk(v, k)
        elif type(value) is list:
            for v in value:
                walk(v, key)
        elif type(value) is int and "seed" in key.lower():
            observed.add(value)

    for base, dirs, names in os.walk(Path(root) / "results/paper3"):
        dirs[:] = [d for d in dirs if not any(s in d for s in
                   ("portable", "bundle", "export", "replay", "__pycache__", "code"))]
        for name in names:
            p = Path(base) / name
            if name == "manifest.json" or (p.parent.name == "calls" and name.endswith(".json")):
                value = t.load(p)
                walk(value.get("request", value) if p.parent.name == "calls" else value)
                files.append((str(p.relative_to(root)), t.sha(p.read_bytes())))
    require(not planned & observed, "historical seed collision")
    return dict(planned=sorted(planned), overlap=[], historical_files=len(files),
                inventory_sha256=t.sha(t.canonical(sorted(files)).encode()))


@cache
def specification():
    bounds = requests.legal_history_bounds()
    batches = [dict(index=i, seed=seed, stage=batch_stage(i), cap_usd=str(CAP),
                    assignments=scheduled(i), maximum_calls=MAX_CALLS)
               for i, seed in enumerate(requests.FRAME_SEEDS)]
    for batch in batches:
        ids = {a["id"] for a in batch["assignments"]}
        reserve = sum(Decimal(r["reserved_usd"]) for r in bounds["assignments"] if r["id"] in ids)
        maximum = max(v for row in bounds["assignments"] if row["id"] in ids for v in row["input_bounds"])
        attempt = (Decimal(maximum) * route.PRICE_IN + Decimal(route.OUTPUT_BOUND) * route.PRICE_OUT) / 1000000
        full = recovery.reservation_bound(reserve, attempt)
        require(len(ids) == 8 and full["fits_proposed_stage_cap"], "complete matched-block recovery bound")
        batch.update(base_full_reservation_usd=str(reserve), largest_attempt_usd=str(attempt),
                     full_reservation_usd=full["full_path_usd"], maximum_physical_calls=265)
    return jsonable(dict(name=NAME, workers=WORKERS, total_maximum_calls=480,
        configuration=CONFIG, cumulative_stop_usd=str(TOTAL_STOP), new_gate_calls=0,
        total_maximum_physical_calls=530, transport_policy=dict(maximum_reissues_per_batch=25,
            reissues_per_logical=1, delay_seconds=300, identical_wire=True, retained_reservations=True,
            only_pinned_pre_answer_shared_pool_429=True, no_bad_content_retries=True),
        pairs=requests.pairs(), assignments=requests.assignments(), batches=batches, bound_proof=bounds,
        order_seed=requests.ORDER_SEED, seed_base=requests.DECISION_SEED_BASE,
        authorization=dict(date="2026-10-02", authorized_batches=[0, 1], total_budget_usd="10", stage_cap_usd="3.30", user_instruction="ok keep going until we get a result please", scope="User standing instruction approves routine continuation within original10 unless a major research redesign. Separate fresh transport-only successor: same qualified configuration and scientific design; one bounded identical pre-answer shared-pool429 reissue. Both new blocks conditional on clean previous block and full3.30 admission. Never reopen any old run.", second_batch_requires_explicit_approval=False, no_local_models=True),
        inference_retries=0, serial_technical_calls=30, receipt_offsets_seconds=[0, 20, 40, 60],
        admission="Whole16-assignment freeze first; both blocks authorized prospectively by latest direct human continuation. Batch1 requires clean full batch0 and full $3.30 admission irrespective of outcomes; stop without allocation if remaining original10 cannot cover its cap. Never restart; older runs remain closed.",
        failure="Only pinned pre-answer shared-pool429 permits one identical-wire/seed reissue after shared300-second cooldown, capped25 per block with all reservations retained. A second429, bad/partial answer, unknown failure, billing-only failure, budget or instrument fault stops. No response repair, fallback or new gate calls.",
        scientific_screen="Unchanged two-sided screen: all16 episodes complete; same nonzero conflict-minus-aligned interaction direction in both blocks; |mean|>=0.04 normalized district regret; mean absolute aligned interaction <=half conflict.",
        limitation="Selected synthetic cases, two sequential matched-frame batches, one trajectory/model route. Stipulated office incentive, deterministic citizen assessments, no intrinsic motivation or candidate-quality selection claim. Partial run remains inconclusive; a selected-case lead proposes independent validation, never publication evidence."))


def prepare(root, qualification_archive=QUALIFICATION, qualification_protocol=QUALIFICATION_PROTOCOL,
            qualification_sha=QUALIFICATION_SHA, metadata=None, ledger_root=BUDGET):
    root = Path(root)
    require(not root.exists(), "fresh parent run required")
    require(type(qualification_sha) is str and len(qualification_sha) == 64 and
            all(c in "0123456789abcdef" for c in qualification_sha),
            "explicit successful qualification archive hash required")
    seeds = seed_audit()
    proof = qualification_proof(qualification_archive, qualification_protocol, qualification_sha)
    if metadata is None:
        with t.opener().open(route.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    route.check_endpoint(metadata)
    before = Ledger(ledger_root).snapshot()
    require(Decimal(before["accounted_usd"]) + CAP <= TOTAL_STOP, "first batch exceeds ten-dollar stop")
    require(not any((Path(ledger_root) / "stages" / (batch_stage(i) + ".json")).exists()
                    for i in (0, 1)), "batch stage already allocated; never restart in a fresh root")
    roots = [Path(__file__), ROOT / "analysis/paper3_retrospective_recovery_discovery_v2_audit.py",
             ROOT / "analysis/paper3_contracts_archive.py", BUDGET / "authority.json",
             ROOT / "tests/test_paper3_retrospective_recovery_discovery_v2.py",
             ROOT / "tests/test_paper3_retrospective_action_contract.py",
             ROOT / "tests/test_paper3_retrospective_recovery_discovery_v2_requests.py",
             ROOT / "tests/test_paper3_retrospective_contract_recovery.py",
             ROOT / "tests/test_paper3_retrospective_contract_calls.py",
             *(ROOT / n for n in proof["source_hashes"])]
    sources = {str(p.relative_to(ROOT)): p.read_text() for p in closure(ROOT, roots)}
    protocol = dict(**specification(), qualification_proof=proof, seed_audit=seeds,
                    pre_stage_budget=before, prior_ledger_entries=prior_inventory(ledger_root),
                    endpoint_metadata=metadata, metadata_observed_unix=time.time())
    manifest = dict(protocol=protocol, sources={n: t.sha(s.encode()) for n, s in sources.items()})
    root.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(qualification_archive, root / "qualification.zip")
    for i in (0, 1):
        for name in ("calls", "decisions", "episodes", "sessions", "attempts", "logicals", "recoveries"):
            (batch_root(root, i) / name).mkdir(parents=True, exist_ok=False)
    atomic(root / "sources.json", sources)
    atomic(root / "manifest.json", manifest)
    return t.sha(t.canonical(manifest).encode())


def verify(root):
    root = Path(root)
    manifest, sources = t.load(root / "manifest.json"), t.load(root / "sources.json")
    require(set(manifest["sources"]) == set(sources), "source inventory")
    for name, digest in manifest["sources"].items():
        p = Path(name)
        require(not p.is_absolute() and ".." not in p.parts, "unsafe source path")
        require(t.sha((ROOT / p).read_bytes()) == digest == t.sha(sources[name].encode()),
                "frozen source changed: " + name)
    require(all(t.canonical(manifest["protocol"].get(k)) == t.canonical(v)
                for k, v in specification().items()), "protocol changed")
    proof = manifest["protocol"]["qualification_proof"]
    require(t.sha((root / "qualification.zip").read_bytes()) == proof["archive_sha256"],
            "qualification archive changed")
    require(proof["exact_offline_replay"] is True and proof["new_gate_calls"] == 0 and
            proof["native_configuration_equal"] is True, "qualified proof flags")
    require(not manifest["protocol"]["seed_audit"]["overlap"], "seed overlap")
    route.check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def resolve_transport(send=None, lookup=None):
    """Resolve the qualified backend before allocating or recording startup."""
    if send is None:
        require(lookup is None, "no partial live transport override")
        send, lookup = transport.transmit, t.receipt_lookup
    require(callable(send) and callable(lookup), "explicit paired transport required")
    return send, lookup


def execute(root, batch, ledger_root=BUDGET, metadata=None, secret=None, send=None,
            lookup=None, clock=time.time, sleep=time.sleep):
    resolved_send, resolved_lookup = resolve_transport(send, lookup)
    require(type(batch) is int and batch in (0, 1), "two frozen batch indices")
    root, local = Path(root), batch_root(root, batch)
    manifest, protocol = verify(root)
    require(batch in manifest["protocol"]["authorization"]["authorized_batches"], "batch not authorized")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(all(not list((local / n).iterdir()) for n in ("calls", "decisions", "episodes", "sessions")),
                "batch already started; never restart")
        if batch == 1:
            previous = audit(root, ledger_root)
            require(previous["batches"][0]["complete"] is True and
                    not previous["batches"][0]["global_safety_stop"], "previous batch incomplete or failed")
        if metadata is None:
            if send is None:
                with t.opener().open(route.METADATA_URL, timeout=20) as response:
                    metadata = json.load(response)
            else:
                metadata = manifest["protocol"]["endpoint_metadata"]
        route.check_endpoint(metadata)
        metadata_observed = clock()
        proof = manifest["protocol"]["qualification_proof"]
        require(qualification_proof(root / "qualification.zip", proof["protocol"], proof["archive_sha256"]) ==
                proof, "qualification proof changed")
        require(0 <= clock() - metadata_observed <= 3600, "stale batch metadata")
        ledger = StopLedger(ledger_root)
        verify_prior_allowed(ledger_root, manifest["protocol"]["prior_ledger_entries"])
        before = ledger.snapshot()
        if batch == 0:
            require(before == manifest["protocol"]["pre_stage_budget"], "pre-stage budget changed")
        require(Decimal(before["accounted_usd"]) + CAP <= TOTAL_STOP, "batch cap exceeds ten-dollar stop")
        ledger.allocate(batch_stage(batch), CAP)
        atomic(local / "sessions/start.json", dict(protocol=protocol, batch=batch, pid=os.getpid(),
            started_unix=clock(), pre_batch_budget=before, prior_ledger_entries=prior_inventory(ledger_root),
            endpoint_metadata=metadata, metadata_observed_unix=metadata_observed))
        calls = coordinator.Calls(local, ledger_root, batch_stage(batch), lambda: verify(root),
            score, send=resolved_send, lookup=resolved_lookup, secret=secret, clock=clock, sleep=sleep)

        def stop_event(call_id, kind):
            calls.halt(call_id, kind)
            with calls.guard:
                path = local / "sessions/safety_stop.json"
                if not path.exists():
                    atomic(path, dict(protocol=protocol, batch=batch, call_id=call_id,
                                      kind=kind, detected_unix=clock()))

        def decide(call):
            path = local / "decisions" / (call["id"] + ".json")
            atomic(path, dict(case=call, result=dict(id=call["id"], status="prepared")))
            status = calls.one(call)
            atomic(path, dict(case=call, result=status))
            if status["status"] != "recorded":
                stop_event(call["id"], "logical_request_not_recorded")
                raise EpisodeFailure("request_not_recorded")
            return status["action"]

        def one(assignment):
            terms = [None, None]
            saved = dict(id=assignment["id"], status="not_started", terms=terms, outcome=None)
            if not calls.stop.is_set():
                def on_term(term):
                    terms[term.index] = jsonable(term)
                    atomic(local / "episodes" / (assignment["id"] + ".json"),
                           dict(id=assignment["id"], status="in_progress", terms=terms, outcome=None))

                def ask(actor, identity, term, stage, context, index):
                    return decide(action_call(assignment, actor, identity, term, stage, context, index))
                try:
                    outcome = institution.episode(assignment["game"], assignment["arm"], ask, on_term)
                    saved.update(status="completed", outcome=jsonable(outcome))
                except EpisodeFailure as exc:
                    saved.update(status="failed", error=str(exc))
                except Exception as exc:
                    stop_event(assignment["id"], "controller_instrument_error")
                    saved.update(status="instrument_error", error=type(exc).__name__)
            atomic(local / "episodes" / (assignment["id"] + ".json"), saved)
            print(json.dumps(dict(event="accountability_episode_terminal", batch=batch,
                                  id=saved["id"], status=saved["status"])), flush=True)
            return dict(id=saved["id"], status=saved["status"])

        assignments = scheduled(batch)
        first = one(assignments[0])
        serial_passed = first["status"] == "completed"
        if serial_passed and not calls.stop.is_set():
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                rest = list(pool.map(one, assignments[1:]))
        else:
            rest = [one(a) for a in assignments[1:]]
        verify_prior_allowed(ledger_root, manifest["protocol"]["prior_ledger_entries"])
        terminal = dict(protocol=protocol, batch=batch, episodes=[first, *rest],
                        serial_episode_passed=serial_passed, global_safety_stop=calls.stop.is_set(),
                        physical_calls=len(list((local / "calls").glob("*.json"))),
                        logical_actions=len(list((local / "logicals").glob("*.json"))),
                        recoveries=calls.recoveries, budget=ledger.snapshot(), ended_unix=clock())
        atomic(local / "sessions/terminal.json", terminal)
        return terminal


@cache
def auditor():
    path = ROOT / "analysis/paper3_retrospective_recovery_discovery_v2_audit.py"
    spec = importlib.util.spec_from_file_location("_keyed_discovery_audit", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def audit(root, ledger_root=BUDGET):
    return auditor().audit(root, ledger_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("prepare", "run", "audit", "export", "replay"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--batch", type=int, choices=(0, 1))
    parser.add_argument("--expected-protocol")
    parser.add_argument("--target", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--qualification-sha")
    args = parser.parse_args()
    if args.prepare:
        result = dict(protocol=prepare(args.root, qualification_sha=args.qualification_sha))
    else:
        require(args.expected_protocol, "expected protocol required")
        if args.replay:
            result = auditor().replay(args.root, args.expected_protocol)
        else:
            require(verify(args.root)[1] == args.expected_protocol, "unexpected protocol")
            if args.run:
                require(args.batch is not None, "explicit batch required")
                result = execute(args.root, args.batch, secret=t.read_key())
            elif args.audit:
                result = audit(args.root)
            else:
                require(args.target and args.archive, "archive paths required")
                result = auditor().export(args.root, BUDGET, args.target, args.archive, t.read_key())
    print(json.dumps(jsonable(result), indent=2))


if __name__ == "__main__":
    main()


