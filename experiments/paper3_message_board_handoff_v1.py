"""Prospective fixed public-board cohort: proposal, prepare, run, offline audit.

Proposal is read-only apart from its new output file. Preparation additionally
requires separately pinned human scope and genuine current-source readiness.
Neither mode allocates money or calls a model. Never reuse a completed root.
"""
# ruff: noqa: E402
import argparse
from dataclasses import asdict
from decimal import Decimal
import fcntl
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from paper3 import message_board_handoff_v1 as design
from paper3 import message_board_runtime_v1 as runtime
from paper3 import message_board_budget_v1 as budget
from paper3.retrospective_source_closure import closure
from paper3.pivot_b_budget import atomic
from experiments import paper3_office_sacrifice_probe_v1 as previous

VERSION = "public-board-handoff-cohort-v1"
N = 16
ROOT_NAME = "results/paper3/message_board_handoff_v1"
LEDGER = "results/paper3/pivot_b_budget"
OLD_ROOT = "results/paper3/office_sacrifice_probe_v1"
OLD_MANIFEST = OLD_ROOT + "/manifest.json"
AUTHORITY = "results/paper3/message_board_authorization_2026_11_04.json"
READINESS = "results/paper3/message_board_readiness_2026_11_04.json"
TESTS = ["tests/test_paper3_message_board_handoff_v1.py",
         "tests/test_paper3_message_board_runtime_v1.py",
         "tests/test_paper3_message_board_coordinator_v1.py"]
ENTRY = "experiments/paper3_message_board_handoff_v1.py"
require, load, digest = runtime.require, runtime.load, runtime.file_sha
REFERENCE_PINS = {
    OLD_ROOT + "/report.json": "1116cf5c44e191fb30bc079cb2cd3637723f7bb105e917d14bc9c4edc076e801",
    previous.READINESS: "42336cf417bc7189d87f61feda2b7adf3033ac53d37a2b6bc02169691fe80d09",
    previous.AUTHORITY: "821f6040eaf67885e4e9dcb774be2719dcba3b8e49e4c0646b67d4ae54c14867",
    "results/paper3/office_sacrifice_final_audit_2026_11_04.json": "b04d1fd47165cbce5225181ef1bc20cb11386262b3fce4d3cd4934b831b2148e",
    "results/paper3/office_sacrifice_stage_closeout_2026_11_04.json": "da2caf8495bc112eec919e2b4b89155c2bf5695c7b91acd764d30fb93cf1c624",
    "results/paper3/office_sacrifice_portable_replay_2026_11_04.json": "f2ca2bf27d3999453b9d7ddf5df312afa9fd062f773a5908dcd6921c42d329c8",
    "paper3/data/office_sacrifice_probe_v1_complete.zip": "3f859ac9972190863f80c9369520d0db0b246dd20fc719f0afb3fa96d3ee1afb",
}


def value_sha(value):
    return hashlib.sha256(design.canonical(value).encode()).hexdigest()


def specification():
    selected = design.cases(N)
    bound = design.request_bound(selected)
    return dict(format=VERSION, cases=[asdict(c) for c in selected],
        episode_and_control_order=runtime.schedule(selected),
        case_seed=design.CASE_SEED, request_base=design.REQUEST_BASE,
        order_seed=runtime.ORDER_SEED, conditions=design.CONDITIONS,
        main_system=design.SYSTEM, score_system=design.SCORE_SYSTEM,
        factual_system=design.FACT_SYSTEM,
        tools=[design.POST_TOOL, design.DECISION_TOOL, design.FACT_TOOL],
        decoding="exact requested tool; no text repair or regenerated content",
        controls=[design.control(c, k) for c in selected for k in ("factual", "score")],
        request_bound=bound, window_seconds=86400, freshness_seconds=60,
        maximum_reissues_per_action=3, cooldowns=[300, 600, 1200],
        retry_predicate=runtime.retry.VERSION, billing_predicate=runtime.billing.VERSION,
        primary="peer minus self replacement rate among all assigned better-successor cases, separately by communication",
        secondary="board by identity interaction; quality sensitivity; all utility loss, controls and missingness",
        controls_never_exclude=True, independent_case_units=N,
        better_successor_cases=sum(c.better_successor for c in selected),
        native_route=design.make_request([], design.POST_TOOL, 0),
        automatic_successor=False, intrinsic_motive_identified=False)


