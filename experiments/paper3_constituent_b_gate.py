"""Constituent-mandate B gate runner, approved for a fresh 12-call/$0.15 allocation.

This gate is distinct from every failed historical gate and cannot inherit its
approval or pass status. Freeze before use and never restart an admitted run.
"""
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

from experiments import paper3_transport_diagnostic as t
from paper3 import constituent_b_gate as gate
from paper3 import constituent_b_requests as requests
from paper3 import hosted_reasoning_calls as service
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure


require = t.require
STAGE = "pivot_b_constituent_gate_v1"
CAP = requests.GATE_CAP
WORKERS = 1
BUDGET = ROOT / "results/paper3/pivot_b_budget"
METADATA_URL = "https://openrouter.ai/api/v1/models/deepseek/deepseek-v3.2/endpoints"
CONFIG = dict(models=[requests.MODEL, requests.MODEL + "-20251201"],
              provider=requests.PROVIDER_NAME,
              output_bound=requests.OUTPUT_BILLABLE_BOUND)


def check_endpoint(metadata):
    require(metadata["data"]["id"] == requests.MODEL, "wrong metadata model")
    matches = [endpoint for endpoint in metadata["data"]["endpoints"]
               if endpoint.get("tag") == requests.PROVIDER_TAG]
    require(len(matches) == 1, "endpoint absent or ambiguous")
    endpoint = matches[0]
    require(endpoint["provider_name"] == CONFIG["provider"] and
            endpoint["model_id"] == requests.MODEL and
            endpoint["quantization"] == "fp4" and endpoint["status"] == 0,
            "provider identity or status changed")
    require(endpoint["max_completion_tokens"] >= requests.OUTPUT_CAP and
            endpoint["context_length"] >= requests.INPUT_BOUND + requests.OUTPUT_BILLABLE_BOUND,
            "capacity insufficient")
    required = {"reasoning", "max_tokens", "temperature", "top_p", "top_k",
                "min_p", "seed", "presence_penalty", "repetition_penalty",
                "response_format", "structured_outputs"}
    require(required <= set(endpoint["supported_parameters"]), "required parameter unsupported")
    for key, ceiling in (("prompt", requests.PRICE_INPUT_PER_M),
                         ("completion", requests.PRICE_OUTPUT_PER_M)):
        observed = Decimal(endpoint["pricing"][key]) * 1000000
        require(observed.is_finite() and 0 <= observed <= ceiling, "price ceiling exceeded")
    return endpoint


def cases():
    contexts = gate.cases()
    prepared = requests.gate_requests()
    result = []
    for context, row in zip(contexts, prepared, strict=True):
        require(context["name"] == row["name"], "gate context mismatch")
        result.append(dict(id=row["name"], context=context, request=row["request"],
                           request_text=row["wire"],
                           request_sha256=t.sha(row["wire"].encode()),
                           input_token_bound=row["input_token_bound"],
                           reserved_usd=row["reserved_usd"]))
    require(len(result) == 12 and
            sum(Decimal(row["reserved_usd"]) for row in result) <= CAP,
            "gate inventory exceeds cap")
    return result


def score(row, case):
    report = dict(usable=False, valid_action=False, exact=False,
                  native_reasoning=None, reply=None, failure=None)
    if row.get("instrument_error") or "assessment" not in row:
        report["failure"] = "instrument_or_unfinished"
        return report
    assessment = service.assess(row, CONFIG)
    summary = assessment["stream"]
    native = service.native_evidence(summary)
    usable = (assessment["passed"] and summary["finish_reasons"] == ["stop"]
              and native["present"] and
              row["request"].get("reasoning") == dict(enabled=True, exclude=False))
    report.update(usable=usable, native_reasoning=native)
    if not usable:
        report["failure"] = "transport_reasoning_or_completion"
        return report
    content = gate.score(row["final_content"], case["context"])
    report.update(valid_action=content["status"] == "completed", exact=content["exact"],
                  reply=content.get("reply"), failure=content.get("error"))
    return report


