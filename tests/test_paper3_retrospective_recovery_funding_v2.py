"""Synthetic account observations only; no credentials/network/ledger writes."""
from copy import deepcopy

import pytest

from paper3 import retrospective_recovery_funding_v2 as funding


def data():
    return dict(total_credits=25, total_usage=0), dict(limit=50, limit_remaining=50,
        is_free_tier=False, expires_at=None, label="DO NOT SAVE", creator_user_id="DO NOT SAVE")


def certify(credits=None, key=None, **kwargs):
    original = data()
    return funding.certify(original[0] if credits is None else credits,
        original[1] if key is None else key, "10.402212691",
        observed_unix=kwargs.pop("observed_unix", 1000), now_unix=kwargs.pop("now_unix", 1001), **kwargs)


def test_account_funding_is_not_new_authority_or_reconciliation():
    result = certify()
    assert result["account_remaining_usd"] == "25" and result["account_funded"]
    assert not result["research_authority_extended"] and not result["old_reservations_certified"]
    assert not result["credit_purchase"] and "DO NOT SAVE" not in str(result)


@pytest.mark.parametrize("field,value", (("total_credits", True), ("total_credits", "NaN"),
    ("total_usage", -1), ("total_usage", 20)))
def test_invalid_or_insufficient_account_credit_refused(field, value):
    credits, _ = data()
    credits[field] = value
    with pytest.raises(ValueError):
        certify(credits=credits)


@pytest.mark.parametrize("changes", (
    dict(limit_remaining=1), dict(limit_remaining=True), dict(limit_remaining="Infinity"),
    dict(is_free_tier=True), dict(limit=None, limit_remaining=50),
    dict(effective_budget=dict(remaining_usd=".2")), dict(budgets=[dict(remaining_usd=".2")]),
    dict(expires_at="1970-01-01T01:00:00Z"), dict(expires_at="2026-12-01T00:00:00")))
def test_applicable_key_restriction_cannot_be_ignored(changes):
    _, key = data()
    key.update(deepcopy(changes))
    with pytest.raises(ValueError):
        certify(key=key)


def test_unlimited_key_still_requires_account_funding_and_saves_no_token():
    _, key = data()
    key.update(limit=None, limit_remaining=None)
    assert certify(key=key)["key_remaining_usd"] is None
    with pytest.raises(ValueError):
        certify(credits=dict(total_credits=5, total_usage=0), key=key)


@pytest.mark.parametrize("observed,now", ((1000, 1061), (1001, 1000), (float("nan"), 1000), (True, 1000)))
def test_stale_or_invalid_observation_is_not_launch_funding(observed, now):
    with pytest.raises(ValueError):
        certify(observed_unix=observed, now_unix=now)
