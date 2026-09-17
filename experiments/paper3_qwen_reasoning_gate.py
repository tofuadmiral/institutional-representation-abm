"""Frozen paired reasoning-mode capability check; no collective experiment."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import PilotStore, digest
from paper3.commitment_memory import parse
from experiments.paper3_minimal_choice_audit import choice_case


def final_answer(raw, thinking):
    """Accept one native Qwen thinking block, never salvage truncated JSON."""
    text = raw.strip()
    if thinking:
        if not text.startswith("<think>") or text.count("</think>") != 1 or text.count("<think>") != 1:
            raise ValueError("missing or malformed native thinking boundary")
        return text.split("</think>", 1)[1].strip()
    if "<think>" in text or "</think>" in text:
        raise ValueError("unexpected thinking output in disabled arm")
    return text


def followup_cases():
    """Unrun signed payoff profiles and issue-order checks, fixed prospectively."""
    cases = []
    for seed in (101, 202):
        for actor in (1, 4):
            rng = random.Random(seed + actor)
            magnitude, offset = rng.randint(4, 9), rng.randint(1, 3)
            for sign in (-1, 1):
                for reverse in (False, True):
                    messages, schema, _ = choice_case(2, 1, "all", "label")
                    messages[0]["content"] = messages[0]["content"].replace("representative 2", f"representative {actor}").replace("principal 2", f"principal {actor}")
                    encoded, task = messages[1]["content"].split("\n", 1)
                    record = json.loads(encoded)
                    record["principal_id"] = actor
                    record["utilities_by_principal"] = {
                        str(i): {"A0": i + 2, "B0": -(i + 3)} for i in range(7)}
                    terms = [sign * (magnitude + offset), -sign * offset]
                    if reverse:
                        terms.reverse()
                        record["offered_projects"].reverse()
                    record["utilities_by_principal"][str(actor)] = dict(zip(("A0", "B0"), terms))
                    messages[1]["content"] = json.dumps(record, sort_keys=True) + "\n" + task
                    expected = dict(action="accept" if sign > 0 else "decline",
                                    principal_utility_if_accepted=sign * magnitude)
                    cases.append(dict(name=f"fresh-seed{seed}-actor{actor}-sign{sign}-reverse{int(reverse)}",
                                      messages=messages, schema={k: t.__name__ for k, t in schema.items()},
                                      expected=expected))
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.model.name != "545dc4251c05440727734bcd94334791f6ab0192":
        raise ValueError("this gate requires the pinned existing Qwen snapshot")
    paired = []
    for actor in (2, 5):
        for sign in (-1, 1):
            for table in ("own", "all"):
                for encoding in ("boolean", "label"):
                    messages, schema, expected = choice_case(actor, sign, table, encoding)
                    paired.append(dict(name=f"actor{actor}-sign{sign}-{table}-{encoding}", messages=messages,
                                       schema={k: t.__name__ for k, t in schema.items()}, expected=expected))
    fresh = followup_cases()
    protocol = dict(name="qwen-paired-reasoning-capability-v1", purpose="capability discovery, not institutional evidence",
                    model=str(args.model), model_revision=args.model.name, paired_cases=paired, fresh_cases=fresh,
                    temperature=0, max_tokens=2048, paired_calls=32, conditional_fresh_calls=16, max_calls=48,
                    gate="thinking enabled: 16/16 paired exact then 16/16 fresh exact; any truncation or parse failure fails",
                    order="alternate which thinking mode runs first across cases; fresh only after paired enabled gate passes",
                    exclusions="none; no model retries, JSON repairs, threshold changes or budget increases",
                    inference="direct unbatched mlx_lm.stream_generate, fresh KV each call, one loaded model, no HTTP server",
                    limitations=["greedy decoding in both modes; not a general model capability estimate",
                                 "mode changes native template; equal output cap is not equal realized compute",
                                 "does not replace original 24-case authorization gate or validate negotiation"],
                    tokenizer_sha256=hashlib.sha256((args.model / "tokenizer_config.json").read_bytes()).hexdigest(),
                    runtime={p: importlib.metadata.version(p) for p in ("mlx", "mlx-lm", "transformers")})
    sources = [Path(__file__), ROOT / "paper3/audit_runtime.py", ROOT / "paper3/commitment_memory.py",
               ROOT / "experiments/paper3_minimal_choice_audit.py"]
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler
    model, tokenizer = load(str(args.model))

    def run(case, thinking):
        name = case["name"] + f"-thinking{int(thinking)}"
        session_path = args.output / "sessions" / (name + ".json")
        if session_path.exists():
            return json.loads(session_path.read_text())
        request = dict(model=str(args.model), messages=case["messages"], temperature=0,
                       max_tokens=2048, chat_template_kwargs=dict(enable_thinking=thinking))
        key = digest(dict(request=request, protocol=store.protocol_hash))
        call_path = args.output / "calls" / (key + ".json")
        if call_path.exists():
            record = json.loads(call_path.read_text())
        else:
            started = time.time()
            prompt = tokenizer.apply_chat_template(case["messages"], tokenize=True,
                                                   add_generation_prompt=True, enable_thinking=thinking)
            chunks, tokens = [], []
            for part in stream_generate(model, tokenizer, prompt=prompt, max_tokens=2048,
                                        sampler=make_sampler(temp=0), prompt_cache=None):
                chunks.append(part.text)
                tokens.append(part.token)
            record = dict(request=request, origin="direct stream_generate; normalized actual output, not HTTP",
                          response=dict(choices=[dict(message=dict(role="assistant", content="".join(chunks)),
                                                      finish_reason=part.finish_reason)],
                                        usage=dict(prompt_tokens=part.prompt_tokens, completion_tokens=part.generation_tokens)),
                          prompt_token_ids=prompt, generated_token_ids=tokens,
                          started_unix=started, elapsed_seconds=time.time() - started, protocol_hash=store.protocol_hash)
            store.save("calls", key, record)
        result = dict(case=case["name"], thinking=thinking, expected=case["expected"],
                      stage="fresh" if case["name"].startswith("fresh-") else "paired",
                      call_keys=[key], protocol_hash=store.protocol_hash)
        try:
            choice = record["response"]["choices"][0]
            if choice["finish_reason"] != "stop":
                raise ValueError("generation did not end normally")
            schema = {k: {"bool": bool, "str": str, "int": int}[v] for k, v in case["schema"].items()}
            reply = parse(final_answer(choice["message"]["content"], thinking), schema)
            result.update(status="completed", reply=reply, exact=reply == case["expected"])
        except ValueError as exc:
            result.update(status="failed", error=str(exc), exact=False)
        store.save("sessions", name, result)
        print(name, result["status"], result["exact"], flush=True)
        return result

    enabled = []
    for i, case in enumerate(paired):
        for thinking in ((False, True) if i % 2 == 0 else (True, False)):
            result = run(case, thinking)
            if thinking:
                enabled.append(result)
    if not all(r["exact"] for r in enabled):
        print("PAIRED ENABLED GATE FAILED; fresh follow-up not run", flush=True)
        return
    validated = [run(case, True) for case in fresh]
    print("FRESH GATE", sum(r["exact"] for r in validated), "/ 16", flush=True)


if __name__ == "__main__":
    main()
