"""Actual native decode loop with a deterministic synthetic logits source, no LLM."""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
from experiments.paper3_bonsai_format_gate import ObservedGrammar, schema_for
from paper3_format_gate_audit import verify_trace


def check(manifest):
    import mlx.core as mx
    from transformers import AutoTokenizer
    from mlx_vlm.generate.ar import generate_step
    from mlx_vlm.structured import ThinkingAwareLogitsProcessor, build_json_schema_logits_processor
    from mlx_vlm.utils import ThinkingBudgetCriteria
    protocol = json.loads(manifest.read_text())["protocol"]
    tokenizer = AutoTokenizer.from_pretrained(protocol["model"], local_files_only=True)
    config = json.loads((Path(protocol["model"]) / "config.json").read_text())
    vocab = mx.arange(config["text_config"]["vocab_size"])
    start, close, newline, ordinary = [tokenizer.encode(s, add_special_tokens=False)[-1]
        for s in ("<think>", "</think>", "\n", "word")]
    results = []
    for forced in (False, True):
        answer = dict(policy_id="policy_m")
        schema = schema_for("pairwise", ["policy_k", "policy_m"])
        budget = protocol["inference"]["thinking_budget"]
        reasoning = [ordinary] * (budget+1 if forced else 3)
        if forced:
            reasoning.append(newline)
        scripted = reasoning + [close] + tokenizer.encode(json.dumps(answer), add_special_tokens=False) + [tokenizer.eos_token_id]

        class Synthetic:
            def __init__(self):
                self.language_model, self.index = self, 0
            def get_input_embeddings(self, input_ids, pixel_values, **kw):
                embed = mx.zeros((1, input_ids.size, 1))
                return SimpleNamespace(inputs_embeds=embed, to_dict=lambda:dict(inputs_embeds=embed))
            def __call__(self, *args, **kwargs):
                # At the two scheduled override positions deliberately prefer
                # ordinary text, so only the real deadline inserts the closure.
                target = scripted[min(self.index, len(scripted)-1)]
                if forced and self.index in (budget+1, budget+2):
                    target = ordinary
                self.index += 1
                return SimpleNamespace(logits=mx.where(vocab == target, 0.0, -float("inf"))[None,None,:],
                    cross_attention_states=None, encoder_outputs=None)

        wrapper = ObservedGrammar(ThinkingAwareLogitsProcessor(
            build_json_schema_logits_processor(tokenizer, schema), tokenizer, enable_thinking=True))
        controller = ThinkingBudgetCriteria(tokenizer, budget, thinking_start_token="<think>",
            thinking_end_token="</think>", enable_thinking=True)
        emitted, forced_positions = [], []
        iterator = generate_step(mx.array([[start,newline]]), Synthetic(), None, None,
            max_tokens=1536, temperature=0, prompt_cache=[], prefill_step_size=None,
            logits_processors=[wrapper], thinking_budget_criteria=controller)
        for token, _ in iterator:
            emitted.append(token)
            next_forced = controller(token)
            if next_forced is not None:
                forced_positions.append(dict(position=len(emitted), token=next_forced))
            if token == tokenizer.eos_token_id:
                break
        iterator.close()
        assert emitted == scripted
        assert len(forced_positions) == (2 if forced else 0)
        verify_trace(dict(prompt_token_ids=[start,newline], generated_token_ids=emitted,
                          grammar_trace=wrapper.events), close)
        results.append(dict(forced=forced, output_tokens=len(emitted), trace_events=len(wrapper.events),
            exact_script=True, forced_positions=forced_positions))
    return dict(no_llm=True, no_weights=True, scope="synthetic native generate_step only, not full publisher-model integration", results=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    print(json.dumps(check(parser.parse_args().manifest), indent=2))
