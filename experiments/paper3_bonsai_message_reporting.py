"""Fresh bounded episode; message-length violations are recorded, not repaired."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import paper3_bonsai_budgeted_episode as old
from paper3.audit_runtime import PilotStore, digest
from paper3.commitment_memory import profile
from paper3.grounded_interface import authorization_case

PARENT_HASH = "a412820a9d989adcbf207ce80a0e7205a6f78fe18de3b33e8233f92b3416bcf2"
NAME = "bonsai-message-reporting-feasibility-v1"
EPISODE_SEED = 123000


def fixtures():
    cases = []
    for index, (seed, actor, package) in enumerate(((1409, 0, 0), (1409, 6, 1),
                                                  (1423, 6, 0), (1423, 3, 2))):
        p = profile(seed)
        messages, expected = authorization_case(p, actor, package, False)
        messages[0]["content"] = messages[0]["content"].replace(
            "Return one JSON object, with no prose outside it.", old.FINAL)
        cases.append(dict(name=f"private-{index}", profile=asdict(p), actor=actor,
            package=package, seed=122000 + index, messages=messages, expected=expected))
    return cases, replace(profile(1301), formateur=0, key="seed1301-leader0")


class EpisodeBackend(old.EpisodeBackend):
    def __init__(self, native, base):
        super().__init__(native, base)
        self.message_lengths = []

    def generate(self, messages, **kwargs):
        # Same prompt request for <=400 characters; only the admission rule changes.
        self.pending_request = old.collective_messages(messages)
        if len(self.call_keys) >= 30:
            raise ValueError("episode decision cap reached")
        key, record = self.native.call(self.pending_request, EPISODE_SEED + len(self.call_keys), self.base)
        self.call_keys.append(key)
        self.pending_request = None
        answer = old.checked_answer(record)
        normalized = answer.strip()
        if normalized.startswith("```") and normalized.endswith("```"):
            normalized = normalized.split("\n", 1)[1].rsplit("```", 1)[0]
        value = json.loads(normalized)
        if isinstance(value, dict) and isinstance(value.get("message"), str):
            self.message_lengths.append(dict(call_key=key, decision_index=len(self.call_keys) - 1,
                characters=len(value["message"]), exceeds_requested_limit=len(value["message"]) > old.MAX_MESSAGE))
        return answer  # Full unmodified message; engine still validates actions.


def run_episode(direct, p):
    result = old.run_episode(direct, p)
    result.update(message_lengths=list(direct.message_lengths),
        overlong_message_count=sum(m["exceeds_requested_limit"] for m in direct.message_lengths))
    return result


def prepare(parent):
    manifest = json.loads((parent / "manifest.json").read_text())
    if digest(manifest) != PARENT_HASH:
        raise ValueError("wrong frozen predecessor")
    for name, expected in manifest["sources"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError("predecessor source changed: " + name)
    previous = manifest["protocol"]
    for name, expected in previous["runtime_source_sha256"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError("installed controller/runtime source changed")
    saved = json.loads((parent / "sessions/episode.json").read_text())
    if (saved["status"] != "failed" or saved["error"] != "public message exceeds frozen limit"
            or len(list((parent / "calls").glob("*.json"))) != 10
            or len(list((parent / "sessions").glob("*.json"))) != 5):
        raise ValueError("predecessor is not the completed failed pilot")
    # Validate identical pinned artifacts and installed versions via frozen code.
    protocol, sources = old.prepare(ROOT / "results/paper3/bonsai_negotiated_memory_a2")
    cases, p = fixtures()
    protocol.update(name=NAME, private_cases=cases, profile=asdict(p), episode_seed_start=EPISODE_SEED,
        predecessor=dict(path=str(parent), manifest_hash=PARENT_HASH,
            records={str(f.relative_to(parent)): hashlib.sha256(f.read_bytes()).hexdigest()
                for folder in ("calls", "sessions") for f in sorted((parent / folder).glob("*.json"))}),
        requested_message_characters=old.MAX_MESSAGE,
        message_policy="retain unchanged <=400-character prompt instruction; preserve complete overlong messages, report noncompliance without aborting; no clipping or action repair",
        secondary=protocol["secondary"] + "; public-message lengths and noncompliance counts",
        authorization="Fuad approved a fresh bounded pilot with nonfatal prose-length reporting; no further pilots or institutional arms follow automatically")
    del protocol["max_message_characters"]  # This is no longer a hard admission cap.
    protocol["caveats"].append("admission rule changed after prior failure; fresh discovery, not confirmation or paired causal comparison")
    sources = sorted(set(sources + [Path(__file__).resolve(), ROOT / "analysis/paper3_budgeted_episode_audit.py",
                                   ROOT / "tests/test_paper3_bonsai_message_reporting.py"]))
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
        old.render(tokenizer, base, case["messages"])
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
    native = old.BudgetBackend(Path(protocol["model"]), store)
    results = []
    for case in cases:
        path = args.output / "sessions" / (case["name"] + ".json")
        if path.exists():
            result = json.loads(path.read_text())
        else:
            key, record = native.call(case["messages"], case["seed"], base)
            result = dict(old.private_score(record, case), case=case["name"], expected=case["expected"],
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
