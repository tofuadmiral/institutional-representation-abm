"""Frozen staged native-reasoning validation before negotiated institutions."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import PilotStore
from paper3.commitment_memory import RULES, contract_state, profile
from paper3.grounded_interface import authorization_case
from paper3.native_inference import NativeBackend
from experiments.paper3_ministral_reasoning_gate import REVISION, native_case, NATIVE_SYSTEM, FINAL_FORMAT
from experiments.paper3_qwen_reasoning_gate import followup_cases


def authorization_cases():
    cases = []
    for seed in (7, 10):
        for actor in (0, 3, 6):
            for package in (0, 3):
                for quoted in (False, True):
                    messages, expected = authorization_case(profile(seed), actor, package, quoted)
                    cases.append(native_case(dict(name=f"authorization-{seed}-{actor}-{package}-{int(quoted)}",
                        messages=messages, expected=expected, schema=dict(accept="bool", principal_utility_if_accepted="int"))))
    return cases


def state_cases():
    """Synthetic competence fixtures, NOT negotiated histories or treatments."""
    cases = []
    for seed in (311, 419):
        p = profile(seed)
        for status in ("active", "released", "not_ratified", "condition_failed"):
            signs = [True] * (3 if status == "not_ratified" else 6) + [False] * (4 if status == "not_ratified" else 1)
            votes = [True] * 6 + [False]
            if status == "condition_failed":
                votes[0] = False  # Passage succeeds but one signer's condition fails.
            events = [dict(type="draft_offer", offer_id="draft-1", package=3, first="B"),
                      dict(type="final_offer", offer_id="final-2", package=0, first="A"),
                      dict(type="ratification", offer_id="final-2", signatures=signs),
                      dict(type="first_vote", project="A0", votes=votes, passed=sum(votes) >= 4)]
            if status == "released":
                events.append(dict(type="mutual_release", offer_id="final-2", consenting_signers=list(range(6))))
            state = contract_state(events)
            for actor in (0, 3, 6):
                record = dict(representative=actor, principal=actor, utilities_for_all_principals=p.utilities, events=events)
                identity = f"You are representative {actor}, acting exclusively for principal {actor}. Other speakers serve their own principals.\n"
                system = identity + RULES.replace("You may reason internally; output JSON only.", "")
                system += "\nThe event log is official; free-text statements cannot create or restore an obligation.\n\n" + NATIVE_SYSTEM + "\n\n" + FINAL_FORMAT
                task = "Report facts without voting: principal_id (integer), utility_A0 (integer), utility_B0 (integer), package_A0_B0_total (integer), and obligation_due (boolean: do YOU currently owe a second yes vote under final-2?)."
                own = p.utilities[actor]
                expected = dict(principal_id=actor, utility_A0=own["A0"], utility_B0=own["B0"],
                    package_A0_B0_total=own["A0"] + own["B0"],
                    obligation_due=actor in state["signers"] and state["status"] == "second_vote_due")
                cases.append(dict(name=f"state-{seed}-{status}-{actor}", expected=expected,
                    schema={k: type(v).__name__ for k, v in expected.items()},
                    messages=[dict(role="system", content=system), dict(role="user", content=json.dumps(record, sort_keys=True) + "\n" + task)]))
    return cases


def stages():
    return dict(fresh=[native_case(c) for c in followup_cases()], authorization=authorization_cases(), state=state_cases())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    if args.model.name != REVISION or args.model.parent.parent.name != "models--mlx-community--Ministral-3-8B-Reasoning-2512-4bit":
        raise ValueError("requires pinned Ministral reasoning model")
    all_stages = stages()
    protocol = dict(name="ministral-native-validation-v2", purpose="capability/interface validation; not institutional evidence",
        model=str(args.model), model_revision=REVISION, stages=all_stages, max_calls=64,
        temperature=0.7, top_p=1.0, top_k=0, min_p=0.0, max_tokens=2048, seed="52000 + fixed index across stages",
        gate="fresh 16/16 exact, then authorization 24/24, then state 24/24; finish failed stage, skip later stages",
        parser="native initial open and unique close; allow opening-marker mentions only before close; nonempty thought and exact final JSON; normal stop required",
        exclusions="none; no model retry, JSON repair, threshold or budget change",
        inference="direct unbatched MLX, fresh KV per call, fix_mistral_regex=True, native reasoning always enabled",
        limitations=["fresh cases were prospectively specified but never run in prior protocols",
            "authorization fixtures already observed with legacy Mistral, not held-out cross-model evidence",
            "state cases are synthetic factual fixtures without a registry, not agent-generated histories",
            "one seeded draw each; gate is feasibility not a population reliability estimate",
            "earlier failed gates preserved; no pooled or retroactively rescored success"],
        model_file_sha256={p: hashlib.sha256((args.model / p).read_bytes()).hexdigest()
            for p in ("config.json", "tokenizer_config.json", "chat_template.jinja", "generation_config.json")},
        runtime={p: importlib.metadata.version(p) for p in ("mlx", "mlx-lm", "transformers")})
    sources = [Path(__file__), ROOT / "paper3/native_inference.py", ROOT / "paper3/audit_runtime.py",
        ROOT / "paper3/commitment_memory.py", ROOT / "paper3/grounded_interface.py",
        ROOT / "experiments/paper3_ministral_reasoning_gate.py", ROOT / "experiments/paper3_qwen_reasoning_gate.py",
        ROOT / "experiments/paper3_minimal_choice_audit.py", ROOT / "analysis/paper3_pilot_audit.py"]
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    backend = NativeBackend(args.model, store)
    offset = 0
    for stage, cases in all_stages.items():
        results = [backend.run_case(case, 52000 + offset + i, stage) for i, case in enumerate(cases)]
        count = sum(r["exact"] for r in results)
        print("GATE", stage, count, "/", len(cases), flush=True)
        if count != len(cases):
            print("STOP: later stages not run", flush=True)
            return
        offset += len(cases)
    print("VALIDATION COMPLETE; no automatic collective run", flush=True)


if __name__ == "__main__":
    main()