def sources():
    old = load(REPO / OLD_MANIFEST)["sources"]
    require(len(old) == 220, "complete old source closure")
    for name, sha in old.items():
        require(digest(REPO / name) == sha, "old frozen source changed: " + name)
    entries = [*old, ENTRY, *TESTS, "analysis/paper3_message_board_offline_v1.py"]
    return {p.relative_to(REPO).as_posix(): digest(p)
            for p in closure(REPO, [REPO / name for name in entries])}


def history():
    return {p.name: digest(p) for p in sorted((REPO / LEDGER / "entries").glob("*.json"))}


def protected_inventory():
    result = dict(load(REPO / previous.PROTECTED)["protected_inventory"])
    def add(name, sha):
        require(name not in result or result[name] == sha, "conflicting historical pins: " + name)
        result[name] = sha
    for name, sha in load(REPO / OLD_MANIFEST)["sources"].items():
        add(name, sha)
    for name, sha in REFERENCE_PINS.items():
        require(digest(REPO / name) == sha, "completed-reference pin changed: " + name)
        add(name, sha)
    # Use the known-good immutable archive inventory rather than blessing the
    # current raw records merely because they exist at preparation time.
    with zipfile.ZipFile(REPO / "paper3/data/office_sacrifice_probe_v1_complete.zip") as archive:
        archived = json.loads(archive.read("bundle.json"))["files"]
    for name, sha in archived.items():
        if name.startswith("repo/" + OLD_ROOT + "/"):
            add(name[5:], sha)
    for name, sha in load(REPO / OLD_ROOT / "report.json")["ledger_hashes"].items():
        add(LEDGER + "/entries/" + name, sha)
    for name, sha in result.items():
        p = REPO / name
        require(not p.is_symlink() and digest(p) == sha, "protected historical artifact changed: " + name)
    return result


def seed_scan():
    seeds = {design.REQUEST_BASE + c.index * 64 + r * 8 + role
             for c in design.cases(N) for r in range(3) for role in range(3)}
    seeds.update(design.control(c, k)["request"]["seed"]
                 for c in design.cases(N) for k in ("factual", "score"))
    count = 0
    for p in (REPO / "results/paper3").glob("**/calls/*.json"):
        require(load(p).get("request", {}).get("seed") not in seeds, "seed overlaps prior physical request")
        count += 1
    return dict(files=count, overlap=0, scope="historical nonarchive raw calls")


def proposal():
    require(not (REPO / ROOT_NAME).exists(), "proposal must precede the new study")
    spec, src, protected = specification(), sources(), protected_inventory()
    book = budget.BoardLedger(REPO / LEDGER)
    snapshot = book.snapshot()
    require(history() == load(REPO / OLD_ROOT / "report.json")["ledger_hashes"],
            "last completed whole-ledger baseline must be unchanged")
    require(Decimal(snapshot["available_for_new_stages_usd"]) >=
            Decimal(spec["request_bound"]["full_bound_usd"]), "whole fixed cohort exceeds headroom")
    return dict(format="PUBLIC_BOARD_PROPOSAL_NOT_AUTHORITY_OR_MODEL_DATA",
        specification=spec, specification_sha256=value_sha(spec), sources=src,
        protected_count=len(protected), protected_sha256=value_sha(protected),
        prior_entries=history(), prior_snapshot=snapshot, seed_scan=seed_scan(),
        new_model_calls=0, allocated=False, prepared=False, paid_launch_authorized=False)


def scope_check(sha, spec):
    require(digest(REPO / AUTHORITY) == sha, "external scope-authority pin")
    a = load(REPO / AUTHORITY)
    require(a["approved"] is True and a["approved_by"] == "Fuad"
            and type(a["direct_user_instructions"]) is list
            and all(type(s) is str and s.strip() for s in a["direct_user_instructions"])
            and a["direct_user_instructions"], "actual direct scope authority required")
    require(a["scope"] == VERSION and a["specification_sha256"] == value_sha(spec)
            and a["total_cumulative_cap_usd"] == "21.31"
            and a["new_allocation_cap_usd"] == spec["request_bound"]["full_bound_usd"]
            and a["maximum_physical_requests"] == spec["request_bound"]["maximum_physical_calls"]
            and a["credit_purchase"] is False and a["new_paid_qualification"] is False
            and a["automatic_successor"] is False and a["historical_runs_modified"] is False,
            "exact new scope without added budget or successor")


