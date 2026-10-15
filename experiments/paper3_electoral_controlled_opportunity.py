"""Frozen-capable focal-consent diagnostic with exogenous matched coalitions.

This is a separate selected-case discovery experiment, not a repair of the
terminal endogenous-election pilot. No hosted call is permitted before a
source/seed/budget/endpoint freeze. No retries, response repair, replacement,
fallback, local model, or restart of a started run.
"""
# ruff: noqa: E402
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import paper3_electoral_accountability_pilot as base
from paper3 import electoral_controlled_opportunity as design
from paper3 import hosted_reasoning_channel_calls as service
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure

t = base.t
require = t.require
STAGE = "pivot_b_electoral_controlled_opportunity_v1"
CAP = Decimal("0.15")
STOP = Decimal("8")
SEED_BASE = 9300000
WORKERS = 4
MAX_CALLS = 16
BUDGET = base.BUDGET
CONFIG = base.CONFIG
PRIOR_ROOT = ROOT / "results/paper3/pivot_b_electoral_accountability_v1"
PRIOR_EXPORT = ROOT / "results/paper3/pivot_b_electoral_accountability_v1_export"
PRIOR_PROTOCOL = "e3da39ff4936131865f825846bce894aad6402767eb200141e8c79ff88db211a"


def cases():
    rows = []
    indexes = {item["id"]: index for index, item in enumerate(design.inventory())}
    for context in design.cases():
        seed = SEED_BASE + indexes[context["profile_id"]]
        req = base.request(context["messages"], seed)
        reserve = base.reservation(req)
        rows.append(dict(id=context["id"],
                         context={key: value for key, value in context.items()
                                  if key != "messages"} | {"seed": seed},
                         request=req, request_text=reserve["wire"],
                         request_sha256=t.sha(reserve["wire"].encode()),
                         input_token_bound=reserve["input_token_bound"],
                         reserved_usd=reserve["reserved_usd"]))
    require(len(rows) == MAX_CALLS and len({row["id"] for row in rows}) == MAX_CALLS,
            "controlled case inventory")
    return rows


def preflight():
    rows = cases()
    total = sum(Decimal(row["reserved_usd"]) for row in rows)
    require(total <= CAP, "full-case reservation exceeds stage cap")
    return dict(intended_calls=MAX_CALLS, full_case_reservation_usd=str(total),
                max_input_bound=max(row["input_token_bound"] for row in rows),
                cap_usd=str(CAP))


def seed_audit(root=ROOT):
    planned = {SEED_BASE + index for index in range(4)}
    observed, inventory = set(), []

    def walk(value, key=""):
        if isinstance(value, dict):
            for name, child in value.items():
                walk(child, name)
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif type(value) is int and "seed" in key.lower():
            observed.add(value)

    for base_dir, dirs, files in os.walk(Path(root) / "results/paper3"):
        dirs[:] = [name for name in dirs if not any(fragment in name for fragment in
                   ("portable", "bundle", "export", "replay", "__pycache__", "code"))]
        for name in files:
            path = Path(base_dir) / name
            if name != "manifest.json" and not (path.parent.name == "calls" and
                                                 name.endswith(".json")):
                continue
            value = t.load(path)
            walk(value.get("request", value) if path.parent.name == "calls" else value)
            inventory.append((str(path.relative_to(root)), t.sha(path.read_bytes())))
    require(not planned & observed, "historical request seed overlap")
    return dict(planned_unique=sorted(planned), overlap=[],
                historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()))


def prior_done():
    require((PRIOR_ROOT / "sessions/terminal.json").is_file() and
            (PRIOR_EXPORT / "bundle.json").is_file() and
            (PRIOR_EXPORT / "expected_report.json").is_file(),
            "prior election run not terminal and archived")
    helper = base.archive_source.archive_helpers()
    require(helper.verify_bundle(PRIOR_EXPORT, PRIOR_PROTOCOL)["experiment_family"] ==
            base.STAGE, "prior election archive changed")
    report = t.load(PRIOR_EXPORT / "expected_report.json")
    require(report["protocol"] == PRIOR_PROTOCOL and
            report["discovery_screen"]["pathway"] ==
            "coalition_opportunity_not_matched" and
            t.load(PRIOR_ROOT / "sessions/terminal.json")["protocol"] ==
            PRIOR_PROTOCOL, "prior election result identity")
    require(base.verify(PRIOR_ROOT)[1] == PRIOR_PROTOCOL,
            "prior election frozen files changed")
    return dict(protocol=PRIOR_PROTOCOL,
                report_sha256=t.sha(t.canonical(report).encode()))


