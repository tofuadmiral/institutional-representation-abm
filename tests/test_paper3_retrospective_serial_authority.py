"""New serial/$10 authority tests: fabricated ledger only, no provider/key."""
from decimal import Decimal

import pytest

from experiments import paper3_retrospective_serial_live as live
from paper3.pivot_b_budget import BUDGET_ID, atomic
from paper3.retrospective_serial_execution import StopLedger


def test_new_approval_pins_serial_backoff_and_original_total():
    live.core.check_approval(live.APPROVAL)
    assert live.APPROVAL["response"] == "approved"
    assert live.APPROVAL["policy"]["workers"] == live.core.WORKERS == 1
    assert live.APPROVAL["policy"]["delay_seconds"] == 300
    assert live.APPROVAL["policy"]["cumulative_stop_usd"] == "10"
    assert live.APPROVAL["policy"]["stage_cap_usd"] == "3.20"
    assert live.APPROVAL["policy"]["authorized_batches"] == [0]
    assert live.core.STOP == Decimal("10")


def test_ten_dollar_transaction_keeps_older_reservations(tmp_path):
    root = tmp_path / "ledger"
    (root / "entries").mkdir(parents=True)
    atomic(root / "authority.json", dict(budget_id=BUDGET_ID, cap_usd="10.00",
                                        credit_purchases_authorized=False))
    old = root / "entries/old-pending.json"
    atomic(old, dict(stage="old", status="reserved", reserved_usd="8.30"))
    before = old.read_bytes()
    ledger = StopLedger(root)
    ledger.allocate("new", "1.70")
    ledger.reserve("new", "allowed", "1.70", "a" * 64)
    assert ledger.snapshot()["accounted_usd"] == "10.00"
    with pytest.raises(ValueError, match="ten-dollar"):
        ledger.reserve("new", "denied", ".01", "b" * 64)
    assert not (root / "entries/denied.json").exists()
    assert old.read_bytes() == before


def test_credits_or_total_authority_cannot_be_expanded(tmp_path):
    root = tmp_path / "ledger"
    root.mkdir()
    atomic(root / "authority.json", dict(budget_id=BUDGET_ID, cap_usd="11.00",
                                        credit_purchases_authorized=False))
    with pytest.raises(ValueError, match="authority mismatch"):
        StopLedger(root)
