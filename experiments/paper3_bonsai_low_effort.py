"""Three selected-failure replays; native reasoning remains on, no follow-on run."""
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
from paper3.commitment_memory import parse, package_check
from experiments.paper3_bonsai_validation import BonsaiBackend, final_answer, append_generated_token

PARENT_HASH = "a8fd7b6bc96ed14523c5ef5e9c201b3a33826e6577b9c7e04c0d232277c2946c"
CASES = (
    ("seed503-leader0", "719d31cf8216d3281b380e0f959891addb84fe8c593c2f6ab6b0e97964cce01e", True),
    ("seed601-leader3", "b2f8a25a4be3d2aa95f5b01f5a97a310396bdf23f955f3f13a5b109109531741", False),
    ("seed709-leader6", "ccc5997bcca04c835e4a4d55ad4a74239fd5ef8425fb52ac4b13fc5dc39a1f8d", True),
)
LOW_INSTRUCTION = ("Reasoning effort is set to low. Keep your thinking brief and focused, "
                   "moving directly to the conclusion without unnecessary elaboration.\n\n")


def low_request(original):
    request = copy.deepcopy(original)
    if request["reasoning_effort"] != "medium" or request["enable_thinking"] is not True:
        raise ValueError("requires original native medium reasoning")
    if request["max_tokens"] != 8192:
        raise ValueError("requires unchanged 8192-token cap")
    request["reasoning_effort"] = "low"
    return request


def render_checked(tokenizer, base, original):
    messages = original["request"]["messages"]
    kwargs = dict(tokenize=False, add_generation_prompt=True, enable_thinking=True)
    medium = tokenizer.apply_chat_template(messages, reasoning_effort="medium", **kwargs)
    low = tokenizer.apply_chat_template(messages, reasoning_effort="low", **kwargs)
    if medium != original["rendered_prompt"] or tokenizer.encode(medium, add_special_tokens=True) != original["prompt_token_ids"]:
        raise ValueError("medium prompt/token replay mismatch")
    prefix = "<|im_start|>system\n"
    if not medium.startswith(prefix) or low != prefix + LOW_INSTRUCTION + medium[len(prefix):]:
        raise ValueError("low template changed more than the approved instruction")
    if not low.endswith("<think>\n"):
        raise ValueError("native thinking prefill missing")
    ids = tokenizer.encode(low, add_special_tokens=True)
    if ids != base.encode(low, add_special_tokens=True) or len(ids) > 8192:
        raise ValueError("base tokenizer mismatch or oversized input")
    return low, ids


def score(record, schema):
    result = dict(status="failed", feasible=False)
    try:
        choice = record["response"]["choices"][0]
        if choice["finish_reason"] != "stop":
            raise ValueError("non-normal generation termination")
        usage = record["response"]["usage"]
        if (record["cached_tokens"] != 0 or len(record["prompt_token_ids"]) != usage["prompt_tokens"]
                or len(record["generated_token_ids"]) != usage["completion_tokens"]
                or usage["completion_tokens"] > 8192):
            raise ValueError("token/cache accounting mismatch")
        types = {"int": int, "str": str, "bool": bool}
        reply = parse(final_answer(choice["message"]["content"]), {k: types[v] for k, v in schema.items()})
        package_check(reply)
        if len(reply["message"]) > 400:
            raise ValueError("public message exceeds frozen limit")
        result.update(status="completed", feasible=True, reply=reply)
    except ValueError as exc:
        result["error"] = str(exc)
    return result


