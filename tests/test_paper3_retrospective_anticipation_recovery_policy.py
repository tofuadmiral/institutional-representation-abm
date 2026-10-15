"""Offline synthetic error evidence only; no paid gate or provider proof."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from paper3 import retrospective_anticipation_recovery_policy as policy
from paper3 import retrospective_contract_recovery as predecessor
from tests.test_paper3_retrospective_contract_recovery import rejection


def plan(row=None, **options):
    args = dict(physical_attempt=1, block_reissues_used=0,
                block_started_unix=1000, detected_unix=1100)
    args.update(options)
    return policy.eligibility(rejection() if row is None else row, **args)


@pytest.mark.parametrize("attempt,delay", [(1, 300), (2, 600), (3, 1200)])
def test_three_distinct_cooldowns_reuse_evidence_without_changing_old_limits(attempt, delay):
    row = rejection()
    before = deepcopy(row)
    result = plan(row, physical_attempt=attempt)
    assert result["eligible"] and result["delay_seconds"] == delay
    assert result["not_before_unix"] == 1100 + delay
    assert result["deadline_unix"] == 87400
    assert row == before
    assert result["full_failed_reservation_retained"]
    assert result["original_attempt_must_be_retained"]
    assert not result["launch_authorized"] and not result["allocation_authorized"]
    assert not result["old_run_reopen_authorized"]
    assert not predecessor.eligibility(row, logical_attempt=2, recoveries_used=0)["eligible"]


@pytest.mark.parametrize("attempt", [0, 4, 5, -1, True, 1.0, None])
def test_per_action_limit(attempt):
    assert not plan(physical_attempt=attempt)["eligible"]


@pytest.mark.parametrize("used", [40, 41, -1, True, 1.0, None])
def test_block_limit(used):
    assert not plan(block_reissues_used=used)["eligible"]


def test_40th_reissue_allowed_but_not_41st():
    assert plan(block_reissues_used=39)["eligible"]
    assert not plan(block_reissues_used=40)["eligible"]


@pytest.mark.parametrize("field,value", [
    ("http_status", 402), ("http_status", 502), ("http_status", 429.0),
    ("lines", ["data: partial answer"]), ("byte_count", 1),
    ("generation_header", "known"), ("first_line_unix", 1100),
    ("secret_redacted", True), ("http_error_body_truncated", True),
])
def test_partial_unknown_or_credit_failure_never_retried(field, value):
    row = rejection()
    row["stream"][field] = value
    row["retryable"] = True
    assert not plan(row, physical_attempt=2)["eligible"]


@pytest.mark.parametrize("field,value", [
    ("limit_source", "account"), ("provider_name", "DeepInfra"),
    ("is_byok", True), ("raw", "Account credits exhausted"),
])
def test_exact_provider_error_required(field, value):
    row = rejection()
    error = json.loads(row["stream"]["http_error_body"])
    error["error"]["metadata"][field] = value
    row["stream"]["http_error_body"] = json.dumps(error)
    assert not plan(row)["eligible"]


@pytest.mark.parametrize("field,value", [
    ("receipts", [{"http_status": 404}]), ("instrument_error", "unknown"),
    ("reserved_usd", "0"), ("reserved_usd", "NaN"),
    ("status", "instrument_error"),
])
def test_billing_content_or_uncertain_instrument_not_retried(field, value):
    row = rejection()
    row[field] = value
    assert not plan(row)["eligible"]


@pytest.mark.parametrize("detected", [float("nan"), float("inf"), True, -1, 999])
def test_invalid_clock_is_not_recovery_authority(detected):
    assert not plan(detected_unix=detected)["eligible"]


def test_deadline_does_not_shorten_cooldown_or_authorize_admission_at_boundary():
    result = plan(physical_attempt=3, detected_unix=86200)
    assert not result["eligible"]
    assert result["not_before_unix"] == result["deadline_unix"] == 87400
    assert result["delay_seconds"] == 1200
    assert policy.admission_open(started_unix=1000, now_unix=87399)
    assert not policy.admission_open(started_unix=1000, now_unix=87400)
    with pytest.raises(ValueError):
        policy.admission_open(started_unix=1000, now_unix=999)


def test_identical_wire_and_seed_not_merely_equivalent_json():
    original = '{"model":"pinned","seed":7}'
    digest = sha256(original.encode()).hexdigest()
    assert policy.verify_identical_wire(original, original, digest)
    for other in ('{"seed":7,"model":"pinned"}', original.replace('7', '8')):
        with pytest.raises(ValueError):
            policy.verify_identical_wire(original, other, digest)
    with pytest.raises(ValueError):
        policy.verify_identical_wire(original, original, "0" * 64)


def test_slot_inventory_and_import_do_not_create_launch_authority():
    assert policy.physical_slots("case") == ("case-a1", "case-a2", "case-a3", "case-a4")
    assert policy.specification()["maximum_reissues_per_block"] == 40
    assert not policy.specification()["launch_authorized"]
    for key in ("../other", "a" * 97, True):
        with pytest.raises(ValueError):
            policy.physical_slots(key)
