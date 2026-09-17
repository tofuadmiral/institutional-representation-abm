import importlib.util
import json
from pathlib import Path


def test_capability_audit_keeps_failed_cases_in_denominator(tmp_path):
    spec = importlib.util.spec_from_file_location("pilot_audit", Path(__file__).parents[1] / "analysis/paper3_pilot_audit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "sessions").mkdir()
    (tmp_path / "calls").mkdir()
    expected = dict(accept=False, principal_utility_if_accepted=-3)
    for i, row in enumerate([
        dict(status="completed", reply=dict(accept=True, principal_utility_if_accepted=-3)),
        dict(status="failed", error="length"),
    ]):
        record = dict(row, expected=expected, stage="paired", thinking=True, call_keys=[])
        (tmp_path / "sessions" / f"{i}.json").write_text(json.dumps(record))
    summary = module.audit(tmp_path)["capability"][0]
    assert summary == dict(stage="paired", thinking=True, n=2, exact=0, action_correct=0,
                           utility_correct=1, harmful_cases=2, harmful_accepted=1, failures=1)
