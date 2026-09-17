"""Recorded native-reasoning inference for prospectively frozen local studies."""
from __future__ import annotations

import json
import time

from paper3.audit_runtime import digest
from paper3.commitment_memory import parse


def final_answer(raw):
    """One unique closing boundary; opening-marker mentions may occur before it.

    No extraction from truncated output, multiple closing boundaries, prose after
    closure, or multiple final objects. The caller separately checks termination
    and the final schema. Earlier stricter gates are not rescored with this rule.
    """
    text = raw.strip()
    if not text.startswith("[THINK]") or text.count("[/THINK]") != 1:
        raise ValueError("missing or ambiguous native closing boundary")
    thought, answer = text[len("[THINK]"):].split("[/THINK]", 1)
    if not thought.replace("[THINK]", "").strip() or not answer.strip() or "[THINK]" in answer:
        raise ValueError("empty thinking/final output or thinking after closure")
    return answer.strip()


class NativeBackend:
    def __init__(self, path, store):
        from mlx_lm import load
        self.path, self.store = path, store
        self.model, self.tokenizer = load(str(path), tokenizer_config={"fix_mistral_regex": True})

    def call(self, messages, seed):
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler
        import mlx.core as mx
        request = dict(model=str(self.path), messages=messages, seed=seed,
                       temperature=0.7, top_p=1.0, top_k=0, min_p=0.0, max_tokens=2048)
        key = digest(dict(request=request, protocol=self.store.protocol_hash))
        path = self.store.root / "calls" / (key + ".json")
        if path.exists():
            return key, json.loads(path.read_text())
        started = time.time()
        mx.random.seed(seed)
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        chunks, tokens = [], []
        for part in stream_generate(self.model, self.tokenizer, prompt=prompt, max_tokens=2048,
                sampler=make_sampler(temp=0.7, top_p=1.0, top_k=0, min_p=0.0), prompt_cache=None):
            chunks.append(part.text)
            tokens.append(part.token)
        record = dict(request=request, origin="direct stream_generate; normalized actual output, not HTTP",
            response=dict(choices=[dict(message=dict(role="assistant", content="".join(chunks)), finish_reason=part.finish_reason)],
                usage=dict(prompt_tokens=part.prompt_tokens, completion_tokens=part.generation_tokens)),
            prompt_token_ids=prompt, generated_token_ids=tokens, peak_memory_gb=part.peak_memory,
            started_unix=started, elapsed_seconds=time.time() - started, protocol_hash=self.store.protocol_hash)
        self.store.save("calls", key, record)
        return key, record

    def run_case(self, case, seed, stage):
        path = self.store.root / "sessions" / (case["name"] + ".json")
        if path.exists():
            return json.loads(path.read_text())
        key, record = self.call(case["messages"], seed)
        result = dict(case=case["name"], thinking=True, expected=case["expected"], stage=stage,
                      call_keys=[key], protocol_hash=self.store.protocol_hash)
        try:
            choice = record["response"]["choices"][0]
            if choice["finish_reason"] != "stop":
                raise ValueError("generation did not end normally")
            schema = {k: {"bool": bool, "str": str, "int": int}[v] for k, v in case["schema"].items()}
            reply = parse(final_answer(choice["message"]["content"]), schema)
            result.update(status="completed", reply=reply, exact=reply == case["expected"],
                          field_errors=[k for k in schema if reply[k] != case["expected"][k]])
        except ValueError as exc:
            result.update(status="failed", error=str(exc), exact=False)
        self.store.save("sessions", case["name"], result)
        print(stage, case["name"], result["status"], result["exact"], flush=True)
        return result
