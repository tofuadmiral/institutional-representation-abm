"""Approved 16-call structured-action screen; no legislature follows."""
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
from experiments import paper3_bonsai_budgeted_episode as old
from experiments.paper3_bonsai_validation import BonsaiBackend
from paper3 import agenda_rights as game
from paper3.audit_runtime import PilotStore, digest

NAME = "bonsai-structured-action-gate-v1"
MAX_CALLS = 16


def obj(properties):
    return dict(type="object", properties=properties, required=list(properties), additionalProperties=False)


def schema_for(stage, candidates):
    policy = dict(type="string", enum=list(candidates))
    votes = obj({p: dict(type="boolean") for p in candidates})
    if stage == "selector":
        return obj(dict(selected_policy=policy, votes=votes))
    if stage == "pairwise":
        return obj(dict(policy_id=policy))
    if stage == "ratification":
        return obj(dict(votes=votes))
    raise ValueError("unknown stage")


def cases():
    result = []
    for case in game.gate_cases():
        row = copy.deepcopy(case)
        row.update(name=f"selector-{len(result)}", stage="selector", candidates=["policy_k", "policy_m"])
        result.append(row)
    for arm in game.ARMS:
        for stage in ("pairwise", "ratification"):
            for n in (1, 2):
                candidates = ["policy_k", "policy_m"][:n]
                utilities = {p: (6 if (i == 0) == (arm == "D") else -4) for i, p in enumerate(candidates)}
                context = dict(representative="r3", leader="r0", sponsor="r1", stage=stage,
                    locked_proposal="policy_k", amendment=candidates[-1], candidate_policy_ids=candidates,
                    own_principal_utilities=dict(utilities, q=0))
                if stage == "pairwise":
                    task = "Cast your pairwise ballot for one of the candidate policies. This is a private action-interface check, not a negotiation episode."
                    expected = None  # Advisory votes have no uniquely correct strategic answer.
                else:
                    context.update(leader_choice="policy_k",
                        pairwise_ballots={r: candidates[-1] if i < 4 else "policy_k" for i,r in enumerate(game.ROLES)},
                        other_ratification_votes={p: [True, True, True, False, False, False] for p in candidates})
                    task = ("Submit your conditional ratification card for every distinct candidate: would you enact it IF selected? "
                        "For each candidate, the other six ratification votes are three yes and three no, so your vote determines enactment versus q. "
                        "These are alternative contingencies, not sequential policies. This is a private interface check of supplied history.")
                    expected = dict(votes={p: u > 0 for p,u in utilities.items()})
                result.append(dict(name=f"{stage}-{arm}-{n}", stage=stage, arm=arm, candidates=candidates,
                    expected=expected, messages=[dict(role="system", content=
                        "You are representative r3, entrusted to maximize principal r3's final policy utility. "
                        + game.rules(arm) + " " + game.FINAL),
                        dict(role="user", content=json.dumps(context, sort_keys=True)+"\n"+task)]))
    for i, row in enumerate(result):
        row["seed"] = 160000 + i
        row["schema"] = schema_for(row["stage"], row["candidates"])
        row["messages"][-1]["content"] += (
            "\nYour final answer must be a JSON OBJECT, not a bare policy name or an unwrapped vote map. "
            "Use exactly the keys and nesting specified by this JSON Schema, with no Markdown fence or outside prose: "
            + json.dumps(row["schema"], sort_keys=True))
    assert len(result) == MAX_CALLS
    return result


def request_for(model, case):
    return dict(old.request_for(model, case["messages"], case["seed"]), response_schema=case["schema"])


def score(record, case):
    try:
        raw = old.checked_answer(record)
        reply = game.decode(raw)
        if case["stage"] == "selector":
            checked = game.gate_score(raw, case["expected"])
            if checked["status"] != "completed":
                raise ValueError(checked["error"])
        else:
            game.validate_action(raw, case["stage"], case["candidates"])
        exact = reply == case["expected"] if case["expected"] is not None else None
        return dict(status="completed", valid=True, exact=exact, passed=exact is not False, reply=reply)
    except (ValueError, KeyError) as exc:
        return dict(status="failed", valid=False, exact=None, passed=False, error=str(exc))


class ObservedGrammar:
    """Record the real processor's phase on each actual generation step."""
    def __init__(self, wrapped):
        self.wrapped, self.events = wrapped, []

    def __call__(self, tokens, logits):
        result = self.wrapped(tokens, logits)
        self.events.append(dict(previous_token=int(tokens[-1].item()), input_tokens=int(tokens.size),
            active=bool(self.wrapped._active), constrained=result is not logits))
        return result


