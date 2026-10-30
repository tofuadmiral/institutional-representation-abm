"""Bounded negotiated-history discovery; separate from all earlier frozen gates."""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict, replace
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Import the dependency-light audit directly. The legacy analysis package's
# __init__ eagerly loads plotting libraries absent from the frozen model runtime.
sys.path.insert(0, str(ROOT / "analysis"))
from paper3_native_diagnostic_audit import audit
from experiments.paper3_bonsai_validation import BonsaiBackend, REVISION, final_answer
from experiments.paper3_bonsai_tokenizer_audit import BASE_REVISION
from experiments.paper3_native_memory_pilot import event_index
from paper3.audit_runtime import PilotStore, digest
from paper3.commitment_memory import profile, negotiate, first_vote, second_vote, contract_state, project_sequence
from paper3.grounded_interface import GroundedInterface

GATE_HASH = "423db8e5526e3108c3d13b8b9697d193009193cc9c585782a49652ed59a509cb"
MAX_INPUT = 8192
MAX_MESSAGE = 400


def study_profiles():
    # Prospectively cover both blocs and the outsider; no observed model outcomes
    # select a profile/leader. This is coverage, not a causal leader comparison.
    return [replace(profile(seed), formateur=leader, key=f"seed{seed}-leader{leader}")
            for seed, leader in ((503, 0), (601, 3), (709, 6))]


def mechanism_opportunity(p, events):
    """Algebraic coverage benchmarks, not imputed counterfactual model choices."""
    state = contract_state(events)
    second = project_sequence(events)[1]
    due = set(state["signers"]) if state["status"] == "second_vote_due" else set()
    positive = {i for i, row in p.utilities.items() if row[second] > 0}
    return dict(costly_due_signers=sorted(i for i in due if p.utilities[i][second] < 0),
        positive_utility_second_voters=sorted(positive), myopic_second_passes=len(positive) >= 4,
        honoring_due_scenario_passes=len(positive | due) >= 4,
        due_votes_can_change_passage=len(positive) < 4 <= len(positive | due))


def frozen_store(root, protocol, sources):
    # JSON object keys are strings. Normalize before the strict reload comparison;
    # never weaken PilotStore's guard or rewrite an existing frozen manifest.
    return PilotStore(root, json.loads(json.dumps(protocol)), sources)


def admit_validation(report):
    if report["integrity_errors"]:
        raise ValueError("validation provenance/score errors")
    for stage, size in (("smoke", 1), ("private", 16), ("pivotal", 24)):
        row = report["stages"].get(stage, {})
        if row.get("calls") != size or row.get("not_run", 0):
            raise ValueError("validation must finish all 41 cases")
        if stage != "pivotal" and row.get("exact") != size:
            raise ValueError("private/smoke prerequisite failed")
    if report["stages"]["pivotal"]["valid"] < 23:
        raise ValueError("pivotal completion prerequisite failed")
    # State and ballot errors are outcomes, not hidden admission exclusions.


def verify_gate(root, model):
    manifest = json.loads((root / "manifest.json").read_text())
    if digest(manifest) != GATE_HASH or manifest["protocol"]["model"] != str(model):
        raise ValueError("wrong frozen Bonsai prerequisite")
    for name, expected in manifest["sources"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError("validation source changed: " + name)
    report = audit(root)
    admit_validation(report)
    protocol = manifest["protocol"]
    versions = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}
    if versions != protocol["runtime"]:
        raise ValueError("Bonsai runtime changed since validation")
    for name, expected in protocol["model_file_sha256"].items():
        if hashlib.sha256((model / name).read_bytes()).hexdigest() != expected:
            raise ValueError("model/runtime artifact changed: " + name)
    records = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
               for folder in ("calls", "sessions") for p in sorted((root / folder).glob("*.json"))}
    return dict(path=str(root), manifest_hash=GATE_HASH, record_hashes=records,
                outcomes=report["stages"]), protocol


class CollectiveBackend:
    def __init__(self, native, base_tokenizer):
        self.native, self.base_tokenizer = native, base_tokenizer
        self.call_keys, self.pending_request = [], None
        self.begin(0)

    def begin(self, seed, view="transcript"):
        self.seed, self.counter, self.view = seed, 0, view
        self.call_keys.clear()
        self.pending_request = None

    def generate(self, messages, **kwargs):
        messages = copy.deepcopy(messages)
        messages[0]["content"] = messages[0]["content"].replace("You may reason internally; output JSON only.", "")
        messages[0]["content"] += "\nAfter your native thinking block, return one JSON object, with no prose outside it."
        encoded, task = messages[-1]["content"].split("\n", 1)
        record = json.loads(encoded)
        if self.view == "event_index":
            record["event_index"] = event_index(record["events"])
        if "message (string)" in task:
            task += f" Your public message must contain at most {MAX_MESSAGE} characters."
        messages[-1]["content"] = json.dumps(record, sort_keys=True) + "\n" + task
        self.pending_request = messages
        tokenizer = self.native.processor.tokenizer
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                               enable_thinking=True, reasoning_effort="medium")
        ids = tokenizer.encode(prompt, add_special_tokens=True)
        if ids != self.base_tokenizer.encode(prompt, add_special_tokens=True):
            raise ValueError("dynamic-history tokenization differs from official base tokenizer")
        if len(ids) > MAX_INPUT:
            raise ValueError("rendered input exceeds frozen local feasibility cap")
        key, response = self.native.call(messages, self.seed + self.counter)
        self.counter += 1
        self.call_keys.append(key)
        self.pending_request = None  # The actual request is now in the raw call record.
        choice = response["response"]["choices"][0]
        if choice["finish_reason"] != "stop":
            raise ValueError("non-normal generation termination")
        answer = final_answer(choice["message"]["content"])
        normalized = answer.strip()
        if normalized.startswith("```") and normalized.endswith("```"):
            normalized = normalized.split("\n", 1)[1].rsplit("```", 1)[0]
        value = json.loads(normalized)
        if isinstance(value, dict) and isinstance(value.get("message"), str) and len(value["message"]) > MAX_MESSAGE:
            raise ValueError("public message exceeds frozen limit; no truncation or retry")
        return answer  # Engine validates exact fields/types; never replaces the action.