def readiness_check(sha, src):
    require(digest(REPO / READINESS) == sha, "external readiness pin")
    r = load(REPO / READINESS)
    require(r["kind"] == "PRIVATE_SOFTWARE_ONLY_NOT_MODEL_OBSERVATIONS"
            and r["sources_before"] == r["sources_after"] == src
            and r["test_files"] == TESTS and r["new_model_calls"] == 0
            and r["actual_ledger_mutations"] == 0
            and r["network_process_denial_selftests"] is True,
            "genuine whole-source current checks")
    require(len(r["checks"]) >= 2 and all(c["returncode"] == 0
            and not c["stderr"].strip() for c in r["checks"])
            and any("passed" in c["stdout"] for c in r["checks"]), "actual successful check records")


def prepare(authority_sha, readiness_sha):
    root = REPO / ROOT_NAME
    require(not root.exists(), "fresh root only; never prepare again")
    spec, src = specification(), sources()
    scope_check(authority_sha, spec)
    readiness_check(readiness_sha, src)
    evidence = proposal()
    require(evidence["sources"] == src and runtime.same(evidence["specification"], spec), "preparation drift")
    m = dict(format=VERSION, sources=src, specification=spec,
        authority=dict(path=AUTHORITY, sha256=authority_sha),
        readiness=dict(path=READINESS, sha256=readiness_sha),
        prior_entries=evidence["prior_entries"], prior_snapshot=evidence["prior_snapshot"],
        protected=protected_inventory(), seed_scan=evidence["seed_scan"])
    root.mkdir()
    atomic(root / "manifest.json", m)
    return dict(protocol=digest(root / "manifest.json"), source_files=len(src),
                logical=spec["request_bound"]["logical_calls"],
                full_bound_usd=spec["request_bound"]["full_bound_usd"],
                model_calls=0, allocated=False)


def verify(protocol, *, full=False):
    root = REPO / ROOT_NAME
    require(not root.is_symlink() and root.resolve().is_relative_to(REPO.resolve()), "same repository root")
    require(digest(root / "manifest.json") == protocol, "external manifest pin")
    m = load(root / "manifest.json")
    require(m["format"] == VERSION and m["authority"]["path"] == AUTHORITY
            and m["readiness"]["path"] == READINESS, "fixed manifest format and authority paths")
    for name, sha in m["sources"].items():
        require(digest(REPO / name) == sha, "source closure changed: " + name)
    require(digest(REPO / AUTHORITY) == m["authority"]["sha256"]
            and digest(REPO / READINESS) == m["readiness"]["sha256"], "scope/readiness changed")
    if full:
        require(sources() == m["sources"] and runtime.same(specification(), m["specification"]),
                "source membership or scientific specification drift")
        scope_check(m["authority"]["sha256"], m["specification"])
        readiness_check(m["readiness"]["sha256"], m["sources"])
        require(protected_inventory() == m["protected"], "historical inventory changed")
        now = history()
        for name, sha in m["prior_entries"].items():
            require(now.get(name) == sha, "prior charge changed")
        stage = "board-" + protocol[:16]
        require(all(name in m["prior_entries"] or load(REPO / LEDGER / "entries" / name)["stage"] == stage
                    for name in now), "unrelated new charges during fixed cohort")
    return m, protocol


def allocate(protocol, m):
    root, stage = REPO / ROOT_NAME, "board-" + protocol[:16]
    path, cap = root / "allocation.json", m["specification"]["request_bound"]["full_bound_usd"]
    book = budget.BoardLedger(REPO / LEDGER)
    if not path.exists():
        group_path = REPO / LEDGER / budget.GROUPS / (stage + ".json")
        if group_path.exists():
            group = load(group_path)
            require(set(group["stages"]) == {stage} and group["cap_usd"] == cap
                    and group["stages"][stage]["prior_entries"] == m["prior_entries"],
                    "exact interrupted allocation recovery")
            pins = {stage: digest(REPO / LEDGER / budget.STAGES / (stage + ".json"))}
        else:
            require(history() == m["prior_entries"], "baseline before one-time allocation")
            pins = book.allocate_group(stage, {stage: cap})["stage_pins"]
        atomic(path, dict(protocol=protocol, stage=stage, stage_pins=pins))
    return allocated_book(protocol, m)


