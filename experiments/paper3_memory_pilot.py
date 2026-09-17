"""Frozen discovery pilot. No parameter tuning or response repairs in a run."""

from __future__ import annotations

import argparse
import json
import importlib.metadata
from dataclasses import asdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paper3.audit_runtime import PilotStore, RecordedBackend, digest
from paper3.commitment_memory import profile, negotiate, first_vote, second_vote


class CompleteResponseBackend(RecordedBackend):
    def generate(self, *args, **kwargs):
        raw = super().generate(*args, **kwargs)
        record = json.loads((self.store.root / "calls" / (self.call_keys[-1] + ".json")).read_text())
        if record["response"]["choices"][0].get("finish_reason") != "stop":
            raise ValueError("server response did not end normally; preserved but not parsed")
        return raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8013/v1")
    parser.add_argument("--mistral-tokenizer-fix", action="store_true",
                        help="Record use of paper3_mistral_server.py; does not alter a running server")
    parser.add_argument("--grounded-interface", action="store_true")
    parser.add_argument("--authorization-gate", type=Path,
                        help="Required 24-case passing gate for the grounded interface")
    args = parser.parse_args()
    gate_provenance = None
    if args.grounded_interface:
        if args.authorization_gate is None:
            raise ValueError("grounded collective pilot requires the private authorization gate")
        gate_manifest = json.loads((args.authorization_gate / "manifest.json").read_text())
        gate_protocol = gate_manifest["protocol"]
        if gate_protocol["model"] != args.model or gate_protocol["model_revision"] != args.model_revision:
            raise ValueError("authorization gate model does not match collective model")
        gate_sessions = [json.loads(p.read_text()) for p in sorted((args.authorization_gate / "sessions").glob("*.json"))]
        if len(gate_sessions) != 24 or not all(r.get("status") == "completed" and r.get("exact") is True for r in gate_sessions):
            raise ValueError("authorization gate did not pass 24/24")
        gate_provenance = dict(path=str(args.authorization_gate), manifest_hash=digest(gate_manifest), records_hash=digest(gate_sessions))
    profiles = [profile(seed, reverse) for seed in (7, 10) for reverse in (False, True)]
    protocol = dict(name="negotiated-commitment-memory-grounded-v2" if args.grounded_interface else "negotiated-commitment-memory-discovery-v1", purpose="mechanism discovery, not confirmation",
                    model=args.model, model_revision=args.model_revision, base_url=args.base_url,
                    profiles=[asdict(p) for p in profiles], temperature=0, max_tokens=192,
                    shared_calls_per_history=23, branch_calls_per_history=28, max_calls=204,
                    factors=dict(ledger=[False, True], mutual_release=[False, True]),
                    primary="paired obligation-state errors and due-but-no votes, clustered by negotiated history",
                    secondary=["realized utility by principal", "false obligations", "negative unbound votes"],
                    exclusions="none; parse/transport errors terminate and mark the affected trajectory or branch; no repair calls",
                    gates=dict(instrument_validity="all deterministic tests pass; no silent truncation",
                               manipulation="at least two shared histories produce an active second obligation",
                               scale="only if process signal remains after checking state, signed harm and label effects"),
                    limitations=["four dependent histories are not a population estimate",
                                 "ledger adds derived information and input tokens",
                                 "all signatures releasing obligations are experimentally imposed, not negotiated",
                                 "no election or enforcement treatment", "no intrinsic incentives are inferred"],
                    runtime={name: importlib.metadata.version(name) for name in ("mlx", "mlx-lm", "transformers")},
                    grounded_interface=args.grounded_interface, authorization_gate=gate_provenance,
                    server=dict(enable_thinking=False, decode_concurrency=1, prompt_concurrency=1, prompt_cache_size=1,
                                fix_mistral_regex=args.mistral_tokenizer_fix))
    sources = [Path(__file__), ROOT / "paper3/commitment_memory.py", ROOT / "paper3/audit_runtime.py"]
    if args.mistral_tokenizer_fix:
        if "mistral" not in args.model.lower():
            raise ValueError("Mistral tokenizer fix requested for another model")
        sources.append(ROOT / "experiments/paper3_mistral_server.py")
    if args.grounded_interface:
        sources.append(ROOT / "paper3/grounded_interface.py")
    store = PilotStore(args.output, protocol, sources)
    snapshot = args.output / "sources.json"
    if not snapshot.exists():
        with snapshot.open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    backend = CompleteResponseBackend(args.model, args.base_url, store)
    if args.grounded_interface:
        from paper3.grounded_interface import GroundedInterface
        backend = GroundedInterface(backend)
    for p in profiles:
        history_key = p.key + "-shared"
        file = args.output / "sessions" / (history_key + ".json")
        if file.exists():
            shared = json.loads(file.read_text())
        else:
            backend.call_keys.clear()
            try:
                events = first_vote(backend, p, negotiate(backend, p))
                shared = dict(status="completed", events=events, profile=asdict(p))
            except (ValueError, OSError, TimeoutError) as exc:
                shared = dict(status="failed", error=str(exc), profile=asdict(p))
            shared.update(call_keys=list(backend.call_keys), protocol_hash=store.protocol_hash)
            store.save("sessions", history_key, shared)
            print(history_key, shared["status"], flush=True)
        if shared["status"] != "completed":
            continue
        for release in (False, True):
            for ledger in (False, True):
                key = f"{p.key}-release{int(release)}-ledger{int(ledger)}"
                if (args.output / "sessions" / (key + ".json")).exists():
                    continue
                backend.call_keys.clear()
                try:
                    result = second_vote(backend, p, shared["events"], ledger=ledger, release=release)
                    result["status"] = "completed"
                except (ValueError, OSError, TimeoutError) as exc:
                    result = dict(status="failed", error=str(exc))
                result.update(shared_history=history_key, ledger=ledger, release=release,
                              call_keys=list(backend.call_keys), protocol_hash=store.protocol_hash)
                store.save("sessions", key, result)
                print(key, {k: result.get(k) for k in ("status", "obligation_errors", "breaches", "due_count")}, flush=True)


if __name__ == "__main__":
    main()
