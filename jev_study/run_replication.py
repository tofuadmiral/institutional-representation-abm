"""Frozen, sequential Jev pilot. Dry-run by default; never logs credentials."""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import PilotStore
from jev_study.bill_choice import request_for, score
from jev_study.replication import make_replication, SPEC

MODEL = "jev-1.13.0"
RATE = 0.042 / 1_000_000
MAX_REQUEST_COST = 64000 * RATE  # Published maximum input length, not a token estimate.


def wire_request(case):
    # Sorting JSON keys would destroy the option-order intervention.
    return json.dumps(request_for(case, MODEL), ensure_ascii=True, separators=(",", ":"))


def read_key(path, allow_single_line=False):
    content = path.read_text().strip()
    match = re.search(r'''(?im)^\s*["'«»“”]?type?safe_(?:api|ai)_key["'«»“”]?\s*[:=]\s*["'«»“”]?([^\s"'«»“”,}]+)''', content)
    if match:
        return match.group(1)
    if allow_single_line and len(content.splitlines()) == 1 and not any(c.isspace() for c in content):
        return content
    raise ValueError("Named key not found; raw single-line credentials require explicit confirmation")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-usd", type=float)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--allow-single-line-key", action="store_true")
    args = parser.parse_args()
    cases = make_replication()
    protocol = dict(name="jev-constituent-bill-choice-pilot-v1", model=MODEL, cases=cases,
        wire_requests=[wire_request(c) for c in cases], max_calls=len(cases),
        primary="mandate fidelity and paired policy-choice changes; cluster by 24 base profiles",
        secondary="Brier, log loss, selected-option probability, stipulated priority loss; confidence separate",
        gates="complete fixed pilot; no automatic expansion, tuning, calibration fitting or publication claim",
        failure_policy="no automatic retries; interrupted in-flight request stops resume for manual reconciliation",
        price=dict(usd_per_input_token=RATE, per_call_reservation=MAX_REQUEST_COST,
                   source="https://docs.typesafe.ai/models", checked="2026-09-18"),
        limitations="synthetic explicit mandates; no inference about real voter behavior; small dependent pilot")
    protocol.update(SPEC)
    # A saved JSON manifest turns tuples into lists; compare JSON-native values
    # so an unchanged dry-run can be resumed without a false protocol mismatch.
    protocol = json.loads(json.dumps(protocol))
    sources = [ROOT / "jev_study/replication.py", Path(__file__), ROOT / "jev_study/bill_choice.py", ROOT / "paper3/audit_runtime.py"]
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as f:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, f, indent=2)
    print("FROZEN", store.protocol_hash, "calls", len(cases),
          "published-price maximum reservation USD", round(len(cases) * MAX_REQUEST_COST, 6), flush=True)
    if not args.execute:
        return
    if args.max_usd is None or args.max_usd <= 0 or args.key_file is None:
        raise ValueError("Live calls require authorized budget and key-file path")
    key = read_key(args.key_file, args.allow_single_line_key)
    budget_root = ROOT / "results/jev"
    budget_root.mkdir(parents=True, exist_ok=True)
    budget_lock = (budget_root / "study_budget.lock").open("a")
    fcntl.flock(budget_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    authorized_limit = min(args.max_usd, 20.0)
    attempts = args.output / "attempts"
    attempts.mkdir(exist_ok=True)
    for case, wire in zip(cases, protocol["wire_requests"]):
        name = case["name"]
        if (store.root / "sessions" / (name + ".json")).exists():
            continue
        call_path = store.root / "calls" / (name + ".json")
        attempt_path = attempts / (name + ".json")
        if not call_path.exists():
            if attempt_path.exists():
                raise RuntimeError("Unresolved prior request; no automatic resend")
            if (len(list(budget_root.glob("**/attempts/*.json"))) + 1) * MAX_REQUEST_COST > authorized_limit:
                print("STOP: conservative study budget reached", flush=True)
                return
            store.save("attempts", name, dict(started_unix=time.time(), protocol_hash=store.protocol_hash))
            started = time.time()
            request = urllib.request.Request("https://api.typesafe.ai/v1/systemone", data=wire.encode(),
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    raw = response.read().decode("utf-8")
                if key in raw:
                    raise RuntimeError("Unexpected credential in response; not recorded")
                record = dict(wire_request=wire, response_text=raw, elapsed_seconds=time.time()-started,
                              protocol_hash=store.protocol_hash)
            except (urllib.error.URLError, TimeoutError) as exc:
                record = dict(wire_request=wire, transport_error=type(exc).__name__,
                    http_status=getattr(exc, "code", None), elapsed_seconds=time.time()-started,
                    protocol_hash=store.protocol_hash)
            store.save("calls", name, record)
        record = json.loads(call_path.read_text())
        result = dict(case=name, call_keys=[name], protocol_hash=store.protocol_hash)
        try:
            if "transport_error" in record:
                raise ValueError("transport failure")
            response = json.loads(record["response_text"])
            if response["model"] != MODEL:
                raise ValueError("unexpected model version")
            result.update(status="completed", metrics=score(case, response), usage=response.get("usage"))
        except (ValueError, KeyError, TypeError) as exc:
            result.update(status="failed", error_type=type(exc).__name__)
        store.save("sessions", name, result)
        print(name, result["status"], result.get("metrics", {}).get("correct"), flush=True)
        if "transport_error" in record:
            print("STOP: resolve transport failure before continuing; no retries", flush=True)
            return


if __name__ == "__main__":
    main()
