"""Production-admission checks; all calls fabricated, never reads the real key."""
from copy import deepcopy
from decimal import Decimal
import time

import pytest

from experiments import paper3_retrospective_overload_live as live
from paper3.pivot_b_budget import BUDGET_ID, atomic
from tests.test_paper3_retrospective_deepseek_gate import endpoint
from tests.test_paper3_retrospective_overload_discovery import fake, replay


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(live.core.requests, "seed_audit", lambda _: dict(overlap=[], historical_files=0))
    ledger = tmp_path / "ledger"
    (ledger / "entries").mkdir(parents=True)
    atomic(ledger / "authority.json", dict(budget_id=BUDGET_ID, cap_usd="10.00", credit_purchases_authorized=False))
    atomic(ledger / "entries/old.json", dict(stage="old", status="reserved", reserved_usd=".01"))
    root = tmp_path / "run"
    protocol = live.prepare(root, ledger, metadata=endpoint(), observed=time.time())
    return root, ledger, protocol


def test_approval_gate_closure_and_no_calls_or_allocations_at_freeze(prepared):
    root, ledger, _ = prepared
    manifest, _ = live.core.verify(root)
    protocol = manifest["protocol"]
    assert protocol["paid_launch_authorized"] and not protocol["integration_only"]
    assert protocol["human_approval"] == live.APPROVAL and protocol["new_gate_calls"] == 0
    assert protocol["qualification_proof"]["exact_offline_replay"]
    assert len(protocol["assignments"]) == 16
    assert "experiments/paper3_retrospective_overload_live.py" in manifest["sources"]
    assert not (ledger / "stages").exists()
    assert not list(root.rglob("calls/*.json"))


def test_wrong_protocol_stops_before_endpoint_or_key(prepared, monkeypatch):
    def forbidden():
        pytest.fail("network or key access before protocol admission")
    monkeypatch.setattr(live, "endpoint", forbidden)
    monkeypatch.setattr(live.core.t, "read_key", forbidden)
    with pytest.raises(ValueError, match="unexpected protocol"):
        live.execute(prepared[0], 0, prepared[1], expected_protocol="wrong")


def test_production_requires_fresh_observation_before_allocating(prepared):
    root, ledger, _ = prepared
    with pytest.raises(ValueError, match="fresh production metadata"):
        live.core.execute(root, 0, ledger, metadata=endpoint(), send=lambda *_: None, lookup=lambda *_: None)
    assert not (ledger / "stages").exists()


def test_live_mode_fabricated_first_block_exact_isolated_replay(prepared, tmp_path):
    terminal, sent = fake(prepared, faults={1: "429"})
    report = live.core.audit(*prepared[:2])
    assert terminal["serial_episode_passed"] and len(sent) == 241 and report["completed"] == 8
    assert report["paid_launch_authorized"] and not report["integration_only"]
    assert not report["publication_evidence"] and report["selected_case_screen"]["verdict"] == "incomplete"
    assert Decimal(report["accounted_usd"]) > Decimal(".024")
    assert replay(prepared, tmp_path, "production-mode")["paid_launch_authorized"]


@pytest.mark.parametrize("key,value", [("delay_seconds", 0), ("retry_bad_answers", True),
                                      ("cumulative_stop_usd", "10")])
def test_approval_never_expands_retry_content_or_financial_scope(key, value):
    changed = deepcopy(live.APPROVAL)
    changed["policy"][key] = value
    with pytest.raises(ValueError, match="scope changed"):
        live.core.check_approval(changed)
