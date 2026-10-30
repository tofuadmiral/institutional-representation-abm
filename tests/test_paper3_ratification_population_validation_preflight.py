"""Offline full-path and stop checks; no hosted requests."""
from __future__ import annotations

from decimal import Decimal

import pytest

from paper3 import ratification_population_validation_preflight as preflight


def test_complete_holdout_inventory_and_reservations():
    assert preflight.verify_inventory() == {
        "batch_1_calls": 512, "batch_2_calls": 448,
        "validation_calls": 960, "discovery_overlap": 0,
        "within_holdout_overlap": 0,
    }
    first, second = (preflight.scripted_preflight(batch) for batch in (1, 2))
    assert first["games"] == list(range(9, 17))
    assert second["games"] == list(range(17, 24))
    assert first["assigned_episodes"] == 32
    assert second["assigned_episodes"] == 28
    assert Decimal(first["reservation_usd"]) == Decimal("3.02458112")
    assert Decimal(second["reservation_usd"]) == Decimal("2.64645152")


def test_budget_stop_is_conservative_and_requires_no_pending_calls():
    snapshot = dict(accounted_usd="4.50", pending=0)
    assert preflight.check_budget(snapshot, 1)[
        "conservative_after_cap_usd"] == "7.60"
    assert preflight.check_budget(snapshot, 2)[
        "conservative_after_cap_usd"] == "7.22"
    with pytest.raises(ValueError, match="stop"):
        preflight.check_budget(dict(accounted_usd="4.91", pending=0), 1)
    with pytest.raises(ValueError, match="pending"):
        preflight.check_budget(dict(accounted_usd="4.00", pending=1), 2)
