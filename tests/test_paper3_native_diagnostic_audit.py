"""Scorer fixtures only; never research observations."""
import json
import pytest

from analysis.paper3_native_diagnostic_audit import audit, design_coverage
from paper3.audit_runtime import digest


def test_coverage_does_not_count_three_views_as_three_opportunities():
    from experiments.paper3_bonsai_validation import stages
    report = design_coverage(stages()["pivotal"])
    assert report["base_cases"] == 8
    assert report["costly_due_cases"] == 1
    assert report["costly_unbound_cases"] == 4
    assert report["profitable_cases"] == 3
    assert all(len(row["views"]) == 3 for row in report["rows"])


def test_raw_audit_rejects_saved_success_for_truncation(tmp_path):
    expected = dict(principal_id=0, current_project_utility=-3, obligation_due=False, vote=False)
    case = dict(name="fixture", base_case="base", profile_seed=1, view="registry",
                messages=[], expected=expected, schema={k: type(v).__name__ for k, v in expected.items()})
    manifest = dict(protocol=dict(name="test-ministral", cases=[case]))
    protocol_hash = digest(manifest)
    (tmp_path / "sessions").mkdir()
    (tmp_path / "calls").mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    row = dict(protocol_hash=protocol_hash, expected=expected, status="completed",
               reply=expected, exact=True, call_keys=["call"])
    (tmp_path / "sessions/fixture.json").write_text(json.dumps(row))
    raw = dict(protocol_hash=protocol_hash, request=dict(messages=[]), response=dict(
        choices=[dict(finish_reason="length", message=dict(content='[THINK]unfinished'))],
        usage=dict(prompt_tokens=30, completion_tokens=20)), elapsed_seconds=1, peak_memory_gb=1)
    (tmp_path / "calls/call.json").write_text(json.dumps(raw))
    report = audit(tmp_path)
    assert report["views"]["registry"]["valid"] == 0
    assert report["views"]["registry"]["action_error"] == 1
    assert report["views"]["registry"]["harmful_unbound_yes"] == 0
    assert report["rows"][0]["marginal_payoff"] is None
    assert report["integrity_errors"] == ["fixture: saved score differs from raw response"]


@pytest.mark.parametrize("changes, action_error, state_error, harm", [
    ({"vote": True}, 1, 0, 1),
    ({"obligation_due": True}, 0, 1, 0),
    ({"obligation_due": True, "vote": True}, 1, 1, 1),
])
def test_raw_audit_separates_reported_state_from_action(tmp_path, changes, action_error, state_error, harm):
    expected = dict(principal_id=0, current_project_utility=-3, obligation_due=False, vote=False)
    reply = {**expected, **changes}
    case = dict(name="fixture", base_case="base", profile_seed=1, view="transcript",
                messages=[], expected=expected, schema={k: type(v).__name__ for k, v in expected.items()})
    manifest = dict(protocol=dict(name="bonsai2-test", stages=dict(pivotal=[case])))
    protocol_hash = digest(manifest)
    (tmp_path / "sessions").mkdir()
    (tmp_path / "calls").mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    row = dict(protocol_hash=protocol_hash, expected=expected, status="completed",
               reply=reply, exact=False, call_keys=["call"])
    (tmp_path / "sessions/fixture.json").write_text(json.dumps(row))
    raw = dict(protocol_hash=protocol_hash, request=dict(messages=[]), response=dict(
        choices=[dict(finish_reason="stop", message=dict(content='reasoning</think>' + json.dumps(reply)))],
        usage=dict(prompt_tokens=30, completion_tokens=20)), elapsed_seconds=1, peak_memory_gb=1)
    (tmp_path / "calls/call.json").write_text(json.dumps(raw))
    report = audit(tmp_path)
    assert report["integrity_errors"] == []
    counts = report["views"]["transcript"]
    assert counts["valid"] == 1
    assert counts["exact"] == 0
    assert counts["action_error"] == action_error
    assert counts["state_error"] == state_error
    assert counts["action_error_correct_state"] == int(action_error and not state_error)
    assert counts["state_error_correct_action"] == int(state_error and not action_error)
    assert counts["harmful_unbound_yes"] == harm
    assert report["rows"][0]["marginal_payoff"] == (-3 if harm else 0)
