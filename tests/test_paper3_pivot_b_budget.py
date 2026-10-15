"""Fabricated spending only; separate from the actual $10 ledger."""
import json
import multiprocessing
from pathlib import Path

import pytest

from paper3.pivot_b_budget import BUDGET_ID, Ledger


@pytest.fixture
def ledger(tmp_path):
    (tmp_path/"authority.json").write_text(json.dumps(dict(
        budget_id=BUDGET_ID, cap_usd="10.00", credit_purchases_authorized=False)))
    obj = Ledger(tmp_path)
    obj.allocate("stage1", "1.50")
    return obj


def test_fresh_allowance_and_cross_stage_total(ledger):
    assert ledger.snapshot()["accounted_usd"] == "0"
    ledger.reserve("stage1", "a", "1.00", "a"*64)
    ledger.allocate("stage2", "9")
    ledger.reserve("stage2", "b", "9", "b"*64)
    assert ledger.snapshot()["remaining_usd"] == "0.00"
    with pytest.raises(ValueError, match="budget admission"):
        ledger.reserve("stage1", "c", ".01", "c"*64)


def test_uncertified_reservation_not_released(ledger):
    ledger.reserve("stage1", "a", ".5", "a"*64)
    with pytest.raises(ValueError, match="cannot be released"):
        ledger.settle("a", ".1", False, "b"*64)
    ledger.settle("a", ".5", False, "b"*64)
    assert ledger.snapshot()["accounted_usd"] == "0.5"
    assert ledger.snapshot()["uncertified"] == 1


def test_certified_charge_releases_only_own_reservation(ledger):
    ledger.reserve("stage1", "a", ".5", "a"*64)
    ledger.reserve("stage1", "b", ".5", "b"*64)
    ledger.settle("a", ".1", True, "c"*64)
    assert Ledger(ledger.root).snapshot()["accounted_usd"] == "0.6"
    assert ledger.snapshot()["pending"] == 1


def test_above_bound_charge_retained(ledger):
    ledger.reserve("stage1", "a", ".5", "a"*64)
    ledger.settle("a", "11", False, "b"*64)
    assert ledger.snapshot()["accounted_usd"] == "11"
    with pytest.raises(ValueError, match="budget admission"):
        ledger.reserve("stage1", "b", ".01", "b"*64)


def test_no_request_restart_or_double_settlement(ledger):
    ledger.reserve("stage1", "a", ".5", "a"*64)
    with pytest.raises(ValueError, match="already admitted"):
        ledger.reserve("stage1", "a", ".5", "a"*64)
    ledger.settle("a", ".1", True, "b"*64)
    with pytest.raises(ValueError, match="already recorded"):
        ledger.settle("a", "0", True, "b"*64)


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "0"])
def test_invalid_reservation(ledger, value):
    with pytest.raises(ValueError):
        ledger.reserve("stage1", "a", value, "a"*64)


def test_stage_cap_cannot_change(ledger):
    ledger.allocate("stage1", "1.5")
    with pytest.raises(ValueError):
        ledger.allocate("stage1", "3")


def test_partial_file_stops_admission(ledger):
    (ledger.root/"entries/a.partial").write_text("incomplete")
    with pytest.raises(ValueError, match="interrupted"):
        ledger.reserve("stage1", "a", ".5", "a"*64)


def reserve_in_process(root, n):
    obj = Ledger(root)
    try:
        obj.reserve("stage1", f"p{n}", ".40", str(n)*64)
        return True
    except ValueError:
        return False


def test_process_shared_admission_cannot_overspend(ledger):
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(4) as pool:
        passed = pool.starmap(reserve_in_process, [(str(ledger.root),i) for i in range(8)])
    assert sum(passed) == 3
    assert ledger.snapshot()["accounted_usd"] == "1.20"


def test_authority_cap_cannot_be_increased(ledger):
    p = ledger.root/"authority.json"
    value = json.loads(p.read_text()); value["cap_usd"] = "14.90"
    p.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="authority"):
        Ledger(ledger.root)