def specification():
    return dict(name=STAGE, cases=cases(), workers=WORKERS,
                max_calls=MAX_CALLS, cap_usd=str(CAP),
                conservative_budget_stop_usd=str(STOP),
                model_configuration=CONFIG, seed_base=SEED_BASE,
                preflight=preflight(),
                conditional_payoff_opportunity=design.opportunity_audit(),
                prior_protocol=PRIOR_PROTOCOL,
                design="Four fresh selected profiles x binding/promise x requested/executed record. Only the last representative is queried; the same three exogenously fixed early signers appear in all four arms of each profile. Binding arms query focal consent. Promise arms query a requested ballot after a fixed four-signature nonbinding pledge, because nonbinding consent is payoff-irrelevant. No synthetic election is executed in this diagnostic.",
                discovery_rule="A selected-case lead requires all 16 usable actions; in BOTH conflict profiles focal binding consent yes under requested visibility and no under executed visibility; the meaningful nonbinding requested-vote controls are no under both labels for each conflict and yes under both labels for aligned and zero-office profiles. Aligned and zero-office binding consent is recorded but not constrained because it can be payoff-indifferent. No post hoc case selection. Anything else is not a lead.",
                failure_rule="Four independent workers, no retries, repairs, replacements, fallback or restart. Two transport/accounting failures or any identity/source/credential/budget/instrument breach stop admissions; preserve all 16 assignments and missingness bounds.",
                limitations="An exogenous matched signature vector estimates a conditional focal consent response, not endogenous seven-agent coalition behavior. These four purpose-built profiles, a deterministic artificial voter rule, one model/provider and a single seed per profile cannot establish a paper finding. A positive lead needs untouched full-institution games and another model.")


def prepare(root, metadata=None, ledger_root=BUDGET):
    root = Path(root)
    require(not root.exists(), "fresh controlled-opportunity directory required")
    prior = prior_done()
    inherited = base.prerequisite()
    seeds = seed_audit()
    if metadata is None:
        with t.opener().open(base.gate.channel.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    base.check_endpoint(metadata)
    budget = Ledger(ledger_root).snapshot()
    require(budget["pending"] == 0 and
            Decimal(budget["accounted_usd"]) + CAP < STOP,
            "pre-stage conservative $8 stop")
    paths = closure(ROOT, [Path(__file__),
                           ROOT / "analysis/paper3_contracts_archive.py",
                           ROOT / "tests/test_paper3_electoral_controlled_opportunity.py",
                           BUDGET / "authority.json"])
    snapshot = {str(path.relative_to(ROOT)): path.read_text() for path in paths}
    protocol = dict(**specification(), prior_terminal_archive=prior,
                    inherited_prerequisite=inherited, seed_audit=seeds,
                    pre_stage_budget=budget, endpoint_metadata=metadata,
                    metadata_observed_unix=time.time())
    manifest = dict(protocol=protocol,
                    sources={name: t.sha(value.encode())
                             for name, value in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    for name in ("calls", "sessions"):
        (root / name).mkdir()
    atomic(root / "sources.json", snapshot)
    atomic(root / "manifest.json", manifest)
    return t.sha(t.canonical(manifest).encode())


def verify(root, code_root=ROOT):
    root = Path(root)
    manifest, snapshot = t.load(root / "manifest.json"), t.load(root / "sources.json")
    require(set(snapshot) == set(manifest["sources"]), "source inventory")
    for relative, expected in manifest["sources"].items():
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts,
                "unsafe frozen source")
        require(t.sha((Path(code_root) / path).read_bytes()) ==
                t.sha(snapshot[relative].encode()) == expected,
                "frozen controlled source changed: " + relative)
    require(all(manifest["protocol"].get(key) == value
                for key, value in specification().items()),
            "controlled specification changed")
    require(manifest["protocol"]["prior_terminal_archive"]["protocol"] ==
            PRIOR_PROTOCOL and
            manifest["protocol"]["inherited_prerequisite"]["native_template"] ==
            base.request([], 0) and
            manifest["protocol"]["seed_audit"]["planned_unique"] ==
            [SEED_BASE + index for index in range(4)] and
            not manifest["protocol"]["seed_audit"]["overlap"],
            "prerequisite or seed inventory changed")
    base.check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, ledger_root=BUDGET, secret=None, send=None, lookup=None,
            clock=time.time, sleep=time.sleep):
    root = Path(root)
    manifest, protocol = verify(root)
    require(prior_done() == manifest["protocol"]["prior_terminal_archive"] and
            base.prerequisite() == manifest["protocol"]["inherited_prerequisite"],
            "prerequisite changed")
    require(0 <= clock() - manifest["protocol"]["metadata_observed_unix"] <= 3600,
            "stale endpoint metadata")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not list((root / "sessions").iterdir()) and
                not list((root / "calls").iterdir()),
                "already started; no restart")
        ledger = Ledger(ledger_root)
        require(ledger.snapshot() == manifest["protocol"]["pre_stage_budget"],
                "shared budget changed since freeze")
        ledger.allocate(STAGE, CAP)
        atomic(root / "sessions/start.json", dict(protocol=protocol,
                                                  pid=os.getpid(),
                                                  started_unix=clock()))
        calls = service.Calls(root, ledger_root, STAGE, MAX_CALLS,
                              lambda: verify(root), base.score, CONFIG, secret,
                              send, lookup, clock, sleep)
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(calls.one, manifest["protocol"]["cases"]))
        terminal = dict(protocol=protocol, results=results,
                        global_safety_stop=calls.stop.is_set(),
                        transport_failures=calls.transport_failures,
                        budget=ledger.snapshot(), ended_unix=clock())
        atomic(root / "sessions/terminal.json", terminal)
        return terminal


