"""Pinned Bonsai native-thinking smoke, private-choice screen and bounded diagnostic."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import PilotStore, digest
from paper3.commitment_memory import parse
from experiments.paper3_ministral_reasoning_gate import cases as private_cases, NATIVE_SYSTEM, FINAL_FORMAT
from experiments.paper3_pivotal_memory_diagnostic import diagnostic_cases
from experiments.paper3_pivotal_budget import select_cases

REVISION = "3f926b415992eaa2ae9dd7b573706494d6bbf787"
MODEL_REPO = "prism-ml/Ternary-Bonsai-2-27B-mlx-2bit"
CAP = 8192


def adapt_case(case):
    case = copy.deepcopy(case)
    system = case["messages"][0]["content"]
    if system.count(NATIVE_SYSTEM) != 1 or system.count(FINAL_FORMAT) != 1:
        raise ValueError("unexpected native system layout")
    case["messages"][0]["content"] = system.replace(NATIVE_SYSTEM, "").replace(
        FINAL_FORMAT, "After your native thinking block, return one JSON object, with no prose outside it.")
    return case


def stages():
    return dict(smoke=[dict(name="smoke-arithmetic", messages=[
        dict(role="system", content="After your native thinking block, return one JSON object, with no prose outside it."),
        dict(role="user", content='What is 17 multiplied by 19? Return result (integer).')],
        schema=dict(result="int"), expected=dict(result=323))],
        private=[adapt_case(c) for c in private_cases()[0]],
        pivotal=[adapt_case(c) for c in select_cases(diagnostic_cases())])


def final_answer(raw):
    # The opening <think> is in the saved prompt, not generated output.
    if raw.count("</think>") != 1:
        raise ValueError("missing or ambiguous native thinking closure")
    thought, answer = raw.split("</think>")
    if not thought.replace("<think>", "").strip() or not answer.strip() or "<think>" in answer:
        raise ValueError("empty reasoning/final answer or reopened reasoning")
    return answer.strip()


def append_generated_token(tokens, part):
    # VLM's terminal length chunk repeats the last emitted token; EOS does not.
    if part.token is not None and len(tokens) < part.generation_tokens:
        tokens.append(int(part.token))


class BonsaiBackend:
    def __init__(self, model_path, store):
        sys.path.insert(0, str(model_path / "runtime"))
        from vision_artifact import load_vl_model
        self.model, self.processor, self.config = load_vl_model(model_path)
        self.path, self.store = model_path, store

    def call(self, messages, seed):
        import mlx.core as mx
        from mlx_vlm import stream_generate
        request = dict(model=str(self.path), messages=messages, seed=seed, max_tokens=CAP,
            temperature=1.0, top_p=0.95, top_k=20, min_p=0.0,
            presence_penalty=0.0, repetition_penalty=1.0,
            enable_thinking=True, reasoning_effort="medium", prefill_step_size=512)
        key = digest(dict(request=request, protocol=self.store.protocol_hash))
        path = self.store.root / "calls" / (key + ".json")
        if path.exists():
            return key, json.loads(path.read_text())
        tokenizer = self.processor.tokenizer
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                               enable_thinking=True, reasoning_effort="medium")
        if not prompt.endswith("<think>\n"):
            raise ValueError("native thinking not enabled in actual prompt")
        prompt_ids = tokenizer.encode(prompt, add_special_tokens=True)
        mx.random.seed(seed)
        started = time.time()
        chunks, tokens = [], []
        for part in stream_generate(self.model, self.processor, prompt=prompt,
                max_tokens=CAP, temperature=1.0, top_p=0.95, top_k=20, min_p=0.0,
                presence_penalty=0.0, repetition_penalty=1.0, prefill_step_size=512,
                enable_thinking=True, skip_special_tokens=False):
            chunks.append(part.text)
            append_generated_token(tokens, part)
        if len(tokens) != part.generation_tokens:
            raise ValueError("stream token accounting mismatch")
        record = dict(request=request, rendered_prompt=prompt, prompt_token_ids=prompt_ids,
            generated_token_ids=tokens, origin="publisher rotation-aware VLM loader; native VLM stream, not HTTP",
            response=dict(choices=[dict(message=dict(role="assistant", content="".join(chunks)),
                finish_reason=part.finish_reason)], usage=dict(prompt_tokens=part.prompt_tokens,
                completion_tokens=part.generation_tokens)), peak_memory_gb=part.peak_memory,
            cached_tokens=part.cached_tokens, started_unix=started, elapsed_seconds=time.time() - started,
            protocol_hash=self.store.protocol_hash)
        self.store.save("calls", key, record)
        return key, record

    def run_case(self, case, seed, stage):
        path = self.store.root / "sessions" / (case["name"] + ".json")
        if path.exists():
            return json.loads(path.read_text())
        key, record = self.call(case["messages"], seed)
        result = dict(case=case["name"], stage=stage, expected=case["expected"], thinking=True,
                      call_keys=[key], protocol_hash=self.store.protocol_hash)
        try:
            choice = record["response"]["choices"][0]
            if choice["finish_reason"] != "stop":
                raise ValueError("generation did not end normally")
            schema = {k: {"bool": bool, "int": int, "str": str}[v] for k, v in case["schema"].items()}
            reply = parse(final_answer(choice["message"]["content"]), schema)
            result.update(status="completed", reply=reply, exact=reply == case["expected"],
                          field_errors=[k for k in schema if reply[k] != case["expected"][k]])
        except ValueError as exc:
            result.update(status="failed", exact=False, error=str(exc))
        self.store.save("sessions", case["name"], result)
        print(stage, case["name"], result["status"], result["exact"],
              record["response"]["usage"], flush=True)
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    if args.model.name != REVISION or args.model.parent.parent.name != "models--prism-ml--Ternary-Bonsai-2-27B-mlx-2bit":
        raise ValueError("wrong model revision")
    all_stages = stages()
    protocol = dict(name="bonsai2-native-validation-v1", model=str(args.model), model_repo=MODEL_REPO,
        model_revision=REVISION, stages=all_stages, max_calls=41,
        max_tokens=CAP, temperature=1.0, top_p=0.95, top_k=20, min_p=0.0,
        reasoning_effort="medium", reasoning="native chat-template prefill; no forced thinking closure",
        seed="82000 + fixed index across stages; one draw per request",
        gates="smoke 1/1 exact; private 16/16 exact; if passed finish all 24 pivotal cases; no collective follow-on",
        outcomes="normal schema-valid output, own payoff/action, obligation state, valid harmful votes; invalid is error, never fabricated vote",
        exclusions="none; no retries, JSON repair, prompt changes or automatic budget escalation",
        limitations=["vendor aggregate benchmarks not taken as research competence",
            "selected familiar synthetic fixtures; no held-out confirmation or seven-agent negotiation",
            "Qwen-derived, not an independent third base-model family",
            "native prompt, sampling and backend differ from Ministral; not a weights-only causal comparison"],
        model_file_sha256={str(p.relative_to(args.model)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in args.model.rglob("*") if p.is_file() and p.name != "model.safetensors"
            and "__pycache__" not in p.parts},
        runtime={d.metadata["Name"]: d.version for d in importlib.metadata.distributions()})
    sources = [Path(__file__), ROOT / "paper3/audit_runtime.py", ROOT / "paper3/commitment_memory.py",
        ROOT / "experiments/paper3_pivotal_budget.py", ROOT / "experiments/paper3_pivotal_memory_diagnostic.py",
        ROOT / "experiments/paper3_ministral_reasoning_gate.py", ROOT / "experiments/paper3_native_validation.py",
        ROOT / "experiments/paper3_native_memory_pilot.py", ROOT / "experiments/paper3_qwen_reasoning_gate.py",
        ROOT / "experiments/paper3_minimal_choice_audit.py", ROOT / "paper3/grounded_interface.py",
        ROOT / "paper3/native_inference.py"]
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    backend = BonsaiBackend(args.model, store)
    offset = 0
    for stage, cases in all_stages.items():
        rows = [backend.run_case(c, 82000 + offset + i, stage) for i, c in enumerate(cases)]
        count = sum(r["exact"] for r in rows)
        print("STAGE", stage, count, "/", len(rows), flush=True)
        if stage != "pivotal" and count != len(rows):
            print("STOP: later stages not run", flush=True)
            return
        offset += len(cases)
    print("COMPLETE; exploratory diagnostic only", flush=True)


if __name__ == "__main__":
    main()
