"""Synthetic unit fixtures only: these never enter research output directories."""
import copy
from dataclasses import asdict
import json
import re
from types import SimpleNamespace
import pytest

from experiments.paper3_bonsai_memory_pilot import CollectiveBackend, admit_validation, study_profiles, mechanism_opportunity, frozen_store, MAX_MESSAGE, MAX_INPUT
from paper3.commitment_memory import ask, profile, negotiate, first_vote, second_vote, contract_state
from paper3.grounded_interface import GroundedInterface


def validation_report():
    return dict(integrity_errors=[], stages={s: dict(calls=n, valid=n, exact=n)
                for s, n in (("smoke", 1), ("private", 16), ("pivotal", 24))})


def test_frozen_profile_keys_resume_without_weakening_change_detection(tmp_path):
    protocol = dict(profiles=[asdict(p) for p in study_profiles()])
    first = frozen_store(tmp_path, protocol, [])
    expected_hash = first.protocol_hash
    first.lock.close()
    second = frozen_store(tmp_path, protocol, [])
    assert second.protocol_hash == expected_hash
    second.lock.close()
    changed = copy.deepcopy(protocol)
    changed["profiles"][0]["utilities"][0]["A0"] += 1
    with pytest.raises(ValueError, match="Protocol or source changed"):
        frozen_store(tmp_path, changed, [])


def test_admission_measures_state_errors_not_perfect_semantic_gate():
    report = validation_report()
    report["stages"]["pivotal"].update(valid=23, exact=0)
    admit_validation(report)
    for stage, changes in (("pivotal", dict(valid=22)), ("pivotal", dict(calls=23)),
                           ("private", dict(exact=15)), ("smoke", dict(exact=0))):
        invalid = copy.deepcopy(report)
        invalid["stages"][stage].update(changes)
        with pytest.raises(ValueError):
            admit_validation(invalid)
    report["integrity_errors"] = ["bad provenance"]
    with pytest.raises(ValueError):
        admit_validation(report)


class Tokenizer:
    def apply_chat_template(self, messages, **kwargs):
        assert kwargs["enable_thinking"] is True
        assert kwargs["reasoning_effort"] == "medium"
        return json.dumps(messages) + "<think>\n"

    def encode(self, prompt, **kwargs):
        return list(prompt.encode())


class NativeFixture:
    def __init__(self, answer='{"vote":false}', finish="stop"):
        self.processor = SimpleNamespace(tokenizer=Tokenizer())
        self.answer, self.finish, self.calls = answer, finish, []

    def call(self, messages, seed):
        self.calls.append((copy.deepcopy(messages), seed))
        return "unit-key", dict(response=dict(choices=[dict(finish_reason=self.finish,
            message=dict(content="unit reasoning fixture</think>" + self.answer))]))


def test_native_wrapper_preserves_negative_ballot_and_official_source_facts():
    native = NativeFixture()
    direct = CollectiveBackend(native, Tokenizer())
    direct.begin(92500, "event_index")
    backend = GroundedInterface(direct)
    result = ask(backend, profile(503), 3, [], 'Vote. Return {"vote":true}.', dict(vote=bool))
    assert result == dict(vote=False)
    messages, seed = native.calls[0]
    assert seed == 92500
    assert direct.call_keys == ["unit-key"]
    assert direct.pending_request is None
    assert "[THINK]" not in messages[0]["content"]
    assert "You may reason internally; output JSON only." not in messages[0]["content"]
    assert "principal 3" in messages[0]["content"]
    assert json.loads(messages[1]["content"].split("\n")[0])["event_index"] == []


@pytest.mark.parametrize("fenced", [False, True])
def test_public_message_limit_is_announced_and_rejects_without_repair(fenced):
    answer = json.dumps(dict(package=0, first="A", message="x" * (MAX_MESSAGE + 1)))
    if fenced:
        answer = "```json\n" + answer + "\n```"
    native = NativeFixture(answer)
    direct = CollectiveBackend(native, Tokenizer())
    with pytest.raises(ValueError, match="public message exceeds"):
        ask(GroundedInterface(direct), profile(503), 0, [],
            'Propose. Return {"package":0,"first":"A","message":"..."}.',
            dict(package=int, first=str, message=str))
    assert len(native.calls) == 1
    assert "at most 400 characters" in native.calls[0][0][-1]["content"]
    assert direct.call_keys == ["unit-key"]


