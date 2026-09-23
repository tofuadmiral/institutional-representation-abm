"""Approved 8 + conditional 100-call Bonsai agenda-rights discovery pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import paper3_bonsai_budgeted_episode as old
from experiments.paper3_bonsai_budgeted_episode import (
    request_for, render, BoundaryRecorder, CAP, THINKING, MAX_INPUT, checked_answer,
)
from experiments.paper3_bonsai_validation import BonsaiBackend
from paper3.audit_runtime import PilotStore, digest
from paper3 import agenda_rights as game

NAME = "bonsai-agenda-rights-discovery-v1"
MAX_CALLS = 108


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
                raise RuntimeError("interrupted call is not retried")
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


def specifications():
    conflict, control = game.profiles()
    return [dict(name="conflict39-D", profile=conflict, arm="D", seed=151000),
            dict(name="common_interest-B", profile=control, arm="B", seed=152000),
            dict(name="conflict39-B", profile=conflict, arm="B", seed=151000),
            dict(name="common_interest-D", profile=control, arm="D", seed=152000)]


def score_gate(record, case):
    try:
        return game.gate_score(checked_answer(record), case["expected"])
    except (ValueError, KeyError) as exc:
        return dict(status="failed", exact=False, error=str(exc))


def run_one(native, base, spec):
    keys, pending = [], None
    def ask(messages):
        nonlocal pending
        if len(keys) >= 25:
            raise RuntimeError("episode call cap exceeded")
        pending = dict(messages=messages, seed=spec["seed"] + len(keys))
        key, record = native.call(messages, pending["seed"], base)
        keys.append(key)
        pending = None
        return checked_answer(record)
    result = game.run_episode(spec["profile"], spec["arm"], ask)
    return dict(result, name=spec["name"], profile=spec["profile"], arm=spec["arm"],
                call_keys=keys, unsubmitted_request=pending)


def prepare():
    parent, sources = old.prepare(ROOT / "results/paper3/bonsai_negotiated_memory_a2")
    protocol = {k: parent[k] for k in ("model", "model_revision", "model_file_sha256",
        "base_tokenizer", "base_file_hashes", "runtime", "runtime_source_sha256", "controller")}
    protocol.update(name=NAME, cases=game.gate_cases(), episodes=specifications(),
        inference=request_for(parent["model"], [], 0), max_calls=MAX_CALLS,
        max_output_tokens=MAX_CALLS * CAP, max_input_tokens=MAX_INPUT,
        authorization="Fuad: Yes approved, following the 108-call agenda/amendment design and analytical preflight.",
        design="two selected synthetic profiles x two known authority rules; 25 decisions per episode; matched proposals, separate endogenous histories",
        gate="all eight private selector/conditional-ratification checks exact before any episode; complete all eight even if one fails",
        primary_behavior="locked-proposal leader advantage; opening proposal is secondary",
        primary_representation="mean normalized finite-menu regret of enacted policy",
        secondary="all principal utilities and losses, L2, actual passage, amendment use, sealed ballot consistency, descriptive fixed-output replay, failures and costs",
        no_amendment="retaining locked proposal is legitimate; anticipatory adaptation does not require an exercised amendment",
        simultaneous="responses, pairwise ballots and ratification cards withheld from same-stage peers until all seven finish",
        control="common-interest ranking, not a guarantee of identical LLM outputs",
        selection="conflict39 selected from no-model geometric screen for viable sponsor-beneficial challenge and scripted adaptation; common-interest fixture constructed; discovery only",
        failure_policy="strict action schemas; invalid call ends that episode without a fabricated policy; continue other prespecified episodes; no repairs/retries; message >400 chars retained and reported",
        interruption="started markers prohibit regeneration; interrupted native call stops run for inspection",
        flat_preferences="fixtures exclude any flat finite-menu utility row",
        ties="analysis sincere ratification rejects utility zero; sincere pairwise retains locked proposal on equal continuation utility; observed indifferent votes are not errors",
        caveats=["two profiles, not independent agents or votes; no significance or publication claims",
                 "Qwen-derived Bonsai is not independent-family replication",
                 "unused conditional ballot may be unreliable; replay is descriptive, not causal mediation",
                 "matched maximum budgets, not identical realized tokens; native reasoning may be forcibly closed",
                 "no election, new model, further batch or confirmation follows automatically"])
    sources = sorted(set(sources + [Path(__file__).resolve(), ROOT / "paper3/agenda_rights.py",
        ROOT / "analysis/paper3_agenda_audit.py", ROOT / "analysis/paper3_budgeted_episode_audit.py",
        ROOT / "tests/test_paper3_agenda_rights.py", ROOT / "tests/test_paper3_bonsai_budgeted_episode.py",
        ROOT / "tests/test_paper3_bonsai_low_effort.py"]))
    return json.loads(json.dumps(protocol)), sources


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    protocol, sources = prepare()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(protocol["model"], local_files_only=True)
    base = AutoTokenizer.from_pretrained(protocol["base_tokenizer"], local_files_only=True)
    for case in protocol["cases"]:
        render(tokenizer, base, case["messages"])
    for spec in protocol["episodes"]:
        render(tokenizer, base, game.messages(spec["profile"], spec["arm"], spec["profile"]["leader"], "opening", []))
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    if (args.output / "sessions/terminal.json").exists():
        print("Already terminal; no inference", flush=True)
        return
    for path in (args.output / "calls").glob("*.json"):
        if json.loads(path.read_text()).get("status") == "started":
            raise RuntimeError("interrupted call requires inspection; no regeneration")
    native = BudgetBackend(Path(protocol["model"]), store)
    gates = []
    for case in protocol["cases"]:
        path = args.output / "sessions" / (case["name"] + ".json")
        if path.exists():
            result = json.loads(path.read_text())
        else:
            key, record = native.call(case["messages"], case["seed"], base)
            result = dict(score_gate(record, case), name=case["name"], expected=case["expected"],
                          call_keys=[key], protocol_hash=store.protocol_hash)
            store.save("sessions", case["name"], result)
        gates.append(result)
        print("GATE", case["name"], result["status"], result["exact"], flush=True)
    passed = all(r["exact"] for r in gates)
    statuses = {}
    for spec in protocol["episodes"]:
        path = args.output / "sessions" / (spec["name"] + ".json")
        if path.exists():
            result = json.loads(path.read_text())
        elif passed:
            print("EPISODE START", spec["name"], flush=True)
            result = dict(run_one(native, base, spec), protocol_hash=store.protocol_hash)
            store.save("sessions", spec["name"], result)
        else:
            result = dict(name=spec["name"], status="not_run", reason="private interface gate failed",
                          call_keys=[], protocol_hash=store.protocol_hash)
            store.save("sessions", spec["name"], result)
        statuses[spec["name"]] = result["status"]
        print("EPISODE", spec["name"], result["status"], result.get("error"), flush=True)
    store.save("sessions", "terminal", dict(gate_passed=passed, episodes=statuses, protocol_hash=store.protocol_hash))
    print("TERMINAL", passed, statuses, "No automatic follow-on", flush=True)


if __name__ == "__main__":
    main()