def prepare(parent):
    manifest = json.loads((parent / "manifest.json").read_text())
    if digest(manifest) != PARENT_HASH:
        raise ValueError("wrong frozen parent")
    p = manifest["protocol"]
    versions = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}
    if versions != p["inference"]["runtime"]:
        raise ValueError("runtime changed since parent")
    for name, expected in manifest["sources"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError("parent source changed: " + name)
    for root, hashes in ((Path(p["model"]), p["inference"]["model_file_sha256"]),
                         (Path(p["base_tokenizer"]), p["base_file_hashes"])):
        for name, expected in hashes.items():
            if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
                raise ValueError("pinned artifact changed: " + name)
    if len(list((parent / "calls").glob("*.json"))) != 5 or len(list((parent / "sessions").glob("*.json"))) != 3:
        raise ValueError("parent is not the completed five-call batch")
    cases, originals = [], {}
    for name, key, response in CASES:
        saved = json.loads((parent / "sessions" / (name + "-shared.json")).read_text())
        old = json.loads((parent / "calls" / (key + ".json")).read_text())
        if (saved["status"] != "failed" or saved["call_keys"][-1] != key
                or old["protocol_hash"] != PARENT_HASH
                or digest(dict(request=old["request"], protocol=PARENT_HASH)) != key
                or old["response"]["choices"][0]["finish_reason"] != "length"
                or old["response"]["usage"]["completion_tokens"] != 8192):
            raise ValueError("original failure/provenance mismatch")
        schema = dict(package="int", first="str", message="str")
        if response:
            schema["support"] = "bool"
        cases.append(dict(name=name, original_call=key, schema=schema, request=low_request(old["request"])))
        originals[name] = old
    protocol = dict(name="bonsai-native-low-effort-selected-failure-v1", max_calls=3,
        parent=str(parent), parent_manifest_hash=PARENT_HASH,
        parent_record_hashes={str(f.relative_to(parent)): hashlib.sha256(f.read_bytes()).hexdigest()
            for folder in ("calls", "sessions") for f in sorted((parent / folder).glob("*.json"))},
        model=p["model"], model_revision=p["model_revision"], base_tokenizer=p["base_tokenizer"],
        runtime=versions, model_file_sha256=p["inference"]["model_file_sha256"],
        base_file_hashes=p["base_file_hashes"], cases=cases,
        intervention="native low vs saved medium: publisher brief-thinking instruction only; reasoning enabled",
        primary="normal finish, unique nonempty native reasoning closure, exact final schema, valid package/order and <=400-character public message",
        secondary="generated tokens, elapsed generation time, memory, complete raw output; descriptive, not semantic correctness or optimal negotiation",
        stopping="complete exactly these three cases; no retries, repairs, budget changes, case replacement or automatic collective follow-on",
        limitations=["selected on medium-effort failures, not independent success-rate estimation",
            "one draw per case; unchanged seed does not force token-prefix equality after prompt change",
            "low adds 26 prompt tokens on these cases; not compute matched",
            "no completed negotiation, institutional contrast or publication result follows from passing"])
    sources = [Path(f) for f in sorted(set(manifest["sources"]) | {str(Path(__file__).resolve())})]
    return protocol, sources, originals


class LowEffortBackend(BonsaiBackend):
    def call_original(self, original, base):
        import mlx.core as mx
        from mlx_vlm import stream_generate
        request = low_request(original["request"])
        key = digest(dict(request=request, protocol=self.store.protocol_hash))
        path = self.store.root / "calls" / (key + ".json")
        if path.exists():
            return key, json.loads(path.read_text())
        prompt, prompt_ids = render_checked(self.processor.tokenizer, base, original)
        mx.random.seed(request["seed"])
        started = time.time()
        chunks, tokens = [], []
        generation = {k: request[k] for k in ("max_tokens", "temperature", "top_p", "top_k", "min_p",
            "presence_penalty", "repetition_penalty", "prefill_step_size", "enable_thinking")}
        for part in stream_generate(self.model, self.processor, prompt=prompt, skip_special_tokens=False, **generation):
            chunks.append(part.text)
            append_generated_token(tokens, part)
        record = dict(request=request, rendered_prompt=prompt, prompt_token_ids=prompt_ids,
            generated_token_ids=tokens, protocol_hash=self.store.protocol_hash,
            origin="publisher rotation-aware VLM loader; native stream; selected-failure low-effort diagnostic",
            response=dict(choices=[dict(message=dict(role="assistant", content="".join(chunks)),
                finish_reason=part.finish_reason)], usage=dict(prompt_tokens=part.prompt_tokens,
                completion_tokens=part.generation_tokens)), peak_memory_gb=part.peak_memory,
            cached_tokens=part.cached_tokens, started_unix=started, elapsed_seconds=time.time() - started,
            preflight=dict(medium_prompt_and_tokens_match=True, only_low_instruction_added=True,
                           native_thinking_prefill=True, base_token_ids_equal=True))
        self.store.save("calls", key, record)
        return key, record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    protocol, sources, originals = prepare(args.parent)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(protocol["model"], local_files_only=True)
    base = AutoTokenizer.from_pretrained(protocol["base_tokenizer"], local_files_only=True)
    for old in originals.values():
        render_checked(tokenizer, base, old)
    store = PilotStore(args.output, protocol, sources)
    snapshot = args.output / "sources.json"
    if not snapshot.exists():
        with snapshot.open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    backend = LowEffortBackend(Path(protocol["model"]), store)
    results = []
    for case in protocol["cases"]:
        saved = args.output / "sessions" / (case["name"] + ".json")
        if saved.exists():
            result = json.loads(saved.read_text())
        else:
            key, record = backend.call_original(originals[case["name"]], base)
            result = dict(case=case["name"], original_call=case["original_call"], schema=case["schema"],
                call_keys=[key], protocol_hash=store.protocol_hash, **score(record, case["schema"]))
            store.save("sessions", case["name"], result)
        results.append(result)
        print(case["name"], result["status"], result.get("error"), flush=True)
    print("COMPLETE", sum(r["feasible"] for r in results), "/3 feasible; no automatic follow-on", flush=True)


if __name__ == "__main__":
    main()
