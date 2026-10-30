import copy
import json
from types import SimpleNamespace
import pytest
from experiments import paper3_bonsai_structured_agenda as study
from experiments import paper3_bonsai_agenda as previous
from analysis.paper3_structured_agenda_audit import Replay


def record(reply):
    return dict(cached_tokens=0, prompt_token_ids=[1], generated_token_ids=[2,3],
        boundary=dict(sampled_output_tokens=2,forced_output_tokens=0),
        response=dict(usage=dict(prompt_tokens=1,completion_tokens=2),choices=[dict(
            finish_reason="stop",message=dict(content="reason\n</think>\n"+json.dumps(reply)))]))


class FakeBackend:
    def __init__(self, invalid_at=None):
        self.cases, self.records, self.invalid_at = [], {}, invalid_at

    def call(self, case, base):
        context = json.loads(case["messages"][-1]["content"].split("\n",1)[0])
        stage = context["stage"]
        candidates = context.get("candidate_policy_ids", [p["policy_id"] for p in context["profile"]["catalog"]])
        policy = "p3" if "p3" in candidates else candidates[0]
        reply = {"votes":{p:True for p in candidates}} if stage == "ratification" else {"policy_id":policy}
        if stage not in ("ratification", "pairwise"):
            reply["message"] = "fixture"
        if len(self.cases) == self.invalid_at:
            reply = policy  # Never silently repair bare policy.
        key = str(len(self.cases))
        self.cases.append(copy.deepcopy(case))
        self.records[key] = dict(record(reply), request=study.request_for("fake",case))
        return key, self.records[key]


def test_only_interface_changes_and_new_seeds():
    for new, old in zip(study.specifications(), previous.specifications()):
        assert new["seed"] not in (old["seed"], 160000)
        assert {k:v for k,v in new.items() if k != "seed"} == {k:v for k,v in old.items() if k != "seed"}
    assert study.MAX_CALLS == 100
    assert len(study.specifications())*25 == study.MAX_CALLS


def test_all_stages_keep_full_legal_choices_and_no_answer_leak():
    profile = study.game.profiles()[0]
    for stage in ("opening","responses","locked_proposal","amendment","leader_selection","pairwise","ratification"):
        for candidates in (["p3"], ["p3","p6"]):
            messages = study.game.messages(profile,"B","r2",stage,[],candidates)
            original = copy.deepcopy(messages)
            case = study.case_for(messages,1)
            assert messages == original
            assert case["messages"][0] == original[0]
            assert case["messages"][-1]["content"].startswith(original[-1]["content"])
            schema = case["schema"]
            assert schema["additionalProperties"] is False
            if stage == "ratification":
                votes = schema["properties"]["votes"]
                assert votes["required"] == candidates
                assert all(v == {"type":"boolean"} for v in votes["properties"].values())
            else:
                assert schema["properties"]["policy_id"]["enum"] == candidates
                if stage != "pairwise":
                    assert schema["properties"]["message"] == {"type":"string"}
            assert study.request_for("fake",case)["enable_thinking"] is True


def test_complete_episodes_replay_exactly_and_hide_simultaneous_actions():
    for spec in study.specifications():
        backend = FakeBackend()
        result = study.run_one(backend,None,spec)
        assert result["status"] == "completed" and len(result["call_keys"]) == 25
        replay = Replay({"model":"fake"},backend.records,result,None,None)
        assert study.run_one(replay,None,spec) == result
        assert replay.position == 25
        contexts = [json.loads(c["messages"][-1]["content"].split("\n",1)[0]) for c in backend.cases]
        for stage in ("responses","pairwise","ratification"):
            group = [c for c in contexts if c["stage"] == stage]
            assert len(group) == 7
            assert all(c["official_events"] == group[0]["official_events"] for c in group)
            assert all(e["stage"] != stage for e in group[0]["official_events"])
        backend.records["0"]["request"]["seed"] += 1
        with pytest.raises(RuntimeError,match="request replay"):
            study.run_one(Replay({"model":"fake"},backend.records,result,None,None),None,spec)


def test_failure_retained_without_policy_or_retry():
    backend = FakeBackend(invalid_at=10)
    result = study.run_one(backend,None,study.specifications()[0])
    assert result["status"] == "failed" and len(result["call_keys"]) == 11
    assert "resolution" not in result and "metrics" not in result
    assert study.run_one(Replay({"model":"fake"},backend.records,result,None,None),None,study.specifications()[0]) == result


def test_call_cap_and_interrupted_marker_precede_generation(tmp_path):
    # Imports are mocked so this test never touches Metal or loads model weights.
    import sys
    from unittest.mock import patch
    core = SimpleNamespace()
    modules = {"mlx":SimpleNamespace(core=core), "mlx.core":core,
        "mlx_vlm":SimpleNamespace(stream_generate=None),
        "mlx_vlm.structured":SimpleNamespace(ThinkingAwareLogitsProcessor=None,build_json_schema_logits_processor=None)}
    calls = tmp_path / "calls"
    calls.mkdir()
    case = study.case_for(study.game.messages(study.game.profiles()[0],"D","r0","opening",[]),171000)
    store = SimpleNamespace(root=tmp_path,protocol_hash="frozen")
    fake = SimpleNamespace(path="fake",store=store)
    for i in range(100):
        (calls / f"{i}.json").write_text("{}")
    with patch.dict(sys.modules,modules):
        with pytest.raises(ValueError,match="call limit"):
            study.StructuredBackend.call(fake,case,None)
        key = study.digest(dict(request=study.request_for("fake",case),protocol="frozen"))
        (calls / (key+".json")).write_text(json.dumps({"status":"started"}))
        with pytest.raises(RuntimeError,match="not retried"):
            study.StructuredBackend.call(fake,case,None)
