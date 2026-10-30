"""Only synthetic test doubles in pytest temporary folders; no research data."""
from dataclasses import asdict
import json
import re
from types import SimpleNamespace

from experiments.paper3_bonsai_memory_pilot import (
    CollectiveBackend, frozen_store, study_profiles, mechanism_opportunity,
)
from paper3.audit_runtime import digest
from paper3.commitment_memory import negotiate, first_vote, second_vote, contract_state
from paper3.grounded_interface import GroundedInterface
from paper3_bonsai_memory_audit import audit


class Tokenizer:
    """Token-accounting placeholder for unit tests, never a real tokenizer."""
    def apply_chat_template(self, messages, **kwargs):
        return json.dumps(messages)

    def encode(self, prompt, **kwargs):
        return [1]


def test_raw_replay_detects_payoff_tampering_and_retains_pending_branches(tmp_path):
    p = study_profiles()[0]
    inference = dict(max_tokens=8192, temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, reasoning_effort="medium")
    protocol = dict(name="bonsai-negotiated-memory-discovery-v1", model="SYNTHETIC_UNIT_TEST_ONLY",
                    profiles=[asdict(p)], inference=inference, max_input_tokens=8192,
                    max_public_message_characters=400)
    store = frozen_store(tmp_path, protocol, [])

    class RecordingFixture:
        processor = SimpleNamespace(tokenizer=Tokenizer())

        def call(self, messages, seed):
            encoded, task = messages[-1]["content"].split("\n", 1)
            data = json.loads(encoded)
            actor = data["principal"]
            if "support (boolean)" in task:
                answer = dict(support=actor != 6, package=0, first="A", message="unit fixture")
            elif "package (integer" in task:
                answer = dict(package=0, first="A", message="unit fixture")
            elif "sign (boolean" in task:
                answer = dict(sign=actor != 6)
            elif "obligation_due (boolean" in task:
                state = contract_state(data["events"])
                due = actor in state["signers"] and state["status"] == "second_vote_due"
                project = re.search(r"Before voting on ([AB][01])", task)[1]
                answer = dict(obligation_due=due, vote=due or data["utilities_for_all_principals"][str(actor)][project] > 0)
            else:
                answer = dict(vote=actor != 6)
            response = dict(choices=[dict(finish_reason="stop", message=dict(content="unit fixture</think>" + json.dumps(answer)))])
            request = dict(messages=messages, seed=seed, model=protocol["model"], **inference,
                enable_thinking=True, presence_penalty=0.0, repetition_penalty=1.0, prefill_step_size=512)
            key = digest(dict(request=request, protocol=store.protocol_hash))
            record = dict(request=request, response={**response, "usage":dict(prompt_tokens=1, completion_tokens=1)},
                protocol_hash=store.protocol_hash, prompt_token_ids=[1], generated_token_ids=[2],
                cached_tokens=0, elapsed_seconds=0, origin="SYNTHETIC_UNIT_TEST_ONLY_NOT_MODEL_OUTPUT")
            store.save("calls", key, record)
            return key, record

    direct = CollectiveBackend(RecordingFixture(), Tokenizer())
    backend = GroundedInterface(direct)
    direct.begin(92000)
    events = first_vote(backend, p, negotiate(backend, p))
    history_key = p.key + "-shared"
    store.save("sessions", history_key, dict(status="completed", profile=asdict(p), events=events,
        **mechanism_opportunity(p, events), call_keys=list(direct.call_keys), protocol_hash=store.protocol_hash))
    direct.begin(92500, "event_index")
    branch = second_vote(backend, p, events, ledger=False, release=False)
    branch.update(status="completed", call_keys=list(direct.call_keys), protocol_hash=store.protocol_hash)
    key = p.key + "-release0-event_index"
    store.save("sessions", key, branch)
    report = audit(tmp_path)
    assert report["integrity_errors"] == []
    assert report["calls"] == 30
    assert len(report["histories"]) == len(report["branches"]) == 1
    assert report["branches"][0]["realized_utility"][6] == -12
    assert len(report["pending_sessions"]) == 5
    assert not report["calls_not_yet_attached_to_sessions"]
    path = tmp_path / "sessions" / (key + ".json")
    changed = json.loads(path.read_text())
    changed["realized_utility"]["0"] += 100
    path.write_text(json.dumps(changed))
    assert any("payoffs differ" in e for e in audit(tmp_path)["integrity_errors"])
