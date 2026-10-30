"""UNAPPROVED candidate Paper 3 route-jurisdiction gate runner.

Do not prepare/freeze or run until an explicit new allocation is approved.
Fabricated transport and isolated portable replay have been tested offline;
this source remains unapproved scaffolding, not an executed model gate.
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
from paper3 import hosted_reasoning_channel_calls as service
from paper3 import route_jurisdiction_gate as gate
from paper3 import route_jurisdiction_requests as requests
from paper3.pivot_b_budget import Ledger, atomic
from paper3.source_closure import closure


require = t.require
STAGE = "pivot_b_route_gate_v1"
CAP = requests.GATE_CAP
WORKERS = 2
BUDGET = ROOT / "results/paper3/pivot_b_budget"
METADATA_URL = "https://openrouter.ai/api/v1/models/qwen/qwen3.5-35b-a3b/endpoints"
CONFIG = dict(models=[requests.MODEL, requests.MODEL + "-20260224"],
              provider="Darkbloom", output_bound=requests.OUTPUT_BILLABLE_BOUND)


def check_endpoint(metadata):
    data = metadata["data"]
    require(data["id"] == requests.MODEL, "wrong metadata model")
    matches = [e for e in data["endpoints"] if e.get("tag") == requests.PROVIDER_TAG]
    require(len(matches) == 1, "endpoint absent or ambiguous")
    endpoint = matches[0]
    require(endpoint["provider_name"] == CONFIG["provider"] and
            endpoint["model_id"] == requests.MODEL and
            endpoint["quantization"] == "fp4" and endpoint["status"] == 0,
            "provider identity or status changed")
    require(endpoint["max_completion_tokens"] >= requests.OUTPUT_CAP and
            endpoint["context_length"] >= requests.INPUT_BOUND + requests.OUTPUT_BILLABLE_BOUND,
            "capacity insufficient")
    required = {"reasoning", "max_tokens", "temperature", "top_p", "top_k", "seed",
                "presence_penalty", "repetition_penalty", "response_format", "structured_outputs"}
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
                           request_text=row["wire"], request_sha256=t.sha(row["wire"].encode()),
                           input_token_bound=row["input_token_bound"],
                           reserved_usd=row["reserved_usd"]))
    require(len(result) == 12 and sum(Decimal(x["reserved_usd"]) for x in result) <= CAP,
            "gate request inventory/cap")
    return result


def score(row, case):
    report = dict(usable=False, valid_action=False, exact=False, native_reasoning=None,
                  reply=None, failure=None)
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
    planned = {requests.GATE_SEED_BASE + i for i in range(12)}
    observed = set()
    inventory = []

    def walk(value, key=""):
        if isinstance(value, dict):
            for k, child in value.items():
                walk(child, k)
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif type(value) is int and "seed" in key.lower():
            observed.add(value)

    for base, dirs, files in os.walk(Path(root) / "results/paper3"):
        dirs[:] = [d for d in dirs if not any(x in d for x in
                   ("portable", "bundle", "export", "__pycache__", "code"))]
        for name in files:
            path = Path(base) / name
            if name == "manifest.json" or (path.parent.name == "calls" and name.endswith(".json")):
                value = t.load(path)
                walk(value.get("request", value))
                inventory.append((str(path.relative_to(root)), t.sha(path.read_bytes())))
    require(not planned & observed, "historical seed overlap")
    return dict(planned=sorted(planned), overlap=[], historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()))


def specification():
    return dict(name=STAGE, cases=cases(), workers=WORKERS, max_calls=12,
                cap_usd=str(CAP), budget_cap_usd="10.00", model_configuration=CONFIG,
                reasoning_evidence="Reasoning enabled AND nonempty native reasoning channel, certified matching billing; inconsistent reported counts retained but not summed.",
                inference_retries=0, receipt_offsets_seconds=[0, 20, 40, 60],
                failure_rule="Any unusable, invalid or factually wrong response stops NEW admissions; already admitted requests finish. Two transport/accounting failures or any identity/source/budget breach also stop. No retry, repair, replacement or fallback.",
                gate="All 12 cases must be completed, locally exact, native-reasoning and billing-certified with no global safety stop. This is interface integrity, not institutional evidence.",
                limitations="One simplified route institution and selected interface cases; a pass does not rescue prior failed contract gates, show strategic competence or establish a paper finding.")


def prepare(root):
    root = Path(root)
    require(not root.exists(), "fresh run directory required")
    seeds = seed_audit()
    with t.opener().open(METADATA_URL, timeout=20) as response:
        metadata = json.load(response)
    check_endpoint(metadata)
    budget = Ledger(BUDGET).snapshot()
    require(budget["pending"] == 0 and Decimal(budget["accounted_usd"]) + CAP <= Decimal("10"),
            "conservative budget admission")
    paths = closure(ROOT, [Path(__file__), ROOT / "analysis/paper3_contracts_archive.py",
                           ROOT / "tests/test_paper3_route_gate_runner.py",
                           BUDGET / "authority.json"])
    snapshot = {str(p.relative_to(ROOT)): p.read_text() for p in paths}
    protocol = dict(**specification(), seed_audit=seeds, pre_stage_budget=budget,
                    endpoint_metadata=metadata, metadata_observed_unix=time.time())
    manifest = dict(protocol=protocol, sources={p: t.sha(v.encode()) for p, v in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    for name in ("calls", "sessions"):
        (root / name).mkdir()
    atomic(root / "sources.json", snapshot)
    atomic(root / "manifest.json", manifest)
    return t.sha(t.canonical(manifest).encode())


def verify(root, code_root=ROOT):
    root = Path(root)
    manifest = t.load(root / "manifest.json")
    snapshot = t.load(root / "sources.json")
    require(set(snapshot) == set(manifest["sources"]), "source inventory changed")
    for relative, expected in manifest["sources"].items():
        path = Path(relative)
        require(not path.is_absolute() and ".." not in path.parts, "unsafe source path")
        data = (Path(code_root) / path).read_bytes()
        require(t.sha(data) == t.sha(snapshot[relative].encode()) == expected,
                "frozen source changed: " + relative)
    require(all(manifest["protocol"].get(k) == value for k, value in specification().items()),
            "protocol specification changed")
    require(manifest["protocol"]["seed_audit"]["planned"] ==
            list(range(requests.GATE_SEED_BASE, requests.GATE_SEED_BASE + 12)) and
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
        require(not list((root / "sessions").iterdir()) and not list((root / "calls").iterdir()),
                "already started; no restart")
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
                row = t.load(root / "calls" / (case["id"] + ".json"))
                result = row["result"]
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
    completed = [r for r in reports if r["status"] == "recorded"]
    passed = (len(completed) == 12 and all(r["result"]["usable"] and
              r["result"]["valid_action"] and r["result"]["exact"] for r in completed)
              and not terminal["global_safety_stop"])
    return dict(protocol=protocol, assignments=reports, gate_passed=passed,
                calls=len(list((root / "calls").glob("*.json"))),
                accounted_usd=str(cost), global_safety_stop=terminal["global_safety_stop"],
                caveat=specification()["limitations"])


def archive_helpers():
    import importlib.util
    spec = importlib.util.spec_from_file_location("route_archive", ROOT / "analysis/paper3_contracts_archive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def export(root, ledger_root, target, destination, secret=None):
    helper = archive_helpers()
    root, ledger_root, target = map(lambda p: Path(p).resolve(), (root, ledger_root, target))
    require((root / "sessions/terminal.json").is_file(), "not terminal")
    require(not target.exists() and not Path(destination).exists(), "archive destination exists")
    with (root / "writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with Ledger(ledger_root).locked():
            report = audit(root, ledger_root)
            manifest, protocol = verify(root)
            contents = {"code/" + p: value.encode()
                        for p, value in t.load(root / "sources.json").items()}
            for prefix, directory in (("run", root), ("ledger", ledger_root)):
                for path in directory.rglob("*"):
                    require(not path.is_symlink(), "symlink in archive source")
                    if path.is_file() and path.suffix == ".json":
                        contents[prefix + "/" + str(path.relative_to(directory))] = path.read_bytes()
            contents["expected_report.json"] = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    contents["README.md"] = (
        "# Paper 3 route-jurisdiction interface gate\n\n"
        "Twelve selected rule/action cases; failures, source and budget records retained. "
        "A gate pass checks interface integrity, not strategic behavior or a paper result.\n\n"
        "From a fresh extracted directory, inspect trusted source and run:\n\n"
        "`python3 -I -S code/experiments/paper3_route_gate.py . --replay "
        "--expected-protocol " + protocol + "`\n\n"
        "No API key, network, model weights or original checkout is required. "
        "Hashes and replay prove internal consistency, not provider authenticity.\n").encode()
    for relative, data in contents.items():
        helper.safe(target, relative)
        helper.credentials(data, secret)
    metadata = dict(format=helper.FORMAT, experiment_family=STAGE, protocol=protocol,
                    files={p: t.sha(data) for p, data in sorted(contents.items())})
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
    return dict(**report, portable_replay=dict(protocol=expected_protocol, exact_report_match=True))


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
        value = replay(args.root, args.expected_protocol)
        print(json.dumps(value, indent=2))
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
