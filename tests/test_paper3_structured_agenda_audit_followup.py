import copy
import json
import pytest
from analysis.paper3_structured_agenda_audit_followup import collect_schemas, reconcile
from experiments import paper3_bonsai_structured_agenda as study


def test_only_reproduced_ordering_failures_can_be_resolved():
    old = dict(integrity_errors=["raw a: "], tokenization_checks=2, grammar_path_checks=1)
    assert reconcile(old,{"a":"ordering"},{},2) == []
    extra = copy.deepcopy(old)
    extra["integrity_errors"].append("episode mismatch")
    assert "episode mismatch" in reconcile(extra,{"a":"ordering"},{},2)
    assert reconcile(old,{}, {},2)
    assert reconcile(old,{"a":"ordering"},{"a":"still invalid"},2)
    assert reconcile(old,{"a":"ordering","b":"unexplained"},{},2)
    missing = dict(old,tokenization_checks=1)
    assert reconcile(missing,{"a":"ordering"},{},2)


def test_runtime_schema_reconstructed_from_frozen_requests_not_saved_order():
    records = {}
    class Backend:
        def call(self, case, base):
            context = json.loads(case["messages"][-1]["content"].split("\n",1)[0])
            stage = context["stage"]
            reply = {"votes":{"p3":True}} if stage=="ratification" else {"policy_id":"p3"}
            if stage not in ("pairwise","ratification"):
                reply["message"] = "fixture"
            record = dict(cached_tokens=0,prompt_token_ids=[1],generated_token_ids=[2,3],
                boundary=dict(sampled_output_tokens=2,forced_output_tokens=0),
                request=study.request_for("fake",case),
                response=dict(usage=dict(prompt_tokens=1,completion_tokens=2),choices=[dict(
                    finish_reason="stop",message=dict(content="reason\n</think>\n"+json.dumps(reply)))]))
            key = str(len(records))
            records[key] = json.loads(json.dumps(record,sort_keys=True))
            return key, records[key]
    spec = study.specifications()[0]
    result = dict(study.run_one(Backend(),None,spec),protocol_hash="frozen")
    assert result["status"] == "completed"
    protocol = dict(model="fake",episodes=[spec])
    sessions = {spec["name"]:result}
    recovered = collect_schemas(protocol,"frozen",records,sessions)
    assert len(recovered)==25
    assert list(recovered["0"]["properties"]) == ["policy_id","message"]
    assert list(records["0"]["request"]["response_schema"]["properties"]) == ["message","policy_id"]
    assert recovered["0"] == records["0"]["request"]["response_schema"]
    records["0"]["request"]["response_schema"]["properties"]["message"]["type"] = "boolean"
    with pytest.raises(RuntimeError,match="request replay"):
        collect_schemas(protocol,"frozen",records,sessions)
