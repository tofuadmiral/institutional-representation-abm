"""Read-only replay of completed negotiated sessions; never generates model output.

Incomplete/failed sessions remain visible without invented votes or payoffs.
This checks recorded requests and outcomes, not GPU execution or tokenizer
equivalence independently of the frozen runner's preflight.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import digest
from paper3.commitment_memory import Profile, negotiate, first_vote, second_vote
from paper3.grounded_interface import GroundedInterface
from experiments.paper3_bonsai_validation import final_answer
from experiments.paper3_bonsai_memory_pilot import mechanism_opportunity
from experiments.paper3_native_memory_pilot import event_index


class AuditMismatch(ValueError):
    pass


def native_messages(messages, view, message_limit):
    """Independent request reconstruction matching the frozen wrapper."""
    messages = copy.deepcopy(messages)
    messages[0]["content"] = messages[0]["content"].replace("You may reason internally; output JSON only.", "")
    messages[0]["content"] += "\nAfter your native thinking block, return one JSON object, with no prose outside it."
    encoded, task = messages[-1]["content"].split("\n", 1)
    record = json.loads(encoded)
    if view == "event_index":
        record["event_index"] = event_index(record["events"])
    if "message (string)" in task:
        task += f" Your public message must contain at most {message_limit} characters."
    messages[-1]["content"] = json.dumps(record, sort_keys=True) + "\n" + task
    return messages


class RecordedReplay:
    def __init__(self, calls, keys, protocol, seed, view):
        self.calls, self.keys, self.protocol = calls, keys, protocol
        self.seed, self.view, self.used = seed, view, 0

    def generate(self, messages, **kwargs):
        if self.used >= len(self.keys):
            raise AuditMismatch("missing recorded response; replay never calls a model")
        row = self.calls[self.keys[self.used]]
        request = row["request"]
        expected = native_messages(messages, self.view, self.protocol["max_public_message_characters"])
        if request["messages"] != expected or request["seed"] != self.seed + self.used:
            raise AuditMismatch("request/seed differs from reconstructed institutional step")
        self.used += 1
        choice = row["response"]["choices"][0]
        if choice["finish_reason"] != "stop":
            raise AuditMismatch("completed session contains non-normal generation")
        answer = final_answer(choice["message"]["content"])
        normalized = answer.strip()
        if normalized.startswith("```") and normalized.endswith("```"):
            normalized = normalized.split("\n", 1)[1].rsplit("```", 1)[0]
        value = json.loads(normalized)
        if isinstance(value, dict) and isinstance(value.get("message"), str):
            if len(value["message"]) > self.protocol["max_public_message_characters"]:
                raise AuditMismatch("completed session contains overlong public message")
        return answer

    def finish(self):
        if self.used != len(self.keys):
            raise AuditMismatch("unexpected extra recorded calls in session")


def audit(root):
    manifest = json.loads((root / "manifest.json").read_text())
    protocol, errors = manifest["protocol"], []
    if protocol["name"] != "bonsai-negotiated-memory-discovery-v1":
        raise ValueError("wrong study protocol")
    protocol_hash = digest(manifest)
    # Replay uses the working engine, so do not silently replay a different version.
    for path, expected in manifest["sources"].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError("frozen source differs: " + path)
    calls = {p.stem: json.loads(p.read_text()) for p in (root / "calls").glob("*.json")}
    sessions = {p.stem: json.loads(p.read_text()) for p in (root / "sessions").glob("*.json")}
    for key, call in calls.items():
        request = call["request"]
        if call["protocol_hash"] != protocol_hash or digest(dict(request=request, protocol=protocol_hash)) != key:
            errors.append(key + ": call provenance mismatch")
        expected = {k: protocol["inference"][k] for k in ("max_tokens", "temperature", "top_p", "top_k", "min_p", "reasoning_effort")}
        expected.update(model=protocol["model"], enable_thinking=True, presence_penalty=0.0, repetition_penalty=1.0, prefill_step_size=512)
        if any(request.get(k) != v for k, v in expected.items()):
            errors.append(key + ": inference configuration mismatch")
        usage = call["response"]["usage"]
        if (len(call["prompt_token_ids"]) != usage["prompt_tokens"]
                or len(call["generated_token_ids"]) != usage["completion_tokens"]
                or usage["prompt_tokens"] > protocol["max_input_tokens"]
                or usage["completion_tokens"] > protocol["inference"]["max_tokens"]
                or call["cached_tokens"] != 0):
            errors.append(key + ": token/cache accounting mismatch")
    referenced, histories, branches, failures, pending = set(), [], [], [], []
    for key, session in sessions.items():
        referenced.update(session["call_keys"])
        if session["protocol_hash"] != protocol_hash:
            errors.append(key + ": session provenance mismatch")
        if session["status"] == "failed":
            last = calls.get(session["call_keys"][-1]) if session["call_keys"] else None
            failures.append(dict(session=key, error=session.get("error"), calls=len(session["call_keys"]),
                                 last_finish=last["response"]["choices"][0]["finish_reason"] if last else None,
                                 last_output_tokens=last["response"]["usage"]["completion_tokens"] if last else None,
                                 has_unsubmitted_request=session.get("unsubmitted_request") is not None))
    for index, data in enumerate(protocol["profiles"]):
        p = Profile(data["key"], {int(i): u for i, u in data["utilities"].items()}, data["formateur"])
        key = p.key + "-shared"
        shared = sessions.get(key)
        if shared is None:
            pending.append(key)
            continue
        if shared["status"] != "completed":
            continue
        try:
            replay = RecordedReplay(calls, shared["call_keys"], protocol, 92000 + index * 1000, "transcript")
            backend = GroundedInterface(replay)
            events = first_vote(backend, p, negotiate(backend, p))
            replay.finish()
            opportunity = mechanism_opportunity(p, events)
            if digest(events) != digest(shared["events"]) or digest(asdict(p)) != digest(shared["profile"]):
                raise AuditMismatch("saved history/profile differs from raw replay")
            if any(shared.get(k) != v for k, v in opportunity.items()):
                raise AuditMismatch("saved mechanism opportunity differs from replay")
            histories.append(dict(history=key, verified=True, **opportunity))
        except (ValueError, KeyError) as exc:
            errors.append(key + ": " + str(exc))
            continue
        for release in (False, True):
            for view in ("transcript", "event_index", "registry"):
                branch_key = f"{p.key}-release{int(release)}-{view}"
                saved = sessions.get(branch_key)
                if saved is None:
                    pending.append(branch_key)
                    continue
                if saved["status"] != "completed":
                    continue
                try:
                    replay = RecordedReplay(calls, saved["call_keys"], protocol,
                                            92500 + index * 1000 + int(release) * 100, view)
                    result = second_vote(GroundedInterface(replay), p, events, ledger=view == "registry", release=release)
                    replay.finish()
                    if digest(result) != digest({k: saved.get(k) for k in result}):
                        raise AuditMismatch("saved branch votes/state/payoffs differ from raw replay")
                    yes = sum(a["vote"] for a in result["actions"])
                    pivotal = [a["actor"] for a in result["actions"]
                               if ((yes - int(a["vote"]) + int(not a["vote"])) >= 4) != (yes >= 4)]
                    branches.append(dict(session=branch_key, verified=True, view=view, release=release,
                        pivotal_actors=pivotal, **{k: result[k] for k in ("due_count", "breaches", "obligation_errors",
                        "false_obligations", "correct_but_breached", "negative_unbound_votes", "second_passed", "realized_utility")}))
                except (ValueError, KeyError) as exc:
                    errors.append(branch_key + ": " + str(exc))
    errors.extend("missing call " + key for key in referenced - calls.keys())
    return dict(protocol_hash=protocol_hash, calls=len(calls), sessions=len(sessions),
        normal_calls=sum(c["response"]["choices"][0]["finish_reason"] == "stop" for c in calls.values()),
        generated_tokens=sum(c["response"]["usage"]["completion_tokens"] for c in calls.values()),
        generation_seconds=sum(c["elapsed_seconds"] for c in calls.values()),
        integrity_errors=errors, histories=histories, branches=branches, failures=failures,
        pending_sessions=pending, calls_not_yet_attached_to_sessions=sorted(calls.keys() - referenced),
        limitation="Completed-session raw replay only; failures retained but not imputed or fully replayed. No independent hardware/tokenizer verification. Three dependent-history clusters, not confirmatory evidence.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    print(json.dumps(audit(parser.parse_args().root), indent=2))
