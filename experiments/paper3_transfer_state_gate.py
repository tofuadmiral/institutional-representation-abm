"""Replay the exact factual-gate requests on a second local model."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import PilotStore, digest
from paper3.commitment_memory import parse
from experiments.paper3_memory_pilot import CompleteResponseBackend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8013/v1")
    args = parser.parse_args()
    cases = []
    for path in sorted((args.source / "sessions").glob("*.json")):
        record = json.loads(path.read_text())
        if len(record["call_keys"]) != 1:
            raise ValueError("expected one request per factual case")
        call = json.loads((args.source / "calls" / (record["call_keys"][0] + ".json")).read_text())
        cases.append(dict(key=path.stem, record=record, request=call["request"]))
    if len(cases) != 18:
        raise ValueError("expected complete 18-case source gate")
    protocol = dict(name="factual-gate-model-transfer-v1", purpose="selected-history cross-model diagnostic, not confirmation",
                    source=str(args.source), source_cases_hash=digest(cases), expected_calls=18,
                    model=args.model, model_revision=args.model_revision,
                    runtime={name: importlib.metadata.version(name) for name in ("mlx", "mlx-lm", "transformers")},
                    server=dict(fix_mistral_regex=True, enable_thinking=False, decode_concurrency=1,
                                prompt_concurrency=1, prompt_cache_size=1),
                    exclusions="none; no repairs or retries", primary="exact five factual fields using unchanged messages")
    sources = [Path(__file__), ROOT / "experiments/paper3_mistral_server.py", ROOT / "paper3/audit_runtime.py",
               ROOT / "paper3/commitment_memory.py", ROOT / "experiments/paper3_memory_pilot.py"]
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    backend = CompleteResponseBackend(args.model, args.base_url, store)
    fields = dict(principal_id=int, utility_A0=int, utility_B0=int, package_A0_B0_total=int, obligation_due=bool)
    for case in cases:
        key, record, request = case["key"], case["record"], case["request"]
        if (args.output / "sessions" / (key + ".json")).exists():
            continue
        backend.call_keys.clear()
        try:
            raw = backend.generate(request["messages"], temperature=request["temperature"], max_tokens=request["max_tokens"])
            reply = parse(raw, fields)
            result = dict(status="completed", reply=reply, errors=[f for f in fields if reply[f] != record["expected"][f]])
        except (ValueError, OSError, TimeoutError) as exc:
            result = dict(status="failed", error=str(exc))
        result.update({k: record[k] for k in ("actor", "condition", "release", "expected")})
        result.update(call_keys=list(backend.call_keys), protocol_hash=store.protocol_hash, source_case=key)
        store.save("sessions", key, result)
        print(key, result.get("errors", result.get("error")), flush=True)


if __name__ == "__main__":
    main()
