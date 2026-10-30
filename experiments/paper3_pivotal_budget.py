"""Frozen output-budget diagnostic; replay unchanged requests, never repair old runs."""
from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import PilotStore, digest
from paper3.native_inference import NativeBackend

PARENT_HASH = "6e7483451479916aa725ef674b037d9b33915076e8f2cf1d9d1ddde19fdba917"
STATES = ("active", "released", "not_ratified", "condition_failed")
CAP = 8192
REPLAY_FIELDS = ("request_equal_except_cap", "prompt_tokens_equal", "original_generated_prefix_equal")


def select_cases(cases):
    """Factor-only selection, independent of previous outputs or correctness."""
    selected = []
    for state_index, state in enumerate(STATES):
        for profile_index, profile in enumerate((863, 947)):
            actor = (0, 3, 6)[(state_index + profile_index) % 3]
            for case in cases:
                record = json.loads(case["messages"][1]["content"].split("\n")[0])
                # State is an exact fixture-name component, not inferred from its outcome.
                if (case["profile_seed"] == profile and record["principal"] == actor
                        and case["base_case"].split("-")[2] == state):
                    selected.append(copy.deepcopy(case))
    if len(selected) != 24 or len({c["name"] for c in selected}) != 24:
        raise ValueError("unexpected fixture layout")
    return selected


def replay_checks(old, new):
    before, after = old["request"].copy(), new["request"].copy()
    before.pop("max_tokens")
    after.pop("max_tokens")
    # MLX emits the last token exactly once, including at a length cutoff.
    prefix = old["generated_token_ids"]
    return dict(request_equal_except_cap=before == after,
                prompt_tokens_equal=old["prompt_token_ids"] == new["prompt_token_ids"],
                original_generated_prefix_equal=new["generated_token_ids"][:len(prefix)] == prefix)


class BudgetBackend(NativeBackend):
    def call(self, messages, seed):
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler
        import mlx.core as mx
        request = dict(model=str(self.path), messages=messages, seed=seed,
                       temperature=0.7, top_p=1.0, top_k=0, min_p=0.0, max_tokens=CAP)
        key = digest(dict(request=request, protocol=self.store.protocol_hash))
        path = self.store.root / "calls" / (key + ".json")
        if path.exists():
            return key, json.loads(path.read_text())
        started = time.time()
        mx.random.seed(seed)
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        chunks, tokens = [], []
        for part in stream_generate(self.model, self.tokenizer, prompt=prompt, max_tokens=CAP,
                sampler=make_sampler(temp=0.7, top_p=1.0, top_k=0, min_p=0.0), prompt_cache=None):
            chunks.append(part.text)
            tokens.append(part.token)
        record = dict(request=request, origin="direct stream_generate; normalized actual output, not HTTP",
            response=dict(choices=[dict(message=dict(role="assistant", content="".join(chunks)),
                                       finish_reason=part.finish_reason)],
                          usage=dict(prompt_tokens=part.prompt_tokens, completion_tokens=part.generation_tokens)),
            prompt_token_ids=prompt, generated_token_ids=tokens, peak_memory_gb=part.peak_memory,
            started_unix=started, elapsed_seconds=time.time() - started, protocol_hash=self.store.protocol_hash)
        self.store.save("calls", key, record)
        return key, record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    parent = json.loads((args.parent / "manifest.json").read_text())
    if digest(parent) != PARENT_HASH:
        raise ValueError("requires original frozen 72-call diagnostic")
    cases = select_cases(parent["protocol"]["cases"])
    old_calls = {}
    for case in cases:
        row = json.loads((args.parent / "sessions" / (case["name"] + ".json")).read_text())
        old = json.loads((args.parent / "calls" / (row["call_keys"][0] + ".json")).read_text())
        if old["request"]["messages"] != case["messages"] or old["request"]["seed"] != case["random_seed"]:
            raise ValueError("parent request mismatch")
        old_calls[case["name"]] = old
    runtime = {p: importlib.metadata.version(p) for p in ("mlx", "mlx-lm", "transformers")}
    if runtime != parent["protocol"]["runtime"]:
        raise ValueError("runtime changed since parent")
    protocol = dict(name="pivotal-native-budget-diagnostic-v1", cases=cases, max_calls=24,
        model=parent["protocol"]["model"], parent_manifest_hash=PARENT_HASH,
        parent_records_hash=digest(old_calls), runtime=runtime,
        max_tokens=CAP, original_max_tokens=2048,
        selection="four states x profiles 863/947; actor (0,3,6)[(state_index+profile_index)%3]; all three views",
        purpose="exploratory feasibility test of unchanged requests at a larger native reasoning cap",
        primary="normal termination AND valid final schema; pass >=23/24 with <=1 failure per view",
        secondary="exact fields, consequential vote and obligation errors; report invalid separately",
        replay="compare request except cap, exact prompt tokens, and old generated-token prefix; report any drift",
        exclusions="none; no retries, repairs, case replacement, prompt tuning or automatic budget increase",
        limitations="8 dependent base cases, actors not equally frequent (3/3/2); no institutional inference or automatic collective run")
    sources = [Path(__file__), ROOT / "paper3/native_inference.py", ROOT / "paper3/audit_runtime.py",
               ROOT / "paper3/commitment_memory.py"]
    store = PilotStore(args.output, protocol, sources)
    snapshot = args.output / "sources.json"
    if not snapshot.exists():
        with snapshot.open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    backend = BudgetBackend(Path(protocol["model"]), store)
    results = []
    for case in cases:
        row = backend.run_case(case, case["random_seed"], case["view"])
        new = json.loads((args.output / "calls" / (row["call_keys"][0] + ".json")).read_text())
        checks = replay_checks(old_calls[case["name"]], new)
        print("REPLAY", case["name"], checks, flush=True)
        results.append(dict(case=case["name"], view=case["view"], status=row["status"], exact=row["exact"], **checks))
    failures = {view: sum(r["status"] != "completed" for r in results if r["view"] == view)
                for view in ("transcript", "event_index", "registry")}
    print("COMPLETE", json.dumps(dict(failures=failures,
        feasibility_pass=sum(failures.values()) <= 1,
        replay_checks_all_pass=all(all(r[k] for k in REPLAY_FIELDS) for r in results))), flush=True)


if __name__ == "__main__":
    main()
