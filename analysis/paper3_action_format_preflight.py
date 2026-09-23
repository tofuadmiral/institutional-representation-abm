"""No-model component checks for a possible future structured action channel.

Uses the installed tokenizer, grammar masks and thinking controller with synthetic
tokens/zero logits. Never loads weights, calls a model, changes the old run, or
certifies full stream-generation integration. Run in the pinned Bonsai runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import itertools
import json
from pathlib import Path


def object_schema(properties):
    return dict(type="object", properties=properties, required=list(properties),
                additionalProperties=False)


def fixtures():
    policy = dict(type="string", enum=["p3", "p6"])
    return {
        "pairwise": (object_schema(dict(policy_id=policy)),
            [dict(policy_id=p) for p in ("p3", "p6")],
            ['p3', '"p3"', '{"policy_id": "p9"}', '{"policy_id": true}']),
        "single_pairwise": (object_schema(dict(policy_id=dict(type="string", enum=["p7"]))),
            [dict(policy_id="p7")],
            ['p7', '{"policy_id": "p3"}', '{"policy_id": "p7", "extra": true}']),
        "ratification": (object_schema(dict(votes=object_schema(
            {p: dict(type="boolean") for p in ("p3", "p6")}))),
            [dict(votes=dict(zip(("p3", "p6"), bits)))
             for bits in itertools.product((False, True), repeat=2)],
            ['{"p3": true, "p6": false}', '{"votes": {"p3": true}}',
             '{"votes": {"p3": 1, "p6": false}}']),
        "single_ratification": (object_schema(dict(votes=object_schema(
            dict(p7=dict(type="boolean"))))),
            [dict(votes=dict(p7=b)) for b in (False, True)],
            ['{"p7": true}', '{"votes": {"p7": "true"}}']),
        "public": (object_schema(dict(policy_id=policy, message=dict(type="string"))),
            [dict(policy_id=p, message="Test message.") for p in ("p3", "p6")],
            ['{"policy_id": "p3"}', '{"policy_id": "p3", "message": false}']),
        "selector_gate": (object_schema(dict(
            selected_policy=dict(type="string", enum=["policy_k", "policy_m"]),
            votes=object_schema({p: dict(type="boolean") for p in ("policy_k", "policy_m")}))),
            [dict(selected_policy=p, votes=dict(zip(("policy_k", "policy_m"), bits)))
             for p in ("policy_k", "policy_m")
             for bits in itertools.product((False, True), repeat=2)],
            ['{"selected_policy": "policy_k"}',
             '{"selected_policy": "invalid", "votes": {"policy_k": true, "policy_m": false}}',
             '{"selected_policy": "policy_k", "votes": {"policy_k": 1, "policy_m": false}}']),
    }


def preflight(manifest_path):
    import mlx.core as mx
    from transformers import AutoTokenizer
    from mlx_vlm.structured import (
        ThinkingAwareLogitsProcessor, build_json_schema_logits_processor,
    )
    from mlx_vlm.utils import ThinkingBudgetCriteria

    protocol = json.loads(manifest_path.read_text())["protocol"]
    model = Path(protocol["model"])
    tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
    config = json.loads((model / "config.json").read_text())
    logits = mx.zeros((1, config["text_config"]["vocab_size"]))
    start, end, newline, ordinary = [tokenizer.encode(s, add_special_tokens=False)[-1]
                                   for s in ("<think>", "</think>", "\n", "word")]
    budget = protocol["inference"]["thinking_budget"]

    def new_wrapper(schema):
        return ThinkingAwareLogitsProcessor(
            build_json_schema_logits_processor(tokenizer, schema), tokenizer,
            enable_thinking=True)

    def reasoning_prefix(wrapper, forced):
        prefix = [start, newline]
        assert wrapper(mx.array(prefix), logits) is logits
        controller = ThinkingBudgetCriteria(tokenizer, budget,
            thinking_start_token="<think>", thinking_end_token="</think>",
            enable_thinking=True)
        for _ in range(budget + 1 if forced else 3):
            prefix.append(ordinary)
            assert wrapper(mx.array(prefix), logits) is logits
            controller(ordinary)
            next_token = int(controller.apply_forced_token(mx.array([ordinary])).item())
            if not forced:
                assert next_token == ordinary
        if forced:
            assert next_token == newline
            prefix.append(newline)
            assert wrapper(mx.array(prefix), logits) is logits
            controller(newline)
            assert int(controller.apply_forced_token(mx.array([ordinary])).item()) == end
        prefix.append(end)
        controller(end)
        assert not controller.in_thinking
        assert int(controller.apply_forced_token(mx.array([ordinary])).item()) == ordinary
        return prefix

    def accepts(wrapper, prefix, text):
        # Teacher-force a candidate token path through real masks; no sampling
        # or language-model computation occurs. Check EOS only on complete JSON.
        targets = tokenizer.encode(text, add_special_tokens=False) + [tokenizer.eos_token_id]
        for i, token in enumerate(targets):
            masked = wrapper(mx.array(prefix), logits)
            if i == 0:
                assert bool(mx.any(mx.isinf(masked)).item())
                assert bool(mx.any(mx.isfinite(masked)).item())
            if not bool(mx.isfinite(masked[0, token]).item()):
                return False
            prefix.append(token)
        return True

    results = {}
    for name, (schema, legal, invalid) in fixtures().items():
        for forced in (False, True):
            for answer in legal:
                wrapper = new_wrapper(schema)
                assert accepts(wrapper, reasoning_prefix(wrapper, forced), json.dumps(answer)), (name, forced, answer)
        for text in invalid:
            wrapper = new_wrapper(schema)
            assert not accepts(wrapper, reasoning_prefix(wrapper, False), text), (name, text)
        wrapper = new_wrapper(schema)
        assert accepts(wrapper, reasoning_prefix(wrapper, False), json.dumps(legal[0]))
        wrapper.reset()
        assert accepts(wrapper, reasoning_prefix(wrapper, True), json.dumps(legal[-1]))
        clone = wrapper.clone()
        assert accepts(clone, reasoning_prefix(clone, False), json.dumps(legal[0]))
        results[name] = dict(legal_paths_per_closure=len(legal), malformed_paths_rejected=len(invalid),
                             natural_closure=True, forced_closure=True, reset=True, clone=True)
    sources = [Path(__file__).resolve(), Path(inspect.getfile(ThinkingAwareLogitsProcessor)),
               Path(inspect.getfile(ThinkingBudgetCriteria))]
    return dict(no_model_calls=True, weights_loaded=False,
        scope="synthetic-token component check; not live stream integration or model competence",
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        tokenizer_sha256=hashlib.sha256((model / "tokenizer.json").read_bytes()).hexdigest(),
        versions={p: importlib.metadata.version(p) for p in ("mlx", "mlx-vlm", "llguidance", "transformers")},
        source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        thinking_budget=budget, results=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(preflight(args.manifest), indent=2))