def allocated_book(protocol, m):
    a = load(REPO / ROOT_NAME / "allocation.json")
    stage = "board-" + protocol[:16]
    require(a["protocol"] == protocol and a["stage"] == stage and set(a["stage_pins"]) == {stage},
            "one exact allocated stage")
    book = budget.BoardLedger(REPO / LEDGER, stage_pins=a["stage_pins"])
    with book.locked():
        record = book._stage(stage)
        require(record["cap_usd"] == m["specification"]["request_bound"]["full_bound_usd"]
                and record["prior_entries"] == m["prior_entries"], "stage cap and immutable baseline")
    return book, stage


def run(protocol, *, secret=None, send=None, lookup=None, admit=None, clock=None, sleep=None):
    root = REPO / ROOT_NAME
    with (root / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        m, _ = verify(protocol, full=True)
        require(not (root / "report.json").exists(), "complete root: audit only")
        starts = sorted((root / "invocations").glob("*-start.json"))
        require(not starts or not starts[-1].with_name(starts[-1].name.replace("start", "terminal")).exists(),
                "latest paused terminal requires a decision")
        # Tests inject transport and never read a key. The CLI uses only this
        # fixed pinned provider service, after exact scope/source verification.
        if send is None:
            secret = previous.read_secret(REPO)
        book, stage = allocate(protocol, m)
        deps = dict(secret=secret, send=send or previous.transport.transmit,
                    lookup=lookup or previous.diagnostic.receipt_lookup,
                    admit=admit or previous.bounded_admission)
        if clock is not None:
            deps.update(clock=clock, sleep=sleep)
        return runtime.run(root, REPO, protocol, design.cases(N), book, stage,
                           lambda: verify(protocol), **deps)


def audit(protocol):
    m, _ = verify(protocol, full=True)
    book, stage = allocated_book(protocol, m)
    result = runtime.audit(REPO / ROOT_NAME, REPO, protocol, design.cases(N), book,
                           stage, lambda: verify(protocol))
    verify(protocol, full=True)
    report = load(REPO / ROOT_NAME / "report.json")
    result.update(identity_private=report["identity_private"], identity_board=report["identity_board"],
                  interaction=report["interaction"], controls=report["control_summary"],
                  intrinsic_motive_identified=False)
    return result


def deny_live():
    def guard(event, args):
        if event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn")) or event in (
                "os.system", "os.fork", "os.forkpty", "os.posix_spawn"):
            raise PermissionError("offline coordinator denies network/process access")
    sys.addaudithook(guard)
    for operation in (lambda: socket.socket(),
                      lambda: subprocess.Popen([sys.executable, "-c", "raise SystemExit(99)"])):
        try:
            operation()
        except PermissionError:
            continue
        raise AssertionError("offline denial selftest failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("proposal", "prepare", "run", "audit"):
        modes.add_argument("--" + mode, action="store_true")
    parser.add_argument("--expected-protocol")
    parser.add_argument("--authority-sha256")
    parser.add_argument("--readiness-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.run:
        deny_live()
    if args.proposal:
        require(args.output is not None and not args.output.exists(), "new proposal output only")
        require(args.output.resolve().parent == (REPO / "results/paper3").resolve()
                and args.output.name.startswith("message_board_proposal_")
                and args.output.suffix == ".json", "proposal outside scientific roots")
        value = proposal()
        atomic(args.output, value)
        result = dict(path=str(args.output), sha256=digest(args.output),
            specification_sha256=value["specification_sha256"], source_files=len(value["sources"]),
            protected_count=value["protected_count"], prior_entries=len(value["prior_entries"]),
            bound_usd=value["specification"]["request_bound"]["full_bound_usd"],
            allocated=False, model_calls=0)
    elif args.prepare:
        require(args.authority_sha256 is not None and args.readiness_sha256 is not None
                and args.expected_protocol is None, "externally pinned scope/readiness required")
        result = prepare(args.authority_sha256, args.readiness_sha256)
    else:
        require(args.expected_protocol is not None, "external protocol required")
        result = audit(args.expected_protocol) if args.audit else run(args.expected_protocol)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
