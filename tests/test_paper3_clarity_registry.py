import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments import paper3_bonsai_clarity_registry as study
from paper3.audit_runtime import digest
from paper3.commitment_memory import PACKAGES, contract_state, project_sequence
from tests.test_paper3_bonsai_budgeted_episode import good_record


def fixture():
    events = [dict(type="final_offer", offer_id="final-2", package=1, first="B"),
        dict(type="ratification", offer_id="final-2", signatures=[True, True, True, False, True, False, False]),
        dict(type="first_vote", project="B1", passed=True, votes=[True, True, False, True, True, True, True])]
    ua, ub = [11, 8, 11, -5, -2, -4, -6], [-1, -1, -2, 8, 9, 8, 2]
    utilities = {str(i): dict(A0=ua[i], B1=ub[i]) for i in range(7)}
    episode = dict(status="completed", events=events, call_keys=[str(i) for i in range(30)],
                   profile=dict(utilities=utilities))
    records = {}
    for actor in range(7):
        context = dict(representative=actor, principal=actor, utilities_for_all_principals=utilities,
            events=events, package_menu={str(i): list(pair) for i, pair in enumerate(PACKAGES)})
        messages = [dict(role="system", content="unchanged rules"),
            dict(role="user", content=json.dumps(context, sort_keys=True) + "\nBefore voting on A0, unchanged task")]
        row = good_record(dict(obligation_due=False, vote=actor in (1, 2, 4)))
        row["request"] = study.old.request_for("model", messages, 123023 + actor)
        records[str(23 + actor)] = row
    return records, episode


def test_exact_controls_rotation_unique_requests_and_budget():
    records, episode = fixture()
    cases = study.cases_for(records, episode)
    assert len(cases) == 28 and study.MAX_CALLS * study.old.CAP == 43008
    assert len({digest(study.old.request_for("model", c["messages"], c["seed"])) for c in cases}) == 28
    for actor in range(7):
        subset = [c for c in cases if c["actor"] == actor]
        offset = actor % 4
        assert [(c["clear"], c["registry"]) for c in subset] == list(study.CELLS[offset:] + study.CELLS[:offset])
        for c in subset:
            assert c["seed"] == 123023 + actor
            if not c["clear"] and not c["registry"]:
                assert study.old.request_for("model", c["messages"], c["seed"]) == records[c["original_key"]]["request"]


def test_transforms_only_designated_fields_preserve_events_and_task():
    records, episode = fixture()
    saved = copy.deepcopy(records)
    for case in study.cases_for(records, episode):
        original = records[case["original_key"]]["request"]["messages"]
        old_record, old_task = original[-1]["content"].split("\n", 1)
        new_record, new_task = case["messages"][-1]["content"].split("\n", 1)
        old_record, new_record = json.loads(old_record), json.loads(new_record)
        assert old_task == new_task
        assert case["messages"][0]["content"] == original[0]["content"] + ("\n" + study.CLARIFICATION if case["clear"] else "")
        if case["clear"]:
            assert new_record.pop("package_menu") == {str(i): dict(A=a, B=b) for i, (a, b) in enumerate(PACKAGES)}
            old_record.pop("package_menu")
        if case["registry"]:
            assert new_record.pop("derived_registry") == contract_state(episode["events"])
        assert old_record == new_record
    assert records == saved
    # Exhaust all package/order combinations: category keys never set vote order.
    for package in range(4):
        for first in ("A", "B"):
            messages = copy.deepcopy(records["23"]["request"]["messages"])
            record, task = messages[-1]["content"].split("\n", 1)
            record = json.loads(record)
            record["events"][0].update(package=package, first=first)
            messages[-1]["content"] = json.dumps(record) + "\n" + task
            changed = json.loads(study.transform(messages, True, True)[-1]["content"].split("\n", 1)[0])
            a, b = PACKAGES[package]
            assert project_sequence(changed["events"]) == ((a, b) if first == "A" else (b, a))


def test_strict_schema_invalid_output_and_control_stability():
    originals, episode = fixture()
    c = study.cases_for(originals, episode)[0]
    original = originals[c["original_key"]]
    result = study.score(original, c, original)
    assert result["state_correct"] and not result["preference_consistent"]
    assert all(result["control_replay"].values())
    changed = copy.deepcopy(original)
    changed["generated_token_ids"][0] = 123
    assert not study.score(changed, c, original)["control_replay"]["generated_tokens_identical"]
    for reply in (dict(obligation_due=0, vote=True), dict(obligation_due=False, vote=1),
                  dict(obligation_due=False, vote=True, extra=1), {}):
        row = good_record(reply)
        row["request"] = original["request"]
        assert study.score(row, c, original)["status"] == "failed"
    for finish, content in (("length", "unclosed"), ("stop", '<think>bad</think>{}')):
        row = copy.deepcopy(original)
        row["response"]["choices"][0].update(finish_reason=finish, message=dict(content=content))
        assert study.score(row, c, original)["status"] == "failed"


def test_complete_cell_pivotality_and_no_imputed_outcomes():
    originals, episode = fixture()
    cases = study.cases_for(originals, episode)
    sessions = {c["name"]: study.score(originals[c["original_key"]], c, originals[c["original_key"]]) for c in cases}
    cells = study.aggregate(cases, sessions, episode)
    cell = cells["clear0-registry0"]
    assert cell["votes"] == [False, True, True, False, True, False, False]
    assert cell["total_utility"] == 23 and cell["state_correct"] == 7 and cell["preference_consistent"] == 5
    assert cell["ballot_flips"][0]["own_utility_gain_if_flipped"] == 11
    assert cell["ballot_flips"][4]["own_utility_gain_if_flipped"] == 0
    assert not cell["ballot_flips"][4]["policy_pivotal"]
    sessions[cases[0]["name"]] = dict(status="failed")
    cell = study.aggregate(cases, sessions, episode)["clear0-registry0"]
    assert not cell["outcomes_available"] and cell["invalid_or_missing"] == 1
    assert "votes" not in cell and "realized_utilities" not in cell
    del sessions[cases[0]["name"]]
    assert not study.aggregate(cases, sessions, episode)["clear0-registry0"]["outcomes_available"]


def test_live_promise_not_scored_as_unbound_preference_error():
    originals, episode = fixture()
    c = study.cases_for(originals, episode)[0]
    context, task = c["messages"][-1]["content"].split("\n", 1)
    context = json.loads(context)
    context["events"][-1]["votes"][2] = True
    c["messages"][-1]["content"] = json.dumps(context) + "\n" + task
    scored = study.score(originals["23"], c, originals["23"])
    assert scored["expected_obligation_due"] and not scored["state_correct"]
    assert scored["preference_consistent"] is None


def test_backend_28_call_limit_before_model_import(tmp_path):
    (tmp_path / "calls").mkdir()
    for i in range(28):
        (tmp_path / "calls" / f"{i}.json").touch()
    backend = study.DiagnosticBackend.__new__(study.DiagnosticBackend)
    backend.path = Path("model")
    backend.store = SimpleNamespace(root=tmp_path, protocol_hash="test")
    with pytest.raises(ValueError, match="28-call"):
        backend.call([], 1, None)
