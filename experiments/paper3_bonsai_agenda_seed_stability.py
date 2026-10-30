"""Approved three-paired-seed stability check; maximum 150 calls, no follow-on."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import paper3_bonsai_structured_agenda as prior
from experiments import paper3_bonsai_budgeted_episode as old
from experiments.paper3_bonsai_validation import BonsaiBackend
from experiments.paper3_bonsai_format_gate import ObservedGrammar
from paper3 import agenda_rights as game
from paper3.audit_runtime import PilotStore, digest

NAME = "bonsai-agenda-seed-stability-v1"
MAX_CALLS = 150
SEEDS = (181000, 182000, 183000)
PREDECESSOR_HASH = "b6865f2f21cec52970c6a80af4ffe7e2648c11b2f506d722d1914736568c58cb"
PREDECESSOR_ARCHIVE = "2ffde71583260dc0563b61491df3c38e5910c28ebad967a6a6e9b31491223c98"
case_for = prior.case_for
request_for = prior.request_for
run_one = prior.run_one


def specifications():
    profile = game.profiles()[0]
    return [dict(name=f"conflict39-s{seed}-{arm}", profile=copy.deepcopy(profile), arm=arm, seed=seed)
        for seed, arms in zip(SEEDS, (("D","B"), ("B","D"), ("D","B")))
        for arm in arms]


def prerequisite():
    archive = ROOT / "paper3/data/bonsai_structured_agenda_a1.zip"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != PREDECESSOR_ARCHIVE:
        raise ValueError("completed predecessor archive changed")
    with zipfile.ZipFile(archive) as bundle:
        report = json.loads(bundle.read("audit.json"))
        if (report["protocol_hash"] != PREDECESSOR_HASH or report["integrity_errors"]
                or report["calls"] != 100 or report["tokenization_checks"] != 100
                or report["grammar_path_checks"] != 100
                or len(report["terminal"]["episodes"]) != 4
                or set(report["terminal"]["episodes"].values()) != {"completed"}):
            raise ValueError("predecessor completion/audit mismatch")
    return dict(private_interface=prior.prerequisite(), predecessor_protocol=PREDECESSOR_HASH,
                predecessor_archive_sha256=PREDECESSOR_ARCHIVE)


def prepare():
    protocol, sources = prior.prepare()
    protocol.update(name=NAME, episodes=specifications(), max_calls=MAX_CALLS,
        max_output_tokens=MAX_CALLS*old.CAP, prerequisite=prerequisite(),
        authorization="Fuad: yes go ahead, approving the 150-call three-paired-seed repeatability check",
        design="three fresh paired seeds on unchanged selected conflict39 profile; six episodes, 25 decisions each; no new common-interest controls",
        control="no fresh common-interest calls; earlier archived controls remain separate evidence",
        selection="same conflict39 selected previously by no-model geometry screen; three new seed blocks fixed before inference, with no outcome-based seed selection",
        inference=request_for(protocol["model"], case_for(game.messages(
            specifications()[0]["profile"], "D", "r0", "opening", []), SEEDS[0])),
        gate="completed archived interface screen and 100-call pilot; no new gate inference",
        seeds="181000..181024 D then B; 182000..182024 B then D; 183000..183024 D then B; matched seeds within pair",
        instrumentation="unchanged prompts/schema/decoding; additionally persist exact schema JSON text and compiled grammar text/hash as record metadata before inference",
        criterion="all six episodes complete for paired feasibility; report every pair and reversal without favorable-outcome gate or replacement",
        reporting="pair is a stochastic replicate on one selected profile, not independent-profile evidence; report signed locked-proposal leader-advantage and enacted-regret differences, individual utility changes, passage, consistency, replay, failures, costs; original seed kept separate",
        scope="selected-profile seed stability only; no confirmation, population effect, significance, independent model replication or paper claim",
        no_follow_on="terminal after six episodes, maximum 150 calls; no retries, repairs, seed/profile selection, new models/elections or automatic larger batch")
    sources = sorted(set(sources + [Path(__file__).resolve(),
        ROOT / "analysis/paper3_agenda_seed_stability_audit.py",
        ROOT / "tests/test_paper3_agenda_seed_stability.py"]))
    return json.loads(json.dumps(protocol)), sources


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
        schema_text = json.dumps(case["schema"])
        processor = build_json_schema_logits_processor(tokenizer, schema_text)
        grammar = ObservedGrammar(ThinkingAwareLogitsProcessor(
            processor, tokenizer, enable_thinking=True))
        row = dict(request=request, rendered_prompt=prompt, prompt_token_ids=ids,
            schema_text=schema_text, compiled_grammar=processor.grammar,
            grammar_sha256=hashlib.sha256(processor.grammar.encode()).hexdigest(),
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

