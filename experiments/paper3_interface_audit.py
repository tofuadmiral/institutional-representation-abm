"""Prospective diagnostic of boolean-example anchoring on one frozen history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paper3.audit_runtime import PilotStore, digest
from paper3.commitment_memory import Profile, second_vote
from experiments.paper3_memory_pilot import CompleteResponseBackend


class InterfaceBackend:
    def __init__(self, backend, condition):
        self.backend, self.condition = backend, condition

    def generate(self, messages, **kwargs):
        messages = [dict(m) for m in messages]
        original = 'Return {"obligation_due":true,"vote":true}.'
        alternatives = {
            "true_example": original,
            "false_example": 'Return {"obligation_due":false,"vote":false}.',
            "neutral_schema": 'Return a JSON object with exactly two fields: obligation_due (a boolean reporting whether your obligation is currently due), and vote (a boolean: true for yes, false for no). Choose each value from the actual state; there is no preset answer.'}
        if original not in messages[-1]["content"]:
            raise ValueError("unexpected original interface")
        messages[-1]["content"] = messages[-1]["content"].replace(original, alternatives[self.condition])
        return self.backend.generate(messages, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8013/v1")
    args = parser.parse_args()
    shared = json.loads(args.source.read_text())
    source_manifest = json.loads((args.source.parents[1] / "manifest.json").read_text())
    if shared["status"] != "completed":
        raise ValueError("history incomplete")
    spec = shared["profile"]
    p = Profile(spec["key"], {int(i): v for i, v in spec["utilities"].items()}, spec["formateur"])
    protocol = dict(name="boolean-example-diagnostic-v1", purpose="instrument validity, not institutional efficacy",
                    source=str(args.source), source_hash=digest(shared), model=args.model,
                    runtime=source_manifest["protocol"]["runtime"],
                    model_revision=source_manifest["protocol"]["model_revision"],
                    conditions=["true_example", "false_example", "neutral_schema"],
                    release=[False, True], ledger=True, temperature=0, max_tokens=192, max_calls=42,
                    primary="whether answers track example booleans instead of actual obligation state",
                    gate="any example-dependent state answer undermines original memory-pilot interpretation",
                    exclusions="none; affected branch fails on malformed or truncated output; no repairs",
                    limits="one deliberately selected failure history; diagnostic only")
    sources = [Path(__file__), ROOT / "paper3/commitment_memory.py", ROOT / "paper3/audit_runtime.py", ROOT / "experiments/paper3_memory_pilot.py"]
    store = PilotStore(args.output, protocol, sources)
    snapshot = args.output / "sources.json"
    if not snapshot.exists():
        with snapshot.open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    backend = CompleteResponseBackend(args.model, args.base_url, store)
    for release in (False, True):
        for condition in protocol["conditions"]:
            key = f"release{int(release)}-{condition}"
            if (args.output / "sessions" / (key + ".json")).exists():
                continue
            backend.call_keys.clear()
            try:
                result = second_vote(InterfaceBackend(backend, condition), p, shared["events"],
                                     ledger=True, release=release)
                result["status"] = "completed"
            except (ValueError, OSError, TimeoutError) as exc:
                result = dict(status="failed", error=str(exc))
            result.update(condition=condition, release=release, call_keys=list(backend.call_keys),
                          protocol_hash=store.protocol_hash)
            store.save("sessions", key, result)
            print(key, {k: result.get(k) for k in ("status", "obligation_errors", "breaches", "due_count")}, flush=True)


if __name__ == "__main__":
    main()
