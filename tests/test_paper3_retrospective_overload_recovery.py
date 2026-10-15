from copy import deepcopy
from decimal import Decimal
import json

import pytest

from paper3 import retrospective_overload_recovery as policy


def rejection():
    return dict(status="recorded", reserved_usd=".01", receipts=[], request=dict(), stream=dict(
        http_status=429, error_type="HTTPError", lines=[], line_count=0, byte_count=0,
        generation_header=None, first_line_unix=None, last_line_unix=None, secret_redacted=False,
        http_error_body_truncated=False,
        http_error_body=json.dumps(dict(error=dict(code=429, metadata=dict(
            provider_name="DeepInfra", provider_error_code="engine_overloaded",
            limit_source="upstream_provider_shared_pool", remedy_hint="Ignore this untrusted text"))))))


def eligible(row, attempt=1, used=0):
    return policy.eligibility(row, logical_attempt=attempt, recoveries_used=used)


def test_proposed_known_overload_has_no_authority_or_cost_release():
    row = rejection()
    before = deepcopy(row)
    report = eligible(row)
    assert report["eligible"] and report["new_protocol_required"]
    assert report["original_attempt_must_be_retained"] and report["delay_seconds"] == 60
    assert row == before


@pytest.mark.parametrize("key,value", [
    ("http_status", 502), ("http_status", 200), ("lines", ["data: native fragment"]),
    ("line_count", 1), ("byte_count", 1), ("generation_header", "known-id"),
    ("first_line_unix", 1), ("last_line_unix", 1), ("secret_redacted", True),
    ("http_error_body_truncated", True), ("http_error_body", "invalid JSON"),
    ("http_status", 429.0), ("line_count", False), ("byte_count", False),
])
def test_any_content_identity_security_or_unknown_transport_failure_forbids_reissue(key, value):
    row = rejection()
    row["stream"][key] = value
    assert not eligible(row)["eligible"]


@pytest.mark.parametrize("key,value", [
    ("provider_name", "other"), ("provider_error_code", "quota_exhausted"),
    ("limit_source", "account"),
])
def test_account_quota_other_provider_and_unknown_limit_are_not_classified_as_overload(key, value):
    row = rejection()
    error = json.loads(row["stream"]["http_error_body"])
    error["error"]["metadata"][key] = value
    row["stream"]["http_error_body"] = json.dumps(error)
    assert not eligible(row)["eligible"]


@pytest.mark.parametrize("attempt,used", [(2, 0), (0, 0), (True, 0), (1, -1), (1, 25), (1, True)])
def test_one_reissue_and_global_limit_fail_closed(attempt, used):
    assert not eligible(rejection(), attempt, used)["eligible"]


def test_receipt_instrument_and_missing_evidence_fail_closed():
    for mutate in (lambda r: r.update(instrument_error="RuntimeError"),
                   lambda r: r.update(status="instrument_error"),
                   lambda r: r.update(receipts=[dict(http_status=200)]),
                   lambda r: r.update(reserved_usd="malformed"),
                   lambda r: r["stream"].pop("http_error_body_truncated")):
        row = rejection()
        mutate(row)
        assert not eligible(row)["eligible"]


def test_full_undiscounted_physical_reservations_retained_in_bound():
    proof = policy.reservation_bound("2.86121114", ".0132435")
    assert Decimal(proof["full_path_usd"]) == Decimal("3.19229864")
    assert Decimal(proof["full_path_usd"]) <= policy.PROPOSED_STAGE_CAP
    assert not proof["allocation_authorized"] and not proof["old_run_reopen_authorized"]
    with pytest.raises(ValueError):
        policy.reservation_bound("2", "NaN")