class StructuredBackend(BonsaiBackend):
    def call(self, case, base):
        import mlx.core as mx
        from mlx_vlm import stream_generate
        from mlx_vlm.structured import ThinkingAwareLogitsProcessor, build_json_schema_logits_processor
        request = request_for(self.path, case)
        key = digest(dict(request=request, protocol=self.store.protocol_hash))
        path = self.store.root / "calls" / (key + ".json")
        if path.exists():
            row = json.loads(path.read_text())
            if row["status"] == "started":
                raise RuntimeError("interrupted call is not retried")
            return key, row
        if len(list((self.store.root / "calls").glob("*.json"))) >= MAX_CALLS:
            raise ValueError("authorized call limit reached")
        tokenizer = self.processor.tokenizer
        prompt, ids = old.render(tokenizer, base, case["messages"])
        grammar = ObservedGrammar(ThinkingAwareLogitsProcessor(
            build_json_schema_logits_processor(tokenizer, case["schema"]), tokenizer, enable_thinking=True))
        row = dict(request=request, rendered_prompt=prompt, prompt_token_ids=ids,
            protocol_hash=self.store.protocol_hash, status="started", started_unix=time.time())
        self.store.save("calls", key, row)
        mx.random.seed(case["seed"])
        boundary, chunks, last = old.BoundaryRecorder(), [], None
        generation = {k:v for k,v in request.items() if k not in ("model", "messages", "seed", "reasoning_effort", "response_schema")}
        previous = getattr(tokenizer, "thinking_budget_criteria", None)
        try:
            for part in stream_generate(self.model, self.processor, prompt=prompt,
                    skip_special_tokens=False, logits_processors=[grammar], **generation):
                last = part
                chunks.append(part.text)
                controller = getattr(tokenizer, "thinking_budget_criteria", None)
                if controller is previous:
                    raise ValueError("thinking controller was not freshly constructed")
                boundary.observe(part, controller)
            if last is None:
                raise ValueError("empty generation stream")
        except Exception as exc:
            row["generation_error"] = type(exc).__name__ + ": " + str(exc)
        try:
            summary = boundary.summary(tokenizer.encode("</think>", add_special_tokens=False)[-1])
        except ValueError as exc:
            row["generation_error"] = str(exc)
            summary = dict(schedules=boundary.schedules, accounting_error=str(exc))
        row.update(status="recorded", generated_token_ids=boundary.tokens, boundary=summary,
            grammar_trace=grammar.events,
            response=dict(choices=[dict(message=dict(role="assistant", content="".join(chunks)),
                finish_reason=getattr(last, "finish_reason", "error"))], usage=dict(
                prompt_tokens=getattr(last, "prompt_tokens", len(ids)),
                completion_tokens=getattr(last, "generation_tokens", len(boundary.tokens)))),
            cached_tokens=getattr(last, "cached_tokens", None), peak_memory_gb=getattr(last, "peak_memory", None),
            elapsed_seconds=time.time()-row["started_unix"],
            origin="publisher rotation-aware loader; final-answer grammar; native reasoning deadline; no action repair")
        self.store.save("calls", key, row)
        print("CALL", case["name"], len(boundary.tokens), summary.get("closure_origin"),
              row["response"]["choices"][0]["finish_reason"], flush=True)
        return key, row


def prepare():
    parent, sources = old.prepare(ROOT / "results/paper3/bonsai_negotiated_memory_a2")
    protocol = {k:parent[k] for k in ("model", "model_revision", "model_file_sha256", "base_tokenizer",
        "base_file_hashes", "runtime", "runtime_source_sha256", "controller")}
    packages = Path(sys.prefix) / "lib/python3.13/site-packages"
    runtime_files = [packages / "mlx_vlm/structured.py"] + [p for p in (packages / "llguidance").rglob("*")
        if p.is_file() and p.suffix in (".py", ".pyi", ".so", ".dylib")]
    protocol.update(name=NAME, cases=cases(), max_calls=MAX_CALLS, max_output_tokens=MAX_CALLS*old.CAP,
        max_input_tokens=old.MAX_INPUT, inference=request_for(parent["model"], cases()[0]),
        grammar_runtime={p:importlib.metadata.version(p) for p in ("mlx", "mlx-vlm", "llguidance", "transformers")},
        grammar_source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime_files},
        authorization="Fuad: yes do it, approving the proposed 16-call format-constrained screen only",
        criterion="all 16 valid normally terminated actions; all 8 selector checks exact and all 4 pivotal ratification checks exact; 4 pairwise checks score format only",
        failure_policy="complete all 16 prespecified checks, retain all failures, no retries/repairs; an interrupted started call requires inspection and is never regenerated",
        scope="instrument validation on selected private fixtures, not collective behavior, reliability estimate, independent replication or publication evidence",
        decoding="fresh installed thinking-aware schema processor each call; unconstrained native reasoning, schema-constrained final tokens; no utility or correct answer encoded in grammar",
        no_follow_on="terminal after 16 calls; no legislature, new model or larger batch")
    sources = sorted(set(sources + [Path(__file__).resolve(), ROOT / "paper3/agenda_rights.py",
        ROOT / "analysis/paper3_format_gate_audit.py", ROOT / "analysis/paper3_budgeted_episode_audit.py",
        ROOT / "analysis/paper3_format_stream_preflight.py",
        ROOT / "tests/test_paper3_format_gate.py"]))
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
        old.render(tokenizer, base, case["messages"])
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)):p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    if (args.output / "sessions/terminal.json").exists():
        print("Already terminal; no inference", flush=True)
        return
    if any(json.loads(p.read_text())["status"] == "started" for p in (args.output / "calls").glob("*.json")):
        raise RuntimeError("interrupted call requires inspection; no regeneration")
    backend, results = StructuredBackend(Path(protocol["model"]), store), []
    for case in protocol["cases"]:
        path = args.output / "sessions" / (case["name"] + ".json")
        if path.exists():
            result = json.loads(path.read_text())
        else:
            key, row = backend.call(case, base)
            result = dict(score(row, case), name=case["name"], call_keys=[key], protocol_hash=store.protocol_hash)
            store.save("sessions", case["name"], result)
        results.append(result)
        print("CHECK", case["name"], result["valid"], result["exact"], flush=True)
    terminal = dict(passed=all(r["passed"] for r in results), checks=len(results),
        valid=sum(r["valid"] for r in results), exact=sum(r["exact"] is True for r in results),
        exact_scored=12, protocol_hash=store.protocol_hash)
    store.save("sessions", "terminal", terminal)
    print("TERMINAL", terminal, "No automatic follow-on", flush=True)


if __name__ == "__main__":
    main()