def audit(root, ledger_root=BUDGET):
    root = Path(root)
    manifest, protocol = verify(root)
    terminal = t.load(root / "sessions/terminal.json")
    require(t.load(root / "sessions/start.json")["protocol"] ==
            terminal["protocol"] == protocol, "terminal protocol")
    assigned = manifest["protocol"]["cases"]
    calls, cost = service.audit_records(root, ledger_root, STAGE, protocol,
                                        assigned, terminal, base.score, CONFIG)
    require(cost <= CAP and
            Decimal(manifest["protocol"]["pre_stage_budget"]["accounted_usd"]) +
            cost < STOP, "stage/budget cap exceeded")
    actions = {case["id"]: (row["result"]["action"][
                               "consent" if case["context"]["stage"] == "consent"
                               else "vote"]
                            if row["status"] == "recorded" and
                            row["result"]["usable"] and
                            row["result"]["valid_action"] else None)
               for case, row in zip(assigned, calls, strict=True)}
    screen = design.screen(actions)
    scored = sum(type(value) is bool for value in actions.values())
    return dict(protocol=protocol, assignments=calls, actions=actions,
                scored_actions=scored, all_16_usable=(scored == MAX_CALLS and
                not terminal["global_safety_stop"]), discovery_screen=screen,
                accounted_usd=str(cost),
                global_safety_stop=terminal["global_safety_stop"],
                caveat=specification()["limitations"])


def export(root, ledger_root, target, destination, secret=None):
    helper = base.archive_source.archive_helpers()
    root, ledger_root, target = map(lambda path: Path(path).resolve(),
                                    (root, ledger_root, target))
    require((root / "sessions/terminal.json").is_file(), "not terminal")
    require(not target.exists() and not Path(destination).exists(),
            "archive destination exists")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with Ledger(ledger_root).locked():
            report = audit(root, ledger_root)
            _, protocol = verify(root)
            contents = {"code/" + relative: value.encode()
                        for relative, value in t.load(root / "sources.json").items()}
            for prefix, directory in (("run", root), ("ledger", ledger_root)):
                for path in directory.rglob("*"):
                    require(not path.is_symlink(), "symlink in archive source")
                    if path.is_file() and path.suffix == ".json":
                        contents[prefix + "/" +
                                 str(path.relative_to(directory))] = path.read_bytes()
            contents["expected_report.json"] = (
                json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = (
        "# Controlled early-coalition focal-consent diagnostic\n\n"
        "All 16 assigned one-agent cases, failures and accounting are retained. "
        "This is not a full election. From fresh extraction run `python3 -I -S "
        "code/experiments/paper3_electoral_controlled_opportunity.py . --replay "
        "--expected-protocol " + protocol + "`.\n").encode()
    for relative, data in contents.items():
        helper.safe(target, relative)
        helper.credentials(data, secret)
    metadata = dict(format=helper.FORMAT, experiment_family=STAGE,
                    protocol=protocol,
                    files={name: t.sha(data) for name, data in sorted(contents.items())})
    target.mkdir(parents=True, exist_ok=False)
    for relative, data in contents.items():
        path = helper.safe(target, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    with (target / "bundle.json").open("x") as stream:
        json.dump(metadata, stream, sort_keys=True, indent=2)
    return dict(protocol=protocol, files=len(contents),
                sha256=helper.archive(target, destination))


def replay(root, expected_protocol):
    helper = base.archive_source.archive_helpers()
    root = Path(root).resolve()
    metadata = helper.verify_bundle(root, expected_protocol)
    require(metadata["experiment_family"] == STAGE, "wrong archive family")
    require(ROOT == root / "code", "isolated replay requires bundled code")
    sys.addaudithook(helper.offline_guard)
    require(verify(root / "run")[1] == expected_protocol,
            "frozen controlled protocol changed")
    report = audit(root / "run", root / "ledger")
    require(report == t.load(root / "expected_report.json"),
            "archived report differs")
    return dict(**report, portable_replay=dict(protocol=expected_protocol,
                                              exact_report_match=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    for name in ("prepare", "run", "audit", "export", "replay"):
        mode.add_argument("--" + name, action="store_true")
    parser.add_argument("--expected-protocol")
    parser.add_argument("--target", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.prepare:
        print(prepare(args.root))
        return
    require(args.expected_protocol, "expected protocol required")
    if args.replay:
        print(json.dumps(replay(args.root, args.expected_protocol), indent=2))
        return
    require(verify(args.root)[1] == args.expected_protocol,
            "unexpected protocol")
    if args.export:
        require(args.target and args.archive, "archive paths required")
        value = export(args.root, BUDGET, args.target, args.archive, t.read_key())
    else:
        value = audit(args.root) if args.audit else execute(args.root,
                                                            secret=t.read_key())
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
