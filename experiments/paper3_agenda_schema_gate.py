"""Prospective strict-JSON action gate for the Qwen sponsorship interface.

Sixteen fresh technical contexts only. This gate does not estimate an
institutional effect, repair the earlier pilot, or authorize a successor.
"""
# ruff: noqa: E402
from __future__ import annotations

import argparse
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

from experiments import paper3_qwen_channel_gate as channel
from experiments import paper3_constituent_b_gptoss_action_gate as archive_source
from paper3 import agenda_schema_interface as interface
from paper3 import agenda_sponsorship_institution as game
from paper3 import hosted_reasoning_channel_calls as service
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure


t = channel.t
require = t.require
STAGE = "pivot_b_agenda_schema_gate_v1"
CAP = Decimal("0.15")
STOP = Decimal("8")
MAX_CALLS = 16
CONFIG = channel.CONFIG
BUDGET = channel.BUDGET
PRIOR_STAGE = "pivot_b_ratification_population_discovery_v1"
PRIOR_PENDING = frozenset((
    PRIOR_STAGE + "-ratification-population-discovery-09-14",
    PRIOR_STAGE + "-ratification-population-discovery-13-01",
    PRIOR_STAGE + "-ratification-population-discovery-11-06",
    PRIOR_STAGE + "-ratification-population-discovery-12-01",
))


def request(messages, seed, stage, compromises):
    result = channel.request_for(messages, seed)
    result["response_format"] = dict(
        type="json_schema",
        json_schema=dict(name=f"paper3_agenda_{stage}", strict=True,
                         schema=interface.schema(stage, compromises)))
    return result


def cases():
    result = []
    for context in interface.contexts():
        req = request(context["messages"], context["seed"],
                      context["stage"], context["compromises"])
        wire = t.canonical(req)
        bound = len(wire.encode()) + 1024
        require(bound + CONFIG["output_bound"] <= channel.CONTEXT,
                "conservative context bound")
        reserve = ((Decimal(bound) * channel.PRICE_IN +
                    Decimal(CONFIG["output_bound"]) * channel.PRICE_OUT) /
                   Decimal(1000000))
        result.append(dict(id=context["id"],
                           context={key: value for key, value in context.items()
                                    if key != "messages"}, request=req,
                           request_text=wire,
                           request_sha256=t.sha(wire.encode()),
                           input_token_bound=bound, reserved_usd=str(reserve)))
    require(len(result) == MAX_CALLS and
            sum(Decimal(row["reserved_usd"]) for row in result) <= CAP,
            "gate inventory or full reservation")
    return result


def score(row, case):
    result = dict(usable=False, valid_action=False, correct=None,
                  native_reasoning=None, action=None, failure=None)
    if row.get("instrument_error") or "assessment" not in row:
        result["failure"] = "instrument_or_unfinished"
        return result
    assessed = service.assess(row, CONFIG)
    stream = assessed["stream"]
    native = service.native_evidence(stream)
    usable = (assessed["passed"] and stream["finish_reasons"] == ["stop"] and
              native["present"] and row["request"].get("reasoning") ==
              dict(enabled=True, exclude=False))
    result.update(usable=usable, native_reasoning=native)
    if not usable:
        result["failure"] = "transport_reasoning_or_completion"
        return result
    try:
        action = game.parse_action(row["final_content"],
                                   case["context"]["stage"],
                                   tuple(case["context"]["compromises"]))
        result.update(valid_action=True, correct=True, action=action)
    except (ValueError, TypeError, KeyError) as exc:
        result["failure"] = type(exc).__name__
    return result


def seed_audit(root=ROOT):
    planned = set(range(interface.SEED_BASE, interface.SEED_BASE + MAX_CALLS))
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

    for base, dirs, files in os.walk(Path(root) / "results/paper3"):
        dirs[:] = [name for name in dirs if not any(fragment in name for fragment in
                   ("portable", "bundle", "export", "replay", "__pycache__", "code"))]
        for name in files:
            path = Path(base) / name
            if name != "manifest.json" and not (path.parent.name == "calls" and
                                                 name.endswith(".json")):
                continue
            value = t.load(path)
            walk(value.get("request", value) if path.parent.name == "calls" else value)
            inventory.append((str(path.relative_to(root)), t.sha(path.read_bytes())))
    require(not planned & observed, "historical request seed overlap")
    return dict(planned=sorted(planned), overlap=[], historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()))


