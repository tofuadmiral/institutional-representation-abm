"""Native-reasoning private-choice capability screen; not institutional evidence."""
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
from experiments.paper3_minimal_choice_audit import choice_case
from experiments.paper3_qwen_reasoning_gate import followup_cases

REVISION = "0b6f067915514745478c14fd55698fbb2d2863cc"
NATIVE_SYSTEM = (
    "# HOW YOU SHOULD THINK AND ANSWER\n\n"
    "First draft your thinking process (inner monologue) until you arrive at a response. "
    "Format your response using Markdown, and use LaTeX for any mathematical equations. "
    "Write both your thoughts and the response in the same language as the input.\n\n"
    "Your thinking process must follow the template below:[THINK]Your thoughts or/and draft, "
    "like working through an exercise on scratch paper. Be as casual and as long as you want "
    "until you are confident to generate the response to the user.[/THINK]Here, provide a self-contained response."
)
FINAL_FORMAT = "After your [/THINK] boundary, return one JSON object, with no prose outside it."


def final_answer(raw):
    text = raw.strip()
    if not text.startswith("[THINK]") or text.count("[THINK]") != 1 or text.count("[/THINK]") != 1:
        raise ValueError("missing or malformed native thinking boundary")
    thought, answer = text[len("[THINK]"):].split("[/THINK]", 1)
    if not thought.strip() or not answer.strip():
        raise ValueError("empty native thinking block or final answer")
    return answer.strip()


def native_case(case):
    case = copy.deepcopy(case)
    original = case["messages"][0]["content"]
    suffix = "Return one JSON object, with no prose outside it."
    if not original.endswith(suffix):
        raise ValueError("unexpected fixture system format")
    # Scope JSON-only to the final answer, preserving the task and publisher setup.
    case["messages"][0]["content"] = original[:-len(suffix)].rstrip() + "\n\n" + NATIVE_SYSTEM + "\n\n" + FINAL_FORMAT
    return case


def cases():
    screen = []
    for actor in (2, 5):
        for sign in (-1, 1):
            for table in ("own", "all"):
                for encoding in ("boolean", "label"):
                    messages, schema, expected = choice_case(actor, sign, table, encoding)
                    screen.append(native_case(dict(name=f"actor{actor}-sign{sign}-{table}-{encoding}",
                        messages=messages, schema={k: t.__name__ for k, t in schema.items()}, expected=expected)))
    return screen, [native_case(c) for c in followup_cases()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    if args.model.name != REVISION or args.model.parent.parent.name != "models--mlx-community--Ministral-3-8B-Reasoning-2512-4bit":
        raise ValueError("requires the pinned Ministral reasoning snapshot")
    screen, fresh = cases()
    protocol = dict(name="ministral-native-reasoning-capability-v1", model=str(args.model), model_revision=REVISION,
        purpose="bounded capability discovery, not institutional evidence", screen_cases=screen, fresh_cases=fresh,
        temperature=0.7, top_p=1.0, top_k=0, min_p=0.0, max_tokens=2048,
        random_seed="42000 + fixed case index (screen 0..15; fresh 16..31), reset before each call",
        gate="16/16 exact screen actions AND payoff reports, then 16/16 exact fresh; any malformed/truncated answer fails",
        screen_calls=16, conditional_fresh_calls=16, max_calls=32,
        exclusions="none; no retries, repair, threshold changes, prompt changes or budget increases",
        reasoning="publisher native system appended to task; JSON-only instruction scoped to final answer after [/THINK]",
        inference="direct unbatched stream_generate, fresh KV each call, tokenizer fix_mistral_regex=True",
        limitations=["selected diagnostic fixtures; not general competence or negotiation validation",
            "different model, native prompt/template and sampling from prior Qwen; not a model-only causal comparison",
            "one seeded draw per fixture, not a reliability estimate; related fixtures are not independent tasks",
            "fresh cases were specified for Qwen but never run; reversed issue utilities and order vary jointly"],
        model_file_sha256={p: hashlib.sha256((args.model / p).read_bytes()).hexdigest()
            for p in ("config.json", "tokenizer_config.json", "chat_template.jinja", "generation_config.json")},
        runtime={p: importlib.metadata.version(p) for p in ("mlx", "mlx-lm", "transformers")})
    sources = [Path(__file__), ROOT / "paper3/audit_runtime.py", ROOT / "paper3/commitment_memory.py",
        ROOT / "experiments/paper3_minimal_choice_audit.py", ROOT / "experiments/paper3_qwen_reasoning_gate.py",
        ROOT / "analysis/paper3_pilot_audit.py"]
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler
    model, tokenizer = load(str(args.model), tokenizer_config={"fix_mistral_regex": True})

    def run(case, index, stage):
        name = case["name"]
        session_path = args.output / "sessions" / (name + ".json")
        if session_path.exists():
            return json.loads(session_path.read_text())
        request = dict(model=str(args.model), messages=case["messages"], temperature=0.7,
                       top_p=1.0, top_k=0, min_p=0.0, max_tokens=2048, seed=42000 + index)
        key = digest(dict(request=request, protocol=store.protocol_hash))
        call_path = args.output / "calls" / (key + ".json")
        if call_path.exists():
            record = json.loads(call_path.read_text())
        else:
            started = time.time()
            mx.random.seed(request["seed"])
            prompt = tokenizer.apply_chat_template(case["messages"], tokenize=True, add_generation_prompt=True)
            chunks, tokens = [], []
            for part in stream_generate(model, tokenizer, prompt=prompt, max_tokens=2048,
                    sampler=make_sampler(temp=0.7, top_p=1.0, top_k=0, min_p=0.0), prompt_cache=None):
                chunks.append(part.text)
                tokens.append(part.token)
            record = dict(request=request, origin="direct stream_generate; normalized actual output, not HTTP",
                response=dict(choices=[dict(message=dict(role="assistant", content="".join(chunks)), finish_reason=part.finish_reason)],
                    usage=dict(prompt_tokens=part.prompt_tokens, completion_tokens=part.generation_tokens)),
                prompt_token_ids=prompt, generated_token_ids=tokens, peak_memory_gb=part.peak_memory,
                started_unix=started, elapsed_seconds=time.time() - started, protocol_hash=store.protocol_hash)
            store.save("calls", key, record)
        result = dict(case=name, thinking=True, expected=case["expected"], stage=stage,
                      call_keys=[key], protocol_hash=store.protocol_hash)
        try:
            choice = record["response"]["choices"][0]
            if choice["finish_reason"] != "stop":
                raise ValueError("generation did not end normally")
            schema = {k: {"bool": bool, "str": str, "int": int}[v] for k, v in case["schema"].items()}
            reply = parse(final_answer(choice["message"]["content"]), schema)
            result.update(status="completed", reply=reply, exact=reply == case["expected"])
        except ValueError as exc:
            result.update(status="failed", error=str(exc), exact=False)
        store.save("sessions", name, result)
        print(stage, name, result["status"], result["exact"], flush=True)
        return result

    screened = [run(c, i, "screen") for i, c in enumerate(screen)]
    if not all(r["exact"] for r in screened):
        print("SCREEN GATE FAILED; conditional fresh cases NOT RUN", flush=True)
        return
    validated = [run(c, i + 16, "fresh") for i, c in enumerate(fresh)]
    print("FRESH GATE", sum(r["exact"] for r in validated), "/ 16; stop before collective experiments", flush=True)


if __name__ == "__main__":
    main()
