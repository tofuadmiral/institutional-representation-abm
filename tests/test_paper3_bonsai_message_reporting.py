import copy
import json

from experiments import paper3_bonsai_budgeted_episode as old
from experiments import paper3_bonsai_message_reporting as study
from tests.test_paper3_bonsai_budgeted_episode import ScriptedNative, good_record


class ReportingNative(ScriptedNative):
    def __init__(self, bad_package=False, cutoff=False):
        super().__init__()
        self.bad_package, self.cutoff, self.records = bad_package, cutoff, {}

    def call(self, messages, seed, base):
        index = len(self.calls)
        assert seed == study.EPISODE_SEED + index
        key, record = super().call(messages, 113000 + index, base)
        if index == 5:
            record = good_record(dict(support=False, package=9 if self.bad_package else 2,
                                      first="A", message="x" * 477))
            if self.cutoff:
                record["response"]["choices"][0]["finish_reason"] = "length"
        record["request"] = old.request_for("model", messages, seed)
        self.records[key] = record
        return key, record


def test_new_profiles_and_seeds_without_changing_model_policy():
    cases, p = study.fixtures()
    assert p.key == "seed1301-leader0" and p.formateur == 0
    assert [c["seed"] for c in cases] == list(range(122000, 122004))
    assert [c["expected"]["accept"] for c in cases] == [True, False, False, True]
    assert {c["profile"]["key"] for c in cases}.isdisjoint(c["profile"]["key"] for c in old.fixtures()[0])
    assert old.CAP == 1536 and old.THINKING == 1024 and old.MAX_CALLS == 34


def test_overlong_message_preserved_into_history_and_auditable():
    native = ReportingNative()
    result = study.run_episode(study.EpisodeBackend(native, None), study.fixtures()[1])
    assert result["status"] == "completed" and len(native.calls) == 30
    assert result["overlong_message_count"] == 1
    assert next(x for x in result["message_lengths"] if x["exceeds_requested_limit"]) == dict(
        call_key="5", decision_index=5, characters=477, exceeds_requested_limit=True)
    # Full prose reaches the final-offer actor; it was not silently clipped.
    events = json.loads(native.calls[8][-1]["content"].split("\n")[0])["events"]
    responses = next(e["responses"] for e in events if e["type"] == "responses")
    assert responses[4]["message"] == "x" * 477
    assert "400 characters" in native.calls[5][-1]["content"]
    assert not result["first_passed"] and not result["second_passed"]
    from analysis.paper3_budgeted_episode_audit import Replay
    replay = Replay(dict(model="model"), native.records, result["call_keys"])
    assert study.run_episode(study.EpisodeBackend(replay, None), study.fixtures()[1]) == result
    bad = copy.deepcopy(native.records)
    bad["5"]["request"]["seed"] += 1
    replay = Replay(dict(model="model"), bad, result["call_keys"])
    assert study.run_episode(study.EpisodeBackend(replay, None), study.fixtures()[1])["status"] == "failed"


def test_action_invalidity_and_output_cutoff_still_abort_without_votes():
    for native in (ReportingNative(bad_package=True), ReportingNative(cutoff=True)):
        result = study.run_episode(study.EpisodeBackend(native, None), study.fixtures()[1])
        assert result["status"] == "failed" and len(native.calls) == 6
        assert "realized_utility" not in result and "actions" not in result


def test_predecessor_remains_strict():
    class OldNative(ReportingNative):
        def call(self, messages, seed, base):
            return super().call(messages, seed + 10000, base)
    native = OldNative()
    result = old.run_episode(old.EpisodeBackend(native, None), old.fixtures()[1])
    assert result["status"] == "failed"
    assert result["error"] == "public message exceeds frozen limit"
    assert len(native.calls) == 6
