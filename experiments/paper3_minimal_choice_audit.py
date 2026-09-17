"""Balanced private-choice diagnostics, not an institutional treatment or gate."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import PilotStore
from paper3.commitment_memory import parse
from experiments.paper3_memory_pilot import CompleteResponseBackend


def choice_case(actor, sign, table, encoding):
    if actor not in (2, 5) or sign not in (-1, 1):
        raise ValueError("unsupported fixture")
    if table not in ("own", "all") or encoding not in ("boolean", "label"):
        raise ValueError("unsupported diagnostic arm")
    utilities = {i: {"A0": i + 1, "B0": -(i + 2)} for i in range(7)}
    utilities[actor] = {"A0": sign * 5, "B0": -sign * 2}
    shown = utilities if table == "all" else {actor: utilities[actor]}
    record = dict(principal_id=actor, utilities_by_principal=shown,
                  offered_projects=["A0", "B0"], decline_utility=0)
    system = (f"You are representative {actor}, serving only principal {actor}. "
              "Maximize that principal's utility in this isolated private choice. "
              "Accepting delivers BOTH offered projects and gives their SUM of utilities. "
              "Declining gives zero. Your choice alone determines this payoff. "
              "There are no promises, other votes, later rounds or reputation rewards. "
              "Return one JSON object, with no prose outside it.")
    if encoding == "boolean":
        task = "Return accept (boolean: true accepts, false declines) and principal_utility_if_accepted (integer)."
        schema = dict(accept=bool, principal_utility_if_accepted=int)
        expected = dict(accept=sign > 0, principal_utility_if_accepted=3 * sign)
    else:
        task = 'Return action (string: "accept" or "decline") and principal_utility_if_accepted (integer).'
        schema = dict(action=str, principal_utility_if_accepted=int)
        expected = dict(action="accept" if sign > 0 else "decline", principal_utility_if_accepted=3 * sign)
    return [dict(role="system", content=system),
            dict(role="user", content=json.dumps(record, sort_keys=True) + "\n" + task)], schema, expected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8013/v1")
    args = parser.parse_args()
    protocol = dict(name="minimal-private-choice-diagnostic-v1",
                    purpose="instrument debugging, never substitutes for the failed authorization gate",
                    model=args.model, model_revision=args.model_revision, base_url=args.base_url,
                    actors=[2, 5], signs=[-1, 1], tables=["own", "all"], encodings=["boolean", "label"],
                    expected_calls=16, max_tokens=96, temperature=0,
                    exclusions="none; no retries, no repairs; stop after these 16 calls",
                    interpretation="paired table/encoding contrasts on synthetic diagnostic fixtures, not population estimates",
                    server=dict(fix_mistral_regex=True, enable_thinking=False, decode_concurrency=1,
                                prompt_concurrency=1, prompt_cache_size=1, prompt_cache_bytes=536870912),
                    runtime={p: importlib.metadata.version(p) for p in ("mlx", "mlx-lm", "transformers")})
    sources = [Path(__file__), ROOT / "paper3/audit_runtime.py", ROOT / "paper3/commitment_memory.py",
               ROOT / "experiments/paper3_memory_pilot.py", ROOT / "experiments/paper3_mistral_server.py"]
    store = PilotStore(args.output, protocol, sources)
    snapshot = args.output / "sources.json"
    if not snapshot.exists():
        with snapshot.open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    backend = CompleteResponseBackend(args.model, args.base_url, store)
    for actor in protocol["actors"]:
        for sign in protocol["signs"]:
            for table in protocol["tables"]:
                for encoding in protocol["encodings"]:
                    key = f"actor{actor}-sign{sign}-{table}-{encoding}"
                    if (args.output / "sessions" / (key + ".json")).exists():
                        continue
                    backend.call_keys.clear()
                    messages, schema, expected = choice_case(actor, sign, table, encoding)
                    result = dict(actor=actor, sign=sign, table=table, encoding=encoding, expected=expected)
                    try:
                        reply = parse(backend.generate(messages, temperature=0, max_tokens=96), schema)
                        action_key = "accept" if encoding == "boolean" else "action"
                        if encoding == "label" and reply[action_key] not in ("accept", "decline"):
                            raise ValueError("invalid action label")
                        result.update(status="completed", reply=reply, exact=reply == expected,
                                      action_correct=reply[action_key] == expected[action_key],
                                      utility_correct=reply["principal_utility_if_accepted"] == expected["principal_utility_if_accepted"])
                    except (ValueError, OSError, TimeoutError) as exc:
                        result.update(status="failed", error=str(exc), exact=False,
                                      action_correct=False, utility_correct=False)
                    result.update(call_keys=list(backend.call_keys), protocol_hash=store.protocol_hash)
                    store.save("sessions", key, result)
                    print(key, result["status"], result["exact"], flush=True)


if __name__ == "__main__":
    main()
