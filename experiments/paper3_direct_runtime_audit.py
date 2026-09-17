"""Four unchanged recorded requests through unbatched MLX, fresh KV per call."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import PilotStore, digest
from paper3.commitment_memory import parse

CASES = [f"actor{actor}-sign{sign}-{table}-{encoding}" for actor, table, encoding in
         [(2, "own", "boolean"), (5, "all", "label")] for sign in (-1, 1)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_manifest = json.loads((args.source / "manifest.json").read_text())
    source_protocol = source_manifest["protocol"]
    cases = []
    for name in CASES:
        session = json.loads((args.source / "sessions" / (name + ".json")).read_text())
        call = json.loads((args.source / "calls" / (session["call_keys"][0] + ".json")).read_text())
        cases.append(dict(name=name, session=session, call=call))
    model_path = Path(source_protocol["model"])
    protocol = dict(name="direct-runtime-replay-v1", purpose="runtime diagnostic, not institutional evidence",
                    source_manifest_hash=digest(source_manifest), source_cases_hash=digest(cases), cases=CASES,
                    model=str(model_path), model_revision=source_protocol["model_revision"], expected_calls=4,
                    inference="mlx_lm.stream_generate, unbatched, new prompt KV cache per call; same weights and tokenizer correction",
                    tokenizer_config_sha256=hashlib.sha256((model_path / "tokenizer_config.json").read_bytes()).hexdigest(),
                    temperature=0, max_tokens=96, exclusions="none; no retries or repairs",
                    runtime={p: importlib.metadata.version(p) for p in ("mlx", "mlx-lm", "transformers")})
    sources = [Path(__file__), ROOT / "paper3/audit_runtime.py", ROOT / "paper3/commitment_memory.py"]
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler
    model, tokenizer = load(str(model_path), tokenizer_config={"fix_mistral_regex": True})
    for case in cases:
        name, request = case["name"], case["call"]["request"]
        if (args.output / "sessions" / (name + ".json")).exists():
            continue
        key = digest(dict(request=request, protocol=store.protocol_hash))
        path = args.output / "calls" / (key + ".json")
        if path.exists():
            record = json.loads(path.read_text())
        else:
            started = time.time()
            prompt = tokenizer.apply_chat_template(request["messages"], tokenize=True,
                                                   add_generation_prompt=True, enable_thinking=False)
            chunks, tokens = [], []
            for part in stream_generate(model, tokenizer, prompt=prompt, max_tokens=request["max_tokens"],
                                        sampler=make_sampler(temp=request["temperature"]), prompt_cache=None):
                chunks.append(part.text)
                tokens.append(part.token)
            # Normalize actual direct-generation output into the existing audit shape.
            response = dict(choices=[dict(message=dict(role="assistant", content="".join(chunks)),
                                          finish_reason=part.finish_reason)],
                            usage=dict(prompt_tokens=part.prompt_tokens, completion_tokens=part.generation_tokens))
            record = dict(request=request, response=response, origin="direct mlx_lm.stream_generate, not an HTTP response",
                          prompt_token_ids=prompt, generated_token_ids=tokens, started_unix=started,
                          elapsed_seconds=time.time() - started, protocol_hash=store.protocol_hash,
                          original_server_response=case["call"]["response"])
            store.save("calls", key, record)
        result = dict(expected=case["session"]["expected"], call_keys=[key], protocol_hash=store.protocol_hash)
        try:
            choice = record["response"]["choices"][0]
            if choice["finish_reason"] != "stop":
                raise ValueError("generation did not end normally")
            schema = dict(accept=bool) if case["session"]["encoding"] == "boolean" else dict(action=str)
            schema["principal_utility_if_accepted"] = int
            reply = parse(choice["message"]["content"], schema)
            result.update(status="completed", reply=reply, exact=reply == result["expected"],
                          same_as_server=reply == case["session"]["reply"])
        except ValueError as exc:
            result.update(status="failed", error=str(exc), exact=False)
        store.save("sessions", name, result)
        print(name, result, flush=True)


if __name__ == "__main__":
    main()
