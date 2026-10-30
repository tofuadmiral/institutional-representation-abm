"""Audit on a fabricated run only; not research evidence."""
import json

from analysis import paper3_deepseek_disclosure_audit as audit_mod
from experiments import paper3_deepseek_disclosure_a2 as run
from tests.test_paper3_deepseek_disclosure_a2 import fake_model, gen_ok, SECRET


def test_audit_complete_fabricated_run_and_detects_tampering(tmp_path):
    assert run.run_gate(tmp_path, SECRET, transport=fake_model, generation=gen_ok())["passed"]
    for i in range(run.SHARDS):
        run.run_shard(tmp_path, i, SECRET, transport=fake_model, generation=gen_ok())
    report = audit_mod.audit(tmp_path)
    assert report["integrity_errors"] == [] and report["complete_profiles"] == 4
    assert report["calls"] == 8 + 4 * 91 and report["transport_reissues"] == 0
    for entry in report["profiles"].values():
        low, high = entry["interaction_bounds"]["mean_regret"]
        assert low <= entry["interaction"]["mean_regret_interaction"] <= high
        assert low == high  # complete cells pin the bounds
    # Tamper with one recorded ratification card; the recomputed resolution must disagree.
    path = tmp_path / "profile-0/sessions/early-D.json"
    session = json.loads(path.read_text())
    selected = session["resolution"]["selected"]
    for action in session["actions"]:
        if action["stage"] == "ratification":
            action["action"]["votes"][selected] = False
    path.write_text(json.dumps(session))
    assert any("resolution mismatch" in e for e in audit_mod.audit(tmp_path)["integrity_errors"])


def test_incomplete_profile_gets_menu_bounds_not_imputation(tmp_path):
    assert run.run_gate(tmp_path, SECRET, transport=fake_model, generation=gen_ok())["passed"]
    run.run_shard(tmp_path, 0, SECRET, transport=fake_model, generation=gen_ok())
    path = tmp_path / "profile-0/sessions/early-B.json"
    session = json.loads(path.read_text())
    session.update(status="failed", error="fabricated failure")
    path.write_text(json.dumps(session))
    entry = audit_mod.audit(tmp_path)["profiles"]["0"]
    assert not entry["complete"] and "interaction" not in entry
    low, high = entry["interaction_bounds"]["mean_regret"]
    assert low < high


def test_audit_uses_the_runner_that_froze_the_run(tmp_path):
    from experiments import paper3_deepseek_disclosure_a3 as run3
    assert run3.run_gate(tmp_path, SECRET, transport=fake_model, generation=gen_ok())["passed"]
    assert audit_mod.runner_for(tmp_path) is run3
    report = audit_mod.audit(tmp_path)
    from decimal import Decimal
    assert Decimal(report["cumulative_additional_usd"]) == run3.PRIOR_ADDITIONAL_USD + Decimal(report["accounted_usd"])
    assert run3.PRIOR_ADDITIONAL_USD == Decimal("1.115910811")
