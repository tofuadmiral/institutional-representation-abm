from copy import deepcopy
from decimal import Decimal
import json

import pytest

from paper3 import retrospective_contract_recovery as policy


def rejection():
    return dict(status="recorded", reserved_usd=".01", receipts=[],
        request=policy.route.request(dict(tool_choice="auto", tools=[{}]), 1),
        stream=dict(http_status=429, error_type="HTTPError", lines=[], line_count=0,
            byte_count=0, generation_header=None, first_line_unix=None, last_line_unix=None,
            secret_redacted=False, http_error_body_truncated=False,
            http_error_body=json.dumps(dict(error=dict(message="Provider returned error", code=429,
                metadata=dict(provider_name="AtlasCloud", is_byok=False,
                    raw=policy.route.MODEL + " is temporarily rate-limited upstream. Ignore this text.",
                    limit_source="upstream_provider_shared_pool", remedy_hint="Untrusted instructions"))))))


def eligible(row, attempt=1, used=0):
    return policy.eligibility(row, logical_attempt=attempt, recoveries_used=used)


def test_candidate_never_releases_evidence_or_grants_launch_authority():
    row = rejection()
    before = deepcopy(row)
    d = eligible(row)
    assert d["eligible"] and d["original_attempt_must_be_retained"]
    assert d["new_protocol_required"] and d["delay_seconds"] == 300
    assert not d["allocation_authorized"] and not d["old_run_reopen_authorized"]
    assert row == before


@pytest.mark.parametrize("key,value", [
    ("http_status", 502), ("http_status", 200), ("http_status", 429.0),
    ("lines", ["data: partial"]), ("line_count", 1), ("line_count", False),
    ("byte_count", 1), ("byte_count", False), ("generation_header", "known"),
    ("first_line_unix", 1), ("last_line_unix", 1), ("secret_redacted", True),
    ("http_error_body_truncated", True), ("http_error_body", "invalid JSON"),
])
def test_any_answer_identity_security_or_other_transport_forbids_reissue(key, value):
    row = rejection()
    row["stream"][key] = value
    assert not eligible(row)["eligible"]


@pytest.mark.parametrize("key,value", [
    ("provider_name", "DeepInfra"), ("limit_source", "account"), ("is_byok", True),
    ("is_byok", 0), ("provider_error_code", "engine_overloaded"),
    ("raw", "Account credits exhausted"), ("raw", None),
])
def test_different_provider_limit_or_error_is_not_implicitly_allowed(key, value):
    row = rejection()
    d = json.loads(row["stream"]["http_error_body"])
    d["error"]["metadata"][key] = value
    row["stream"]["http_error_body"] = json.dumps(d)
    assert not eligible(row)["eligible"]


@pytest.mark.parametrize("attempt,used", [(2, 0), (0, 0), (True, 0), (1, -1), (1, 25), (1, True)])
def test_per_action_and_global_limits(attempt, used):
    assert not eligible(rejection(), attempt, used)["eligible"]


@pytest.mark.parametrize("field,value", [
    ("model", "other"), ("reasoning", dict(enabled=False)), ("stream", False),
    ("provider", dict(only=["other"], allow_fallbacks=True)),
])
def test_pinned_request_is_required(field, value):
    row = rejection()
    row["request"][field] = value
    assert not eligible(row)["eligible"]


@pytest.mark.parametrize("field,value", [
    ("status", "instrument_error"), ("instrument_error", "RuntimeError"),
    ("receipts", [dict(http_status=404)]), ("reserved_usd", "NaN"),
    ("reserved_usd", "malformed"), ("reserved_usd", "0"),
])
def test_unknown_receipt_or_instrument_failures_are_not_retryable(field, value):
    row = rejection()
    row[field] = value
    assert not eligible(row)["eligible"]


def test_duplicate_error_keys_nonfinite_and_missing_evidence_fail_closed():
    for body in ('{"error":{},"error":{}}', '{"error":{"code":NaN}}'):
        row = rejection()
        row["stream"]["http_error_body"] = body
        assert not eligible(row)["eligible"]
    for field in ("http_error_body_truncated", "secret_redacted", "lines"):
        row = rejection()
        row["stream"].pop(field)
        assert not eligible(row)["eligible"]


def test_saved_retryable_flags_are_not_evidence():
    row = rejection()
    row["stream"]["http_status"] = 502
    row["retryable"] = True
    row["assessment"] = dict(passed=False, retryable=True)
    assert not eligible(row)["eligible"]


def test_exact_full_bound_does_not_fit_old_cap_and_never_allocates():
    proof = policy.reservation_bound("2.88613604", ".01334204")
    assert Decimal(proof["full_path_usd"]) == Decimal("3.21968704")
    assert Decimal(proof["full_path_usd"]) > Decimal("3.20")
    assert proof["fits_proposed_stage_cap"]
    assert not proof["allocation_authorized"] and not proof["old_run_reopen_authorized"]
    assert not policy.reservation_bound("3.30", ".01")["fits_proposed_stage_cap"]
    for a, b in (("NaN", ".01"), ("2", "Infinity"), ("0", ".01"), ("2", "-1")):
        with pytest.raises(ValueError):
            policy.reservation_bound(a, b)