def test_preflight_failure_preserves_unsubmitted_request_and_makes_no_call():
    native = NativeFixture()
    reference = SimpleNamespace(encode=lambda *args, **kwargs: [])
    direct = CollectiveBackend(native, reference)
    with pytest.raises(ValueError, match="tokenization differs"):
        ask(GroundedInterface(direct), profile(503), 0, [], 'Vote. Return {"vote":true}.', dict(vote=bool))
    assert not native.calls
    assert direct.pending_request[0]["role"] == "system"
    assert direct.call_keys == []


def test_context_cap_is_checked_before_inference():
    native = NativeFixture()
    native.processor.tokenizer.encode = lambda *args, **kwargs: [1] * (MAX_INPUT + 1)
    direct = CollectiveBackend(native, native.processor.tokenizer)
    with pytest.raises(ValueError, match="input exceeds"):
        ask(GroundedInterface(direct), profile(503), 0, [], 'Vote. Return {"vote":true}.', dict(vote=bool))
    assert not native.calls
    assert direct.pending_request is not None


class EngineFixture(NativeFixture):
    """Deterministic oracle for code testing, NEVER a research agent or observation."""
    def call(self, messages, seed):
        encoded, task = messages[-1]["content"].split("\n", 1)
        record = json.loads(encoded)
        actor = record["principal"]
        if "support (boolean)" in task:
            answer = dict(support=actor != 6, package=0, first="A", message="unit fixture")
        elif "package (integer" in task:
            answer = dict(package=0, first="A", message="unit fixture")
        elif "sign (boolean" in task:
            answer = dict(sign=actor != 6)
        elif "obligation_due (boolean" in task:
            state = contract_state(record["events"])
            due = actor in state["signers"] and state["status"] == "second_vote_due"
            project = re.search(r"Before voting on ([AB][01])", task)[1]
            gain = record["utilities_for_all_principals"][str(actor)][project]
            answer = dict(obligation_due=due, vote=due or gain > 0)
        else:
            assert "first project A0" in task
            answer = dict(vote=actor != 6)
        self.answer = json.dumps(answer)
        return super().call(messages, seed)


def test_three_history_pipeline_uses_195_calls_and_unforced_ballots():
    native = EngineFixture()
    direct = CollectiveBackend(native, Tokenizer())
    backend = GroundedInterface(direct)
    profiles = study_profiles()
    assert [p.formateur for p in profiles] == [0, 3, 6]
    assert len({p.key for p in profiles}) == 3
    for index, p in enumerate(profiles):
        direct.begin(92000 + index * 1000)
        history = first_vote(backend, p, negotiate(backend, p))
        assert len(direct.call_keys) == 23
        assert contract_state(history)["signers"] == list(range(6))
        assert mechanism_opportunity(p, history)["due_votes_can_change_passage"]
        alternative = copy.deepcopy(history)
        next(e for e in alternative if e["type"] == "final_offer")["package"] = 3
        next(e for e in alternative if e["type"] == "first_vote")["project"] = "A1"
        opportunity = mechanism_opportunity(p, alternative)
        assert opportunity["costly_due_signers"]
        assert not opportunity["due_votes_can_change_passage"]
        for release in (False, True):
            results = []
            for view in ("transcript", "event_index", "registry"):
                direct.begin(92500 + index * 1000 + int(release) * 100, view)
                result = second_vote(backend, p, history, ledger=view == "registry", release=release)
                assert len(direct.call_keys) == 7
                assert result["second_passed"] is not release
                assert result["due_count"] == (0 if release else 6)
                assert result["realized_utility"][6] == (-6 if release else -12)
                assert result["obligation_errors"] == 0
                results.append(result["realized_utility"])
            assert results[0] == results[1] == results[2]
    assert len(native.calls) == 195