def seed_audit(root=ROOT):
    planned_gate = {requests.GATE_SEED_BASE + i for i in range(12)}
    planned_discovery = {case["seed_base"] + i
                         for case in requests.discovery_assignments() for i in range(30)}
    require(not planned_gate & planned_discovery, "gate/discovery seed collision")
    observed, inventory = set(), []

    def walk(value, key=""):
        if isinstance(value, dict):
            for field, child in value.items():
                walk(child, field)
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif type(value) is int and "seed" in key.lower():
            observed.add(value)

    for base, dirs, files in os.walk(Path(root) / "results/paper3"):
        dirs[:] = [d for d in dirs if not any(fragment in d for fragment in
                   ("portable", "bundle", "export", "__pycache__", "code"))]
        for name in files:
            path = Path(base) / name
            if name == "manifest.json" or (path.parent.name == "calls" and name.endswith(".json")):
                value = t.load(path)
                walk(value.get("request", value) if path.parent.name == "calls" else value)
                inventory.append((str(path.relative_to(root)), t.sha(path.read_bytes())))
    overlap = (planned_gate | planned_discovery) & observed
    require(not overlap, "historical seed overlap")
    return dict(gate=sorted(planned_gate), discovery_unique=sorted(planned_discovery),
                overlap=[], historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()))


def specification():
    return dict(name=STAGE, cases=cases(), workers=WORKERS, max_calls=12,
                cap_usd=str(CAP), budget_cap_usd="10.00",
                model_configuration=CONFIG,
                proposed_conditional_discovery_cap_usd=str(requests.DISCOVERY_CAP),
                discovery_frame_seed=requests.DISCOVERY_FRAME_SEED,
                discovery_assignments=requests.discovery_assignments(),
                discovery_preflight=requests.scripted_discovery_preflight(),
                inference_retries=0, receipt_offsets_seconds=[0, 20, 40, 60],
                failure_rule="One worker; any unusable, invalid, or factually wrong case stops new admissions. No retry, replacement, fallback, or rescoring. Preserve all twelve assignments and charges/reservations.",
                gate="All twelve cases exact/valid with pinned provider, native reasoning, complete certified billing and no safety stop. Pass is engineering integrity only.",
                limitations="Four engineered archetypes with two exchange opportunities; a future pilot is discovery, not population or paper evidence.")


def prepare(root, *, metadata=None, ledger_root=BUDGET):
    root = Path(root)
    require(not root.exists(), "fresh run directory required")
    seeds = seed_audit()
    if metadata is None:
        with t.opener().open(METADATA_URL, timeout=20) as response:
            metadata = json.load(response)
    check_endpoint(metadata)
    budget = Ledger(ledger_root).snapshot()
    require(budget["pending"] == 0 and
            Decimal(budget["accounted_usd"]) + CAP <= Decimal("10"),
            "conservative budget admission")
    paths = closure(ROOT, [Path(__file__), ROOT / "analysis/paper3_contracts_archive.py",
                           ROOT / "tests/test_paper3_constituent_b_gate_runner.py",
                           Path(ledger_root) / "authority.json"])
    snapshot = {str(path.relative_to(ROOT)): path.read_text() for path in paths}
    protocol = dict(**specification(), seed_audit=seeds, pre_stage_budget=budget,
                    endpoint_metadata=metadata, metadata_observed_unix=time.time())
    manifest = dict(protocol=protocol,
                    sources={path: t.sha(value.encode()) for path, value in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    for name in ("calls", "sessions"):
        (root / name).mkdir()
    atomic(root / "sources.json", snapshot)
    atomic(root / "manifest.json", manifest)
    return t.sha(t.canonical(manifest).encode())


def verify(root, code_root=ROOT):
    root = Path(root)
    manifest, snapshot = t.load(root / "manifest.json"), t.load(root / "sources.json")
    require(set(snapshot) == set(manifest["sources"]), "source inventory changed")
    for relative, expected in manifest["sources"].items():
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts, "unsafe source path")
        data = (Path(code_root) / path).read_bytes()
        require(t.sha(data) == t.sha(snapshot[relative].encode()) == expected,
                "frozen source changed: " + relative)
    require(all(manifest["protocol"].get(key) == value
                for key, value in specification().items()), "protocol specification changed")
    require(manifest["protocol"]["seed_audit"]["gate"] == list(range(
            requests.GATE_SEED_BASE, requests.GATE_SEED_BASE + 12)) and
            not manifest["protocol"]["seed_audit"]["overlap"], "seed audit changed")
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
        require(not list((root / "sessions").iterdir()) and
                not list((root / "calls").iterdir()), "already started; no restart")
        ledger = Ledger(ledger_root)
        require(ledger.snapshot() == manifest["protocol"]["pre_stage_budget"],
                "pre-stage accounting changed")
        ledger.allocate(STAGE, CAP)
        atomic(root / "sessions/start.json", dict(protocol=protocol, pid=os.getpid(),
                                                  started_unix=clock()))
        calls = service.Calls(root, ledger_root, STAGE, 12, lambda: verify(root),
                              score, CONFIG, secret, send, lookup, clock, sleep)

        def one(case):
            status = calls.one(case)
            if status["status"] == "recorded":
                result = t.load(root / "calls" / (case["id"] + ".json"))["result"]
                if not (result["usable"] and result["valid_action"] and result["exact"]):
                    calls.stop.set()
            return status

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(one, manifest["protocol"]["cases"]))
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
            terminal["protocol"] == protocol, "terminal protocol mismatch")
    reports, cost = service.audit_records(root, ledger_root, STAGE, protocol,
                                          manifest["protocol"]["cases"], terminal,
                                          score, CONFIG)
    require(cost <= CAP, "gate stage cap exceeded")
    prior = Decimal(manifest["protocol"]["pre_stage_budget"]["accounted_usd"])
    require(prior + cost <= Decimal("10"), "fresh B cap exceeded")
    completed = [row for row in reports if row["status"] == "recorded"]
    passed = (len(completed) == 12 and all(row["result"]["usable"] and
              row["result"]["valid_action"] and row["result"]["exact"]
              for row in completed) and not terminal["global_safety_stop"])
    return dict(protocol=protocol, assignments=reports, gate_passed=passed,
                calls=len(list((root / "calls").glob("*.json"))),
                accounted_usd=str(cost), global_safety_stop=terminal["global_safety_stop"],
                caveat=specification()["limitations"])


