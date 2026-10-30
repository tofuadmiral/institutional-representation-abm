"""Approved four-episode structured-action agenda pilot; maximum 100 calls."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import paper3_bonsai_agenda as agenda
from experiments import paper3_bonsai_format_gate as gate
from experiments import paper3_bonsai_budgeted_episode as old
from experiments.paper3_bonsai_validation import BonsaiBackend
from experiments.paper3_bonsai_format_gate import ObservedGrammar
from paper3 import agenda_rights as game
from paper3.audit_runtime import PilotStore, digest

NAME = "bonsai-structured-agenda-discovery-v1"
MAX_CALLS = 100
PREREQUISITE_HASH = "25977965de8b0f19e0e6ecd1b7e89f2913600c3a64de12a59c3ac76d9073935c"
PREREQUISITE_ARCHIVE = "e0c96daca60203cfe63ce87eda2c0cb6cfab8da4b042440da51b2ab3263d7f48"


def specifications():
    specs = copy.deepcopy(agenda.specifications())
    for spec in specs:
        spec["seed"] = 171000 if spec["profile"]["name"] == "conflict39" else 172000
    return specs


def case_for(messages, seed):
    context = json.loads(messages[-1]["content"].split("\n", 1)[0])
    stage = context["stage"]
    candidates = context.get("candidate_policy_ids",
        [p["policy_id"] for p in context["profile"]["catalog"]])
    if stage in ("pairwise", "ratification"):
        schema = gate.schema_for(stage, candidates)
    elif stage in ("opening", "responses", "locked_proposal", "amendment", "leader_selection"):
        schema = gate.obj(dict(policy_id=dict(type="string", enum=list(candidates)),
                               message=dict(type="string")))
    else:
        raise ValueError("unknown stage")
    structured = copy.deepcopy(messages)
    structured[-1]["content"] += (
        "\nYour final answer must be a JSON OBJECT, not a bare policy name or an unwrapped vote map. "
        "Use exactly the keys and nesting specified by this JSON Schema, with no Markdown fence or outside prose: "
        + json.dumps(schema, sort_keys=True))
    return dict(name=f"{seed}-{stage}-{context['representative']}", messages=structured,
                seed=seed, schema=schema)


def request_for(model, case):
    return gate.request_for(model, case)


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


def run_one(native, base, spec):
    keys, pending = [], None
    def ask(messages):
        nonlocal pending
        if len(keys) >= 25:
            raise RuntimeError("episode call cap exceeded")
        case = case_for(messages, spec["seed"] + len(keys))
        pending = case
        key, record = native.call(case, base)
        keys.append(key)
        pending = None
        return old.checked_answer(record)
    result = game.run_episode(spec["profile"], spec["arm"], ask)
    return dict(result, name=spec["name"], profile=spec["profile"], arm=spec["arm"],
                call_keys=keys, unsubmitted_request=pending)


def prerequisite():
    root = ROOT / "results/paper3/bonsai_format_gate_a1"
    manifest = json.loads((root / "manifest.json").read_text())
    terminal = json.loads((root / "sessions/terminal.json").read_text())
    archive = ROOT / "paper3/data/bonsai_format_gate_a1.zip"
    if digest(manifest) != PREREQUISITE_HASH or terminal != dict(
            checks=16, exact=12, exact_scored=12, passed=True,
            protocol_hash=PREREQUISITE_HASH, valid=16):
        raise ValueError("completed prerequisite mismatch")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != PREREQUISITE_ARCHIVE:
        raise ValueError("prerequisite archive changed")
    return dict(protocol_hash=PREREQUISITE_HASH, archive_sha256=PREREQUISITE_ARCHIVE,
                terminal=terminal)


def prepare():
    protocol, sources = agenda.prepare()
    interface, interface_sources = gate.prepare()
    protocol.pop("cases")
    protocol.update(name=NAME, episodes=specifications(), max_calls=MAX_CALLS,
        max_output_tokens=MAX_CALLS*old.CAP, prerequisite=prerequisite(),
        gate="completed frozen 16-call screen is prerequisite; no additional gate calls",
        authorization="Fuad: run it, approving four legislature episodes capped at 100 calls",
        inference=request_for(protocol["model"], case_for(game.messages(
            specifications()[0]["profile"], "D", "r0", "opening", []), 171000)),
        grammar_runtime=interface["grammar_runtime"],
        grammar_source_sha256=interface["grammar_source_sha256"],
        decoding=interface["decoding"],
        interface_change="Explicit schema text plus constrained final decoding at every stage; public message remains unconstrained string with instructed 400-character limit, overlength retained/reported",
        seeds="fresh fixed 171000..171024 conflict; 172000..172024 common-interest; same seeds paired across arms, distinct requests/history",
        criterion="all four episodes complete for paired feasibility; preserve incomplete episodes without imputed policy; behavioral adaptation and representation readouts remain discovery only",
        no_follow_on="terminal after four episodes, at most 100 calls; no retries, repair, expansion, confirmation or election follows automatically")
    sources = sorted(set(sources + interface_sources + [
        Path(__file__).resolve(), ROOT / "analysis/paper3_structured_agenda_audit.py",
        ROOT / "tests/test_paper3_structured_agenda.py"]))
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
    for spec in protocol["episodes"]:
        for stage in ("opening", "responses", "locked_proposal", "amendment",
                      "pairwise", "leader_selection", "ratification"):
            candidates = ["p3", "p6"] if stage in ("pairwise", "leader_selection", "ratification") else None
            case = case_for(game.messages(spec["profile"], spec["arm"],
                spec["profile"]["leader"], stage, [], candidates), spec["seed"])
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
    backend = StructuredBackend(Path(protocol["model"]), store)
    statuses = {}
    for spec in protocol["episodes"]:
        path = args.output / "sessions" / (spec["name"] + ".json")
        if path.exists():
            result = json.loads(path.read_text())
        else:
            print("EPISODE START", spec["name"], flush=True)
            result = dict(run_one(backend, base, spec), protocol_hash=store.protocol_hash)
            store.save("sessions", spec["name"], result)
        statuses[spec["name"]] = result["status"]
        print("EPISODE", spec["name"], result["status"], result.get("resolution"),
              result.get("error"), flush=True)
    terminal = dict(prerequisite_passed=True, episodes=statuses, protocol_hash=store.protocol_hash)
    store.save("sessions", "terminal", terminal)
    print("TERMINAL", terminal, "No automatic follow-on", flush=True)


if __name__ == "__main__":
    main()

