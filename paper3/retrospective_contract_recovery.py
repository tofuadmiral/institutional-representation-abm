"""Prospective AtlasCloud pre-answer rate-limit policy; offline only.

Never attach this policy to a started or closed run. Failed physical requests
and their reservations remain evidence, even when a subsequent attempt works.
Eligibility is not proof of nonbilling, random missingness or model reliability.
No allocation, inference, fallback or change to the institution occurs here.
"""
from decimal import Decimal
import json

from paper3 import hosted_reasoning_channel_calls as service
from paper3 import retrospective_contract_route_v2 as route

MAX_REISSUES = 25
DELAY_SECONDS = 300
PROPOSED_STAGE_CAP = Decimal("3.30")
CONFIG = dict(models=[route.MODEL, route.MODEL_ALIAS], provider=route.PROVIDER,
              output_bound=route.OUTPUT_BOUND)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate error key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("nonfinite error value")


def eligibility(row, *, logical_attempt, recoveries_used):
    """Fail closed on anything but the pinned, answerless shared-pool error."""
    result = dict(eligible=False, reason="not_pinned_pre_answer_shared_pool_429",
                  new_protocol_required=True, original_attempt_must_be_retained=True,
                  delay_seconds=DELAY_SECONDS, allocation_authorized=False,
                  old_run_reopen_authorized=False)
    if (type(logical_attempt) is not int or logical_attempt != 1 or
            type(recoveries_used) is not int or not 0 <= recoveries_used < MAX_REISSUES):
        result["reason"] = "logical_or_global_recovery_limit"
        return result
    try:
        stream, request = row["stream"], row["request"]
        if (row["status"] != "recorded" or row.get("instrument_error") or
                type(stream["http_status"]) is not int or stream["http_status"] != 429 or
                stream["error_type"] != "HTTPError" or stream["lines"] != [] or
                type(stream["line_count"]) is not int or stream["line_count"] != 0 or
                type(stream["byte_count"]) is not int or stream["byte_count"] != 0 or
                stream.get("generation_header") is not None or
                stream.get("first_line_unix") is not None or stream.get("last_line_unix") is not None or
                stream.get("secret_redacted") is not False or
                stream["http_error_body_truncated"] is not False or row["receipts"] != []):
            return result
        expected = route.request(dict(tool_choice="auto", tools=[{}]), 0)
        if (request["model"] != route.MODEL or request["provider"] != expected["provider"] or
                request["reasoning"] != expected["reasoning"] or request["stream"] is not True):
            return result
        error = json.loads(stream["http_error_body"], object_pairs_hook=unique_object,
                           parse_constant=reject_constant)["error"]
        metadata = error["metadata"]
        if (type(error["code"]) is not int or error["code"] != 429 or
                error["message"] != "Provider returned error" or
                metadata["provider_name"] != route.PROVIDER or
                metadata["limit_source"] != "upstream_provider_shared_pool" or
                metadata["is_byok"] is not False or "provider_error_code" in metadata or
                not isinstance(metadata["raw"], str) or
                not metadata["raw"].startswith(route.MODEL + " is temporarily rate-limited upstream.")):
            return result
        # Do not trust saved assessment/result flags or error-body instructions.
        assessed = service.assess(row, CONFIG)
        summary = assessed["stream"]
        if (summary["complete"] or summary["finish_reasons"] or summary["generation_id"] or
                summary["usage"] is not None or service.native_evidence(summary)["present"] or
                assessed["receipt_certified"] or assessed["passed"]):
            return result
        amount = Decimal(str(row["reserved_usd"]))
        if not amount.is_finite() or amount <= 0:
            return result
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return result
    result.update(eligible=True, reason="pinned_pre_answer_429_shared_pool")
    return result


def reservation_bound(base_usd, largest_attempt_usd):
    """Full base path plus 25 undiscounted physical-attempt reservations.

    Fresh-case callers must independently prove both inputs over legal histories.
    Returning a bound does not allocate it or promise that a later block fits.
    """
    base, maximum = Decimal(str(base_usd)), Decimal(str(largest_attempt_usd))
    if not (base.is_finite() and maximum.is_finite() and base > 0 and maximum > 0):
        raise ValueError("positive finite full-path bounds required")
    full = base + MAX_REISSUES * maximum
    return dict(full_path_usd=str(full), fits_proposed_stage_cap=full <= PROPOSED_STAGE_CAP,
                proposed_stage_cap_usd=str(PROPOSED_STAGE_CAP), maximum_additional_calls=MAX_REISSUES,
                delay_seconds=DELAY_SECONDS, allocation_authorized=False,
                old_run_reopen_authorized=False)