def pending_inventory(ledger_root=BUDGET):
    root = Path(ledger_root)
    require(not list(root.rglob("*.partial")), "interrupted ledger write")
    entries = [t.load(path) for path in (root / "entries").glob("*.json")]
    pending = {row["request_id"] for row in entries
               if row["status"] == "reserved"}
    require(pending <= PRIOR_PENDING and
            all(row["stage"] == PRIOR_STAGE for row in entries
                if row["status"] == "reserved"),
            "unknown pending request outside interrupted predecessor")
    return sorted(pending)


def check_endpoint(metadata):
    endpoint = channel.check_metadata(metadata)
    require("structured_outputs" in endpoint["supported_parameters"],
            "pinned endpoint does not advertise structured outputs")
    require(endpoint.get("uptime_last_30m") is not None and
            endpoint["uptime_last_30m"] >= 99 and
            endpoint.get("uptime_last_5m") is not None and
            endpoint["uptime_last_5m"] >= 95,
            "endpoint uptime below gate threshold")
    return endpoint


def specification():
    return dict(name=STAGE, cases=cases(), workers=1, max_calls=MAX_CALLS,
                cap_usd=str(CAP), budget_stop_usd=str(STOP),
                model_configuration=CONFIG, inference_retries=0,
                gate="All 16 fresh advocacy/sponsor/vote actions must be usable, exactly one-key, native-reasoning, and billing-certified; no content or policy outcome selection.",
                failure_rule="Serial first-failure stop. No retry, coercion, repair, fallback, case replacement or restart; preserve all not-started assignments.",
                scientific_status="Action-format engineering gate only; not evidence of any institutional effect.")


