"""Conditional native-reasoning institutional discovery, not confirmation."""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import PilotStore, digest
from paper3.commitment_memory import profile, negotiate, first_vote, second_vote, contract_state, parse
from paper3.grounded_interface import GroundedInterface
from paper3.native_inference import NativeBackend, final_answer
from experiments.paper3_ministral_reasoning_gate import REVISION, NATIVE_SYSTEM, FINAL_FORMAT


def verify_gate(root, model):
    manifest = json.loads((root / "manifest.json").read_text())
    p = manifest["protocol"]
    if p["name"] != "ministral-native-validation-v2" or p["model"] != str(model) or p["model_revision"] != REVISION:
        raise ValueError("wrong prerequisite model/protocol")
    cases = [c for rows in p["stages"].values() for c in rows]
    if len(cases) != 64:
        raise ValueError("incomplete prerequisite case set")
    records = []
    for case in cases:
        r = json.loads((root / "sessions" / (case["name"] + ".json")).read_text())
        if r.get("status") != "completed" or r.get("reply") != case["expected"] or r["protocol_hash"] != digest(manifest):
            raise ValueError("prerequisite stage failed")
        if len(r["call_keys"]) != 1:
            raise ValueError("unexpected prerequisite call count")
        call = json.loads((root / "calls" / (r["call_keys"][0] + ".json")).read_text())
        choice = call["response"]["choices"][0]
        schema = {k: {"bool": bool, "str": str, "int": int}[v] for k, v in case["schema"].items()}
        if choice["finish_reason"] != "stop" or parse(final_answer(choice["message"]["content"]), schema) != case["expected"]:
            raise ValueError("prerequisite raw response failed")
        records.append(r)
    return dict(path=str(root), manifest_hash=digest(manifest), records_hash=digest(records))


def event_index(events):
    """Redundant source facts without the reducer's derived obligation status."""
    fields = ("type", "offer_id", "actor", "package", "first", "signatures", "project", "votes", "passed", "consenting_signers")
    return [{k: copy.deepcopy(e[k]) for k in fields if k in e} for e in events]


class CollectiveBackend:
    def __init__(self, native):
        self.native = native
        self.call_keys = []
        self.view = "transcript"
        self.seed_base = 0
        self.counter = 0

    def begin(self, seed_base, view="transcript"):
        self.call_keys.clear()
        self.seed_base, self.counter, self.view = seed_base, 0, view

    def generate(self, messages, **kwargs):
        # GroundedInterface has already assigned the principal and neutral schema.
        messages = copy.deepcopy(messages)
        messages[0]["content"] = messages[0]["content"].replace("You may reason internally; output JSON only.", "")
        messages[0]["content"] += "\n\n" + NATIVE_SYSTEM + "\n\n" + FINAL_FORMAT
        encoded, task = messages[-1]["content"].split("\n", 1)
        record = json.loads(encoded)
        if self.view == "event_index":
            record["event_index"] = event_index(record["events"])
        messages[-1]["content"] = json.dumps(record, sort_keys=True) + "\n" + task
        key, response = self.native.call(messages, self.seed_base + self.counter)
        self.counter += 1
        self.call_keys.append(key)
        choice = response["response"]["choices"][0]
        if choice["finish_reason"] != "stop":
            raise ValueError("non-normal generation termination")
        return final_answer(choice["message"]["content"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    if args.model.name != REVISION:
        raise ValueError("requires pinned Ministral")
    gate = verify_gate(args.gate, args.model)
    profiles = [profile(seed) for seed in (503, 601)]
    protocol = dict(name="native-negotiated-memory-discovery-v3", purpose="mechanism discovery, not confirmation",
        model=str(args.model), model_revision=REVISION, prerequisite=gate, profiles=[asdict(p) for p in profiles],
        temperature=0.7, top_p=1.0, top_k=0, min_p=0.0, max_tokens=2048,
        reasoning="native system and unique-closing final extraction; always enabled",
        seed="62000 + profile_index*1000 for history calls; 62500 + profile_index*1000 + release*100 for each branch's actors; same seeds across views",
        factors=dict(view=["transcript", "event_index", "registry"], mutual_release=[False, True]),
        max_calls=130, shared_calls_per_profile=23, branch_calls_per_profile=42,
        primary="paired obligation-state errors, due-vote breaches and principal-level realized utility, clustered by two shared negotiated histories",
        gates=dict(opportunity="both histories must produce a genuine due second obligation; otherwise no scale-up",
            interpretation="factual recognition is not internal belief; losses or nonpivotal votes are not objective abandonment",
            scale="no automatic confirmation; effect must survive structured-view control, unseen profiles and model replication"),
        exclusions="none; failed trajectories/branches and no-deal histories retained; no retries, repairs, budget/prompt changes",
        limitations=["two profiles are not a population estimate; related branches are dependent",
            "event index repeats source fields while registry supplies derived state; neither is input-token matched",
            "mutual release is imposed, not endogenously negotiated; no enforcement or election arm",
            "shared seeded draws across views are variance control, not guaranteed identical randomness after token divergence",
            "payoff generator intentionally permits beneficial exchanges; ceiling does not justify arbitrary task obfuscation"],
        runtime={p: importlib.metadata.version(p) for p in ("mlx", "mlx-lm", "transformers")})
    sources = [Path(__file__), ROOT / "paper3/commitment_memory.py", ROOT / "paper3/grounded_interface.py",
        ROOT / "paper3/native_inference.py", ROOT / "paper3/audit_runtime.py",
        ROOT / "experiments/paper3_ministral_reasoning_gate.py", ROOT / "experiments/paper3_native_validation.py",
        ROOT / "analysis/paper3_pilot_audit.py"]
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    direct = CollectiveBackend(NativeBackend(args.model, store))
    backend = GroundedInterface(direct)
    for index, p in enumerate(profiles):
        history_key = p.key + "-shared"
        path = args.output / "sessions" / (history_key + ".json")
        if path.exists():
            shared = json.loads(path.read_text())
        else:
            direct.begin(62000 + index * 1000)
            try:
                events = first_vote(backend, p, negotiate(backend, p))
                shared = dict(status="completed", events=events, profile=asdict(p))
            except (ValueError, OSError, TimeoutError) as exc:
                shared = dict(status="failed", error=str(exc), profile=asdict(p))
            shared.update(call_keys=list(direct.call_keys), protocol_hash=store.protocol_hash)
            store.save("sessions", history_key, shared)
        print(history_key, shared["status"], flush=True)
        if shared["status"] != "completed":
            continue
        print("STATE", contract_state(shared["events"]), flush=True)
        for release in (False, True):
            # Alternate view order across profiles, retaining the same paired seeds.
            views = ("transcript", "event_index", "registry") if index == 0 else ("registry", "event_index", "transcript")
            for view in views:
                key = f"{p.key}-release{int(release)}-{view}"
                if (args.output / "sessions" / (key + ".json")).exists():
                    continue
                direct.begin(62500 + index * 1000 + int(release) * 100, view)
                try:
                    result = second_vote(backend, p, shared["events"], ledger=view == "registry", release=release)
                    result["status"] = "completed"
                except (ValueError, OSError, TimeoutError) as exc:
                    result = dict(status="failed", error=str(exc))
                result.update(shared_history=history_key, condition=view, ledger=view == "registry", release=release,
                              call_keys=list(direct.call_keys), protocol_hash=store.protocol_hash)
                store.save("sessions", key, result)
                print(key, {k: result.get(k) for k in ("status", "obligation_errors", "breaches", "due_count")}, flush=True)


if __name__ == "__main__":
    main()
