"""Bounded reasoning-policy feasibility: four private checks, one actual episode.

The deadline changes inference policy, not institutional rules. Never repairs an
answer or fabricates an action. Earlier spontaneous-closure studies stay frozen.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.paper3_bonsai_low_effort import prepare as verify_parent, LOW_INSTRUCTION
from experiments.paper3_bonsai_validation import BonsaiBackend, append_generated_token, final_answer
from paper3.audit_runtime import PilotStore, digest
from paper3.commitment_memory import profile, parse, negotiate, first_vote, second_vote
from paper3.grounded_interface import GroundedInterface, authorization_case

CAP, THINKING, MAX_CALLS, MAX_INPUT, MAX_MESSAGE = 1536, 1024, 34, 8192, 400
FINAL = "After your native thinking block, return one JSON object, with no prose outside it."


def fixtures():
    # Selected before inference; balanced actions, not selected model outcomes.
    cases = []
    for index, (seed, actor, package) in enumerate(((1201, 0, 0), (1201, 6, 1),
                                                  (1213, 6, 0), (1213, 3, 2))):
        p = profile(seed)
        messages, expected = authorization_case(p, actor, package, False)
        messages[0]["content"] = messages[0]["content"].replace(
            "Return one JSON object, with no prose outside it.", FINAL)
        cases.append(dict(name=f"private-{index}", profile=asdict(p), actor=actor,
            package=package, seed=112000 + index, messages=messages, expected=expected))
    p = replace(profile(1103), formateur=0, key="seed1103-leader0")
    return cases, p


def request_for(model, messages, seed):
    return dict(model=str(model), messages=messages, seed=seed, max_tokens=CAP,
        thinking_budget=THINKING, thinking_start_token="<think>", thinking_end_token="</think>",
        temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0,
        repetition_penalty=1.0, enable_thinking=True, reasoning_effort="low", prefill_step_size=512)


def render(tokenizer, base, messages):
    kw = dict(tokenize=False, add_generation_prompt=True, enable_thinking=True)
    medium = tokenizer.apply_chat_template(messages, reasoning_effort="medium", **kw)
    low = tokenizer.apply_chat_template(messages, reasoning_effort="low", **kw)
    prefix = "<|im_start|>system\n"
    if not medium.startswith(prefix) or low != prefix + LOW_INSTRUCTION + medium[len(prefix):]:
        raise ValueError("unexpected low-effort template")
    ids = tokenizer.encode(low, add_special_tokens=True)
    if not low.endswith("<think>\n") or ids != base.encode(low, add_special_tokens=True) or len(ids) > MAX_INPUT:
        raise ValueError("native prefill, base tokenization or input-cap failure")
    return low, ids


class BoundaryRecorder:
    """Observe the real controller before the suspended stream applies overrides.

    Scheduled overrides target the NEXT output position. A schedule at the final
    cap is not an emitted forced token. Terminal length chunks repeat a token.
    """
    def __init__(self):
        self.tokens, self.schedules = [], []

    def observe(self, part, controller):
        previous = len(self.tokens)
        append_generated_token(self.tokens, part)
        if len(self.tokens) == previous:
            return
        if controller is None or not controller.enable_thinking or controller.thinking_budget != THINKING:
            raise ValueError("missing or changed live thinking controller")
        if part.finish_reason is None and controller.forced_token_id is not None:
            self.schedules.append(dict(position=len(self.tokens), token_id=int(controller.forced_token_id),
                                       counter=controller.thinking_token_count))

    def summary(self, closing_id):
        forced = [s for s in self.schedules if s["position"] < len(self.tokens)]
        if any(self.tokens[s["position"]] != s["token_id"] for s in forced):
            raise ValueError("scheduled controller token not emitted at expected position")
        closes = [i for i, t in enumerate(self.tokens) if t == closing_id]
        return dict(schedules=self.schedules, emitted_forced_tokens=forced,
            sampled_output_tokens=len(self.tokens) - len(forced), forced_output_tokens=len(forced),
            closing_positions=closes, closure_origin=("forced" if any(s["position"] in closes for s in forced)
                else "natural" if closes else "absent"),
            tokens_after_first_close=len(self.tokens) - closes[0] - 1 if closes else 0)


def checked_answer(record):
    if record.get("generation_error"):
        raise ValueError("generation error: " + record["generation_error"])
    choice, usage = record["response"]["choices"][0], record["response"]["usage"]
    boundary = record["boundary"]
    if (record["cached_tokens"] != 0 or len(record["prompt_token_ids"]) != usage["prompt_tokens"]
            or len(record["generated_token_ids"]) != usage["completion_tokens"]
            or usage["completion_tokens"] > CAP
            or boundary["sampled_output_tokens"] + boundary["forced_output_tokens"] != usage["completion_tokens"]):
        raise ValueError("token/cache/controller accounting mismatch")
    if choice["finish_reason"] != "stop":
        raise ValueError("non-normal generation termination")
    raw = choice["message"]["content"]
    if "<think>" in raw:
        raise ValueError("repeated or reopened native reasoning marker")
    return final_answer(raw)


class BudgetBackend(BonsaiBackend):
    def call(self, messages, seed, base):
        import mlx.core as mx
        from mlx_vlm import stream_generate
        request = request_for(self.path, messages, seed)
        key = digest(dict(request=request, protocol=self.store.protocol_hash))
        path = self.store.root / "calls" / (key + ".json")
        if path.exists():
            saved = json.loads(path.read_text())
            if saved.get("status") == "started":
                raise ValueError("interrupted call is not retried")
            return key, saved
        if len(list((self.store.root / "calls").glob("*.json"))) >= MAX_CALLS:
            raise ValueError("frozen call limit reached")
        tokenizer = self.processor.tokenizer
        prompt, ids = render(tokenizer, base, messages)
        record = dict(request=request, rendered_prompt=prompt, prompt_token_ids=ids,
                      protocol_hash=self.store.protocol_hash, status="started", started_unix=time.time())
        self.store.save("calls", key, record)  # Crash marker prevents silent retries.
        mx.random.seed(seed)
        boundary, chunks, last = BoundaryRecorder(), [], None
        generation = {k: v for k, v in request.items() if k not in ("model", "messages", "seed", "reasoning_effort")}
        previous_controller = getattr(tokenizer, "thinking_budget_criteria", None)
        try:
            for part in stream_generate(self.model, self.processor, prompt=prompt, skip_special_tokens=False, **generation):
                last = part
                chunks.append(part.text)
                controller = getattr(tokenizer, "thinking_budget_criteria", None)
                if controller is previous_controller:
                    raise ValueError("controller was not freshly constructed for this request")
                boundary.observe(part, controller)
            if last is None:
                raise ValueError("empty generation stream")
        except Exception as exc:
            record["generation_error"] = type(exc).__name__ + ": " + str(exc)
        try:
            summary = boundary.summary(tokenizer.encode("</think>", add_special_tokens=False)[-1])
        except ValueError as exc:
            record["generation_error"] = str(exc)
            summary = dict(schedules=boundary.schedules, accounting_error=str(exc))
        record.update(status="recorded", generated_token_ids=boundary.tokens, boundary=summary,
            response=dict(choices=[dict(message=dict(role="assistant", content="".join(chunks)),
                finish_reason=getattr(last, "finish_reason", "error"))], usage=dict(
                prompt_tokens=getattr(last, "prompt_tokens", len(ids)),
                completion_tokens=getattr(last, "generation_tokens", len(boundary.tokens)))),
            cached_tokens=getattr(last, "cached_tokens", None), peak_memory_gb=getattr(last, "peak_memory", None),
            elapsed_seconds=time.time() - record["started_unix"],
            origin="publisher rotation-aware loader; installed MLX-VLM forced phase deadline; no action repair")
        self.store.save("calls", key, record)
        print("CALL", seed, len(boundary.tokens), summary.get("closure_origin"),
              record["response"]["choices"][0]["finish_reason"], flush=True)
        return key, record


def collective_messages(messages):
    messages = copy.deepcopy(messages)
    messages[0]["content"] = messages[0]["content"].replace("You may reason internally; output JSON only.", "") + "\n" + FINAL
    encoded, task = messages[-1]["content"].split("\n", 1)
    if "message (string)" in task:
        task += f" Your public message must contain at most {MAX_MESSAGE} characters."
    messages[-1]["content"] = json.dumps(json.loads(encoded), sort_keys=True) + "\n" + task
    return messages


class EpisodeBackend:
    def __init__(self, native, base):
        self.native, self.base = native, base
        self.call_keys, self.pending_request = [], None

    def generate(self, messages, **kwargs):
        self.pending_request = collective_messages(messages)
        if len(self.call_keys) >= 30:
            raise ValueError("episode decision cap reached")
        key, record = self.native.call(self.pending_request, 113000 + len(self.call_keys), self.base)
        self.call_keys.append(key)
        self.pending_request = None
        answer = checked_answer(record)
        normalized = answer.strip()
        if normalized.startswith("```") and normalized.endswith("```"):
            normalized = normalized.split("\n", 1)[1].rsplit("```", 1)[0]
        value = json.loads(normalized)
        if isinstance(value, dict) and isinstance(value.get("message"), str) and len(value["message"]) > MAX_MESSAGE:
            raise ValueError("public message exceeds frozen limit")
        return answer


def private_score(record, case):
    try:
        reply = parse(checked_answer(record), dict(accept=bool, principal_utility_if_accepted=int))
        return dict(status="completed", reply=reply, exact=reply == case["expected"],
                    action_correct=reply["accept"] == case["expected"]["accept"])
    except ValueError as exc:
        return dict(status="failed", exact=False, action_correct=False, error=str(exc))


def run_episode(direct, p):
    backend = GroundedInterface(direct)
    history = []
    try:
        history = negotiate(backend, p)
        history = first_vote(backend, p, history)
        result = second_vote(backend, p, history, ledger=False, release=False)
        if len(direct.call_keys) != 30:
            raise ValueError("completed episode did not contain 30 decisions")
        result["status"] = "completed"
    except (ValueError, OSError, TimeoutError) as exc:
        result = dict(status="failed", error=str(exc), completed_phase_history=history,
                      unsubmitted_request=direct.pending_request)
    return dict(result, profile=asdict(p), call_keys=list(direct.call_keys))


def prepare(parent):
    old, sources, _ = verify_parent(parent)
    cases, p = fixtures()
    runtime_root = Path(sys.prefix) / "lib/python3.13/site-packages/mlx_vlm"
    runtime_files = {str(runtime_root / f): hashlib.sha256((runtime_root / f).read_bytes()).hexdigest()
                     for f in ("utils.py", "generate/dispatch.py", "generate/ar.py")}
    protocol = dict(name="bonsai-budgeted-episode-feasibility-v1", model=old["model"],
        model_revision=old["model_revision"], model_file_sha256=old["model_file_sha256"],
        base_tokenizer=old["base_tokenizer"], base_file_hashes=old["base_file_hashes"],
        runtime=old["runtime"], runtime_source_sha256=runtime_files,
        parent_manifest_hash=old["parent_manifest_hash"], private_cases=cases, profile=asdict(p),
        inference=request_for(old["model"], [], 0), episode_seed_start=113000,
        max_calls=MAX_CALLS, max_output_tokens=MAX_CALLS * CAP,
        max_input_tokens=MAX_INPUT, max_message_characters=MAX_MESSAGE,
        gate="complete four private choices; all four normal, strict schema, correct action AND exact payoff before episode",
        primary="one complete 30-decision transcript-only episode with no repairs, retries, fallbacks or substituted votes",
        secondary="actual offers, signatures, votes, obligation errors, due breaches, principal/outsider payoffs, tokens/time/memory",
        controller="installed nominal 1024 thinking counter, forced newline + closing marker; ordinary closure after 1027 output tokens; total cap 1536 includes forced tokens",
        caveats=["repeated opening markers can evade controller counter; total cap still applies; repeated markers fail parsing",
            "forced closure is not spontaneous model reasoning termination; record every scheduled and emitted override",
            "single adaptive feasibility episode, no causal institutional contrast or reliability estimate",
            "no-deal, no passage and welfare losses are outcomes, not exclusion criteria",
            "four private cases do not prove general competence; old failures remain failures",
            "no registry, release, elections, extra profiles or automatic confirmatory expansion"],
        interruption="persist started-call marker; interrupted calls are not regenerated")
    sources = sorted(set(sources + [Path(__file__).resolve()]))
    return json.loads(json.dumps(protocol)), sources


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    protocol, sources = prepare(args.parent)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(protocol["model"], local_files_only=True)
    base = AutoTokenizer.from_pretrained(protocol["base_tokenizer"], local_files_only=True)
    cases, p = fixtures()
    for case in cases:
        render(tokenizer, base, case["messages"])
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    if (args.output / "sessions/episode.json").exists():
        print("Already terminal; no new inference", flush=True)
        return
    native = BudgetBackend(Path(protocol["model"]), store)
    results = []
    for case in cases:
        path = args.output / "sessions" / (case["name"] + ".json")
        if path.exists():
            result = json.loads(path.read_text())
        else:
            key, record = native.call(case["messages"], case["seed"], base)
            result = dict(private_score(record, case), case=case["name"], expected=case["expected"],
                          call_keys=[key], protocol_hash=store.protocol_hash)
            store.save("sessions", case["name"], result)
        results.append(result)
        print(case["name"], result["status"], result["exact"], flush=True)
    if all(r["exact"] for r in results):
        result = run_episode(EpisodeBackend(native, base), p)
    else:
        result = dict(status="not_run", reason="private exact gate failed", call_keys=[])
    store.save("sessions", "episode", dict(result, protocol_hash=store.protocol_hash))
    print("TERMINAL", result["status"], result.get("error"), "No automatic follow-on", flush=True)


if __name__ == "__main__":
    main()