def prepare(root, *, metadata=None, ledger_root=BUDGET):
    root = Path(root)
    require(not root.exists(), "fresh schema-gate directory required")
    seeds = seed_audit()
    pending = pending_inventory(ledger_root)
    if metadata is None:
        with t.opener().open(channel.METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    check_endpoint(metadata)
    budget = Ledger(ledger_root).snapshot()
    require(budget["pending"] == len(pending) and
            Decimal(budget["accounted_usd"]) + CAP < STOP,
            "conservative $8 spending stop")
    paths = closure(ROOT, [Path(__file__),
                           ROOT / "analysis/paper3_contracts_archive.py",
                           ROOT / "tests/test_paper3_agenda_schema_gate.py",
                           BUDGET / "authority.json"])
    snapshot = {str(path.relative_to(ROOT)): path.read_text() for path in paths}
    protocol = dict(**specification(), seed_audit=seeds,
                    pre_stage_budget=budget, prior_pending=pending,
                    endpoint_metadata=metadata,
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
        require(not path.is_absolute() and ".." not in path.parts, "unsafe source")
        require(t.sha((Path(code_root) / path).read_bytes()) ==
                t.sha(snapshot[relative].encode()) == expected,
                "frozen schema-gate source changed: " + relative)
    require(all(manifest["protocol"].get(key) == value
                for key, value in specification().items()),
            "schema-gate specification changed")
    require(manifest["protocol"]["seed_audit"]["planned"] ==
            list(range(interface.SEED_BASE, interface.SEED_BASE + MAX_CALLS)) and
            not manifest["protocol"]["seed_audit"]["overlap"],
            "seed audit")
    check_endpoint(manifest["protocol"]["endpoint_metadata"])
    return manifest, t.sha(t.canonical(manifest).encode())


def execute(root, ledger_root=BUDGET, secret=None, send=None, lookup=None,
            clock=time.time, sleep=time.sleep):
    root = Path(root)
    manifest, protocol = verify(root)
    require(0 <= clock() - manifest["protocol"]["metadata_observed_unix"] <= 3600,
            "stale endpoint metadata")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not list((root / "calls").iterdir()) and
                not list((root / "sessions").iterdir()),
                "already started; no restart")
        ledger = Ledger(ledger_root)
        require(ledger.snapshot() == manifest["protocol"]["pre_stage_budget"] and
                pending_inventory(ledger_root) ==
                manifest["protocol"]["prior_pending"],
                "shared budget changed since freeze")
        ledger.allocate(STAGE, CAP)
        atomic(root / "sessions/start.json", dict(protocol=protocol,
                                                 pid=os.getpid(), started_unix=clock()))
        calls = service.Calls(root, ledger_root, STAGE, MAX_CALLS,
                              lambda: verify(root), score, CONFIG,
                              secret, send, lookup, clock, sleep)
        results = []
        stopped_on_content = False
        for case in manifest["protocol"]["cases"]:
            if calls.stop.is_set() or stopped_on_content:
                results.append(dict(id=case["id"], status="not_started"))
                continue
            outcome = calls.one(case)
            results.append(outcome)
            if outcome["status"] != "recorded":
                stopped_on_content = True
                continue
            saved = t.load(root / "calls" / (case["id"] + ".json"))
            result = saved["result"]
            if not (result["usable"] and result["valid_action"] and
                    result["correct"] is True):
                stopped_on_content = True
        terminal = dict(protocol=protocol, results=results,
                        stopped_on_content=stopped_on_content,
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
    reports, cost = service.audit_records(root, ledger_root, STAGE, protocol,
                                          manifest["protocol"]["cases"], terminal,
                                          score, CONFIG)
    require(cost <= CAP and
            Decimal(manifest["protocol"]["pre_stage_budget"]["accounted_usd"]) +
            cost < STOP, "stage or cumulative stop exceeded")
    first_failure = next((i for i, row in enumerate(reports)
                          if not (row["status"] == "recorded" and
                                  row["result"]["usable"] and
                                  row["result"]["valid_action"] and
                                  row["result"]["correct"] is True)), None)
    if first_failure is not None:
        require(all(row["status"] == "not_started"
                    for row in reports[first_failure + 1:]),
                "later gate case started after failure")
    passed = first_failure is None and not terminal["global_safety_stop"]
    require(terminal["stopped_on_content"] ==
            (first_failure is not None and
             reports[first_failure]["status"] == "recorded") or
            terminal["global_safety_stop"] or passed,
            "gate stopping state")
    return dict(protocol=protocol, assignments=reports,
                calls=len(list((root / "calls").glob("*.json"))),
                valid=sum(row["status"] == "recorded" and
                          row["result"]["usable"] and
                          row["result"]["valid_action"] and
                          row["result"]["correct"] is True for row in reports),
                gate_passed=passed, accounted_usd=str(cost),
                global_safety_stop=terminal["global_safety_stop"],
                caveat="Fresh strict-action format gate only, not an institutional outcome or evidence of strategic reliability.")


def export(root, ledger_root, target, destination, secret=None):
    helper = archive_source.archive_helpers()
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
                        contents[prefix + "/" + str(path.relative_to(directory))] = (
                            path.read_bytes())
            contents["expected_report.json"] = (
                json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = (
        "# Strict sponsorship-action interface gate\n\n"
        "Engineering only; preserve all failed and unstarted cases. "
        "From a fresh extraction run `python3 -I -S "
        "code/experiments/paper3_agenda_schema_gate.py . --replay "
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
    helper = archive_source.archive_helpers()
    root = Path(root).resolve()
    metadata = helper.verify_bundle(root, expected_protocol)
    require(metadata["experiment_family"] == STAGE, "wrong archive family")
    require(ROOT == root / "code", "isolated replay requires bundled code")
    sys.addaudithook(helper.offline_guard)
    require(verify(root / "run")[1] == expected_protocol,
            "frozen gate protocol changed")
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
        result = export(args.root, BUDGET, args.target, args.archive, t.read_key())
    else:
        result = audit(args.root) if args.audit else execute(args.root,
                                                              secret=t.read_key())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
