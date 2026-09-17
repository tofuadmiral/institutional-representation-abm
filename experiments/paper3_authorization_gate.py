"""Twenty-four strict, pivotal private decisions before grounded collective use."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import PilotStore
from paper3.commitment_memory import profile, parse
from paper3.grounded_interface import authorization_case
from experiments.paper3_memory_pilot import CompleteResponseBackend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8013/v1")
    args = parser.parse_args()
    protocol = dict(name="grounded-pivotal-authorization-gate-v1", purpose="interface validation, not institutional evidence",
                    model=args.model, model_revision=args.model_revision, seeds=[7, 10], actors=[0, 3, 6],
                    packages=[0, 3], quoted_draft=[False, True], expected_calls=24,
                    max_tokens=96, temperature=0, pass_gate="24/24 exact decisions and utility fields; all parse normally",
                    exclusions="none; no retries or repairs", server=dict(fix_mistral_regex=True, enable_thinking=False, decode_concurrency=1, prompt_concurrency=1, prompt_cache_size=1),
                    runtime={p: importlib.metadata.version(p) for p in ("mlx", "mlx-lm", "transformers")})
    sources = [Path(__file__), ROOT / "paper3/grounded_interface.py", ROOT / "paper3/commitment_memory.py",
               ROOT / "paper3/audit_runtime.py", ROOT / "experiments/paper3_memory_pilot.py", ROOT / "experiments/paper3_mistral_server.py"]
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    backend = CompleteResponseBackend(args.model, args.base_url, store)
    passed = 0
    for seed in protocol["seeds"]:
        for actor in protocol["actors"]:
            for package in protocol["packages"]:
                for quoted in protocol["quoted_draft"]:
                    key = f"seed{seed}-actor{actor}-package{package}-quoted{int(quoted)}"
                    path = args.output / "sessions" / (key + ".json")
                    if path.exists():
                        result = json.loads(path.read_text())
                    else:
                        backend.call_keys.clear()
                        messages, expected = authorization_case(profile(seed), actor, package, quoted)
                        try:
                            raw = backend.generate(messages, temperature=0, max_tokens=96)
                            reply = parse(raw, dict(accept=bool, principal_utility_if_accepted=int))
                            result = dict(status="completed", reply=reply, expected=expected, exact=reply == expected)
                        except (ValueError, OSError, TimeoutError) as exc:
                            result = dict(status="failed", error=str(exc), expected=expected, exact=False)
                        result.update(call_keys=list(backend.call_keys), protocol_hash=store.protocol_hash)
                        store.save("sessions", key, result)
                    passed += result["exact"]
                    print(key, result["status"], result["exact"], flush=True)
    print(f"gate: {passed}/24 exact", flush=True)


if __name__ == "__main__":
    main()