def main():
    parser = argparse.ArgumentParser()
    for name in ("model", "gate", "base-tokenizer", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    if args.model.name != REVISION or args.base_tokenizer.name != BASE_REVISION:
        raise ValueError("requires pinned Bonsai and official base tokenizer")
    gate, validated = verify_gate(args.gate, args.model)
    profiles = study_profiles()
    protocol = dict(name="bonsai-negotiated-memory-discovery-v1", model=str(args.model), model_revision=REVISION,
        prerequisite=gate, profiles=[asdict(p) for p in profiles], max_calls=195,
        inference={k: validated[k] for k in ("runtime", "model_file_sha256", "max_tokens", "temperature", "top_p", "top_k", "min_p", "reasoning_effort")},
        base_tokenizer=str(args.base_tokenizer), base_tokenizer_revision=BASE_REVISION,
        base_file_hashes={name: hashlib.sha256((args.base_tokenizer / name).read_bytes()).hexdigest()
                         for name in ("config.json", "tokenizer.json", "tokenizer_config.json")},
        max_input_tokens=MAX_INPUT, max_public_message_characters=MAX_MESSAGE,
        seed="history 92000 + profile_index*1000 + call index; branch 92500 + profile_index*1000 + release*100 + actor; shared across views",
        factors=dict(view=["transcript", "event_index", "registry"], imposed_release=[False, True]),
        outcomes="state reports, actual due-vote breaches, false obligations, per-principal utility, costly obligation coverage and vote pivotality; descriptive",
        stopping="finish fixed batch; at least two histories need live costly obligations for mechanism opportunity; no automatic confirmation; retain ceiling/null",
        failures="no retry, repair, coercion, fabricated vote/payoff or message truncation; preserve failed/no-deal sessions and exact unsubmitted requests",
        limitations=["adaptive discovery designed while Bonsai validation was in progress, not confirmation",
            "three agent-generated histories with dependent execution branches; leadership and profile differ together, no causal role comparison or population estimate",
            "registry supplies derived state and extra tokens; not information/compute matched",
            "release is imposed, not agent-negotiated; treatment occurs after bargaining",
            "state reports are not internal beliefs; losses/nonpivotal votes do not prove objective abandonment",
            "same Qwen-derived model family; no independent-family replication"])
    files = set(validated_path for validated_path in json.loads((args.gate / "manifest.json").read_text())["sources"])
    files.update(str(ROOT / p) for p in ("experiments/paper3_bonsai_memory_pilot.py",
        "experiments/paper3_bonsai_tokenizer_audit.py", "analysis/paper3_native_diagnostic_audit.py"))
    sources = [Path(p) for p in sorted(files)]
    store = frozen_store(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    from transformers import AutoTokenizer
    reference = AutoTokenizer.from_pretrained(str(args.base_tokenizer), local_files_only=True)
    direct = CollectiveBackend(BonsaiBackend(args.model, store), reference)
    backend = GroundedInterface(direct)
    for index, p in enumerate(profiles):
        key = p.key + "-shared"
        path = args.output / "sessions" / (key + ".json")
        if path.exists():
            shared = json.loads(path.read_text())
        else:
            direct.begin(92000 + index * 1000)
            try:
                events = first_vote(backend, p, negotiate(backend, p))
                shared = dict(status="completed", events=events, profile=asdict(p), **mechanism_opportunity(p, events))
            except (ValueError, OSError, TimeoutError) as exc:
                shared = dict(status="failed", error=str(exc), profile=asdict(p), unsubmitted_request=direct.pending_request)
            shared.update(call_keys=list(direct.call_keys), protocol_hash=store.protocol_hash)
            store.save("sessions", key, shared)
        print(key, shared["status"], shared.get("costly_due_signers"), flush=True)
        if shared["status"] != "completed":
            continue
        for release in (False, True):
            views = ("transcript", "event_index", "registry")
            views = views[index:] + views[:index]
            for view in views:
                key = f"{p.key}-release{int(release)}-{view}"
                if (args.output / "sessions" / (key + ".json")).exists():
                    continue
                direct.begin(92500 + index * 1000 + int(release) * 100, view)
                try:
                    result = second_vote(backend, p, shared["events"], ledger=view == "registry", release=release)
                    result["status"] = "completed"
                except (ValueError, OSError, TimeoutError) as exc:
                    result = dict(status="failed", error=str(exc), unsubmitted_request=direct.pending_request)
                result.update(shared_history=p.key + "-shared", condition=view, ledger=view == "registry", release=release,
                              call_keys=list(direct.call_keys), protocol_hash=store.protocol_hash)
                store.save("sessions", key, result)
                print(key, {k: result.get(k) for k in ("status", "obligation_errors", "breaches", "due_count")}, flush=True)
    print("DISCOVERY COMPLETE; assess coverage, failures and actual welfare; no automatic expansion", flush=True)


if __name__ == "__main__":
    main()