def archive_helpers():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "constituent_b_archive", ROOT / "analysis/paper3_contracts_archive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def export(root, ledger_root, target, destination, secret=None):
    helper = archive_helpers()
    root, ledger_root, target = map(lambda path: Path(path).resolve(),
                                    (root, ledger_root, target))
    require((root / "sessions/terminal.json").is_file(), "not terminal")
    require(not target.exists() and not Path(destination).exists(),
            "archive destination exists")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with Ledger(ledger_root).locked():
            report = audit(root, ledger_root)
            manifest, protocol = verify(root)
            contents = {"code/" + relative: value.encode()
                        for relative, value in t.load(root / "sources.json").items()}
            for prefix, directory in (("run", root), ("ledger", ledger_root)):
                for path in directory.rglob("*"):
                    require(not path.is_symlink(), "symlink in archive source")
                    if path.is_file() and path.suffix == ".json":
                        contents[prefix + "/" + str(path.relative_to(directory))] = path.read_bytes()
            contents["expected_report.json"] = (
                json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = (
        "# Paper 3 constituent-mandate B gate\n\n"
        "Twelve prespecified factual/action checks; all failures, source and budget records retained. "
        "A pass checks interface integrity, not strategic behavior or a paper result.\n\n"
        "From a fresh extracted directory, run: `python3 -I -S "
        "code/experiments/paper3_constituent_b_gate.py . --replay --expected-protocol "
        + protocol + "`\n").encode()
    for relative, data in contents.items():
        helper.safe(target, relative)
        helper.credentials(data, secret)
    metadata = dict(format=helper.FORMAT, experiment_family=STAGE, protocol=protocol,
                    files={path: t.sha(data) for path, data in sorted(contents.items())})
    target.mkdir(parents=True, exist_ok=False)
    for relative, data in contents.items():
        path = helper.safe(target, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    with (target / "bundle.json").open("x") as stream:
        json.dump(metadata, stream, sort_keys=True, indent=2)
    return dict(protocol=protocol, files=len(contents), sha256=helper.archive(target, destination))


def replay(root, expected_protocol):
    helper = archive_helpers()
    root = Path(root).resolve()
    metadata = helper.verify_bundle(root, expected_protocol)
    require(metadata["experiment_family"] == STAGE, "wrong archive family")
    require(ROOT == root / "code", "replay needs bundled source under isolated Python")
    sys.addaudithook(helper.offline_guard)
    require(verify(root / "run")[1] == expected_protocol, "frozen protocol changed")
    report = audit(root / "run", root / "ledger")
    require(report == t.load(root / "expected_report.json"), "archived report differs")
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
    require(args.expected_protocol, "explicit expected protocol required")
    if args.replay:
        print(json.dumps(replay(args.root, args.expected_protocol), indent=2))
        return
    require(verify(args.root)[1] == args.expected_protocol, "unexpected protocol")
    if args.export:
        require(args.target and args.archive, "archive paths required")
        value = export(args.root, BUDGET, args.target, args.archive, t.read_key())
    else:
        value = audit(args.root) if args.audit else execute(args.root, secret=t.read_key())
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
