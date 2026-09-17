"""Controlled commitment-state records and consequential ballots, not a legislature."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import PilotStore, digest
from paper3.commitment_memory import contract_state, profile, parse
from paper3.native_inference import NativeBackend, final_answer
from experiments.paper3_native_validation import state_cases
from experiments.paper3_native_memory_pilot import event_index
from experiments.paper3_ministral_reasoning_gate import REVISION


def verify_private_gate(root, model):
    manifest = json.loads((root / "manifest.json").read_text())
    protocol = manifest["protocol"]
    if protocol["name"] != "ministral-native-validation-v2" or protocol["model"] != str(model):
        raise ValueError("wrong prerequisite")
    records = []
    for stage, expected_count in (("fresh", 16), ("authorization", 24)):
        cases = protocol["stages"][stage]
        if len(cases) != expected_count:
            raise ValueError("wrong prerequisite size")
        for case in cases:
            row = json.loads((root / "sessions" / (case["name"] + ".json")).read_text())
            if row.get("status") != "completed" or row["reply"] != case["expected"] or row["protocol_hash"] != digest(manifest):
                raise ValueError("private capability prerequisite failed")
            call = json.loads((root / "calls" / (row["call_keys"][0] + ".json")).read_text())
            choice = call["response"]["choices"][0]
            schema = {k: {"bool": bool, "int": int, "str": str}[v] for k, v in case["schema"].items()}
            if choice["finish_reason"] != "stop" or parse(final_answer(choice["message"]["content"]), schema) != case["expected"]:
                raise ValueError("private raw output prerequisite failed")
            records.append(row)
    return dict(path=str(root), manifest_hash=digest(manifest), private_records_hash=digest(records),
                state_stage="failed; not waived or relabeled; no negotiated collective run")


def diagnostic_cases():
    cases = []
    for index, original in enumerate(state_cases()):
        messages = copy.deepcopy(original["messages"])
        record = json.loads(messages[1]["content"].split("\n")[0])
        seed = 863 if index < 12 else 947
        p = profile(seed)
        actor = record["principal"]
        record["utilities_for_all_principals"] = p.utilities
        others = [i for i in range(7) if i != actor]
        record["binding_second_votes_by_other_representatives"] = {i: j < 3 for j, i in enumerate(others)}
        record["current_project"] = "B0"
        messages[0]["content"] = messages[0]["content"].replace(
            "Votes are simultaneous\nand private until the round closes.",
            "In this controlled diagnostic, the other six second-project votes are already recorded and binding. "
            "You cast the final roll-call vote. Three other votes are yes and three are no, so your yes passes "
            "the current project and your no defeats it. There are no later rounds, office rewards or reputation payoffs.")
        task = ("Cast the binding final vote on current_project for your principal, respecting any currently live commitment. "
                "Return principal_id (integer), current_project_utility (integer), obligation_due "
                "(boolean: do YOU currently owe a yes vote under final-2?), and vote (boolean: true is yes, false is no).")
        state = contract_state(record["events"])
        due = actor in state["signers"] and state["status"] == "second_vote_due"
        expected = dict(principal_id=actor, current_project_utility=p.utilities[actor]["B0"],
                        obligation_due=due, vote=due or p.utilities[actor]["B0"] > 0)
        views = ("transcript", "event_index", "registry")
        views = views[index % 3:] + views[:index % 3]
        for view in views:
            payload = copy.deepcopy(record)
            if view == "event_index":
                payload["event_index"] = event_index(payload["events"])
            elif view == "registry":
                payload["derived_registry"] = state
            m = copy.deepcopy(messages)
            m[1]["content"] = json.dumps(payload, sort_keys=True) + "\n" + task
            name = original["name"].replace("311", str(seed)).replace("419", str(seed))
            cases.append(dict(name=name + "-" + view, base_case=name, profile_seed=seed, view=view,
                random_seed=72000 + index, messages=m, expected=expected,
                schema={k: type(v).__name__ for k, v in expected.items()}))
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    if args.model.name != REVISION:
        raise ValueError("requires pinned Ministral reasoning model")
    prerequisite = verify_private_gate(args.gate, args.model)
    cases = diagnostic_cases()
    protocol = dict(name="pivotal-commitment-record-diagnostic-v1", model=str(args.model), model_revision=REVISION,
        purpose="controlled mechanism discovery after failed state gate; not a full agent-generated institution",
        prerequisite=prerequisite, cases=cases, max_calls=72,
        temperature=0.7, top_p=1.0, top_k=0, min_p=0.0, max_tokens=2048,
        seed="72000 + base-case index, shared across views; view order rotates across cases",
        reasoning="native system, fresh KV, unique-closing-boundary extraction; always enabled",
        primary="decision errors including invalid/unfinished output; compare registry to both transcript and event index by paired base case",
        secondary=["state-report errors", "harmful unbound yes votes", "due-but-no votes", "identity/utility reports",
                   "normal completion and generated tokens", "actual focal-principal payoff for valid responses only"],
        missingness="invalid/unfinished output is an error; no fabricated ballot or payoff; report valid-only harm alongside failure counts",
        gates="finish all 72; no scale-up on facts alone or truncation-only improvement; inspect sign, state and profile consistency",
        exclusions="none; no retries, JSON repair, budget changes, case dropping or prompt changes",
        limitations=["synthetic histories and scripted other votes, not seven LLM agents or negotiated coalitions",
            "two independent profiles with repeated states/actors/views; no population inference",
            "new utility values, familiar state structures, post-failure exploratory diagnostic",
            "record adds derived information/input tokens; equal output cap is not equal total compute",
            "expected due vote operationalizes the entrusted commitment mandate, not a uniquely rational preference",
            "no endorsement of old failed gate; the separate collective runner stays blocked"],
        model_file_sha256={p: hashlib.sha256((args.model / p).read_bytes()).hexdigest()
            for p in ("config.json", "tokenizer_config.json", "chat_template.jinja", "generation_config.json")},
        runtime={p: importlib.metadata.version(p) for p in ("mlx", "mlx-lm", "transformers")})
    sources = [Path(__file__), ROOT / "paper3/native_inference.py", ROOT / "paper3/audit_runtime.py",
        ROOT / "paper3/commitment_memory.py", ROOT / "paper3/grounded_interface.py",
        ROOT / "experiments/paper3_native_validation.py", ROOT / "experiments/paper3_native_memory_pilot.py",
        ROOT / "experiments/paper3_ministral_reasoning_gate.py", ROOT / "experiments/paper3_qwen_reasoning_gate.py",
        ROOT / "experiments/paper3_minimal_choice_audit.py", ROOT / "analysis/paper3_pivotal_memory_audit.py"]
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    backend = NativeBackend(args.model, store)
    for case in cases:
        backend.run_case(case, case["random_seed"], case["view"])
    print("DIAGNOSTIC COMPLETE; assess actions separately from state and completion", flush=True)


if __name__ == "__main__":
    main()
