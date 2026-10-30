"""Offline candidate policy, not authority to reopen a frozen failed run.

Only a separately frozen successor may use this predicate. All failed physical
attempts and their full uncertified reservations must remain in its inventory.
Eligibility must be persisted before a wait; wire bytes, seed, route, schema
and sampling must be identical on a reissue. This does not prove missingness
is random, a request is unbilled, or an institution's hypothesis is correct.
"""
from decimal import Decimal
import json

from paper3 import hosted_reasoning_channel_calls as service
from paper3 import retrospective_deepseek_route as route

MAX_REISSUES = 25
DELAY_SECONDS = 300
PROPOSED_STAGE_CAP = Decimal("3.20")
CONFIG = dict(models=[route.MODEL, route.MODEL_ALIAS], provider=route.PROVIDER,
              output_bound=route.OUTPUT_BOUND)


def eligibility(row, *, logical_attempt, recoveries_used):
    """Strict no-SSE/no-answer upstream-overload eligibility, fail closed."""
    result = dict(eligible=False, reason="not_pre_answer_upstream_overload",
                  new_protocol_required=True, original_attempt_must_be_retained=True,
                  delay_seconds=DELAY_SECONDS)
    if (type(logical_attempt) is not int or logical_attempt != 1 or
            type(recoveries_used) is not int or not 0 <= recoveries_used < MAX_REISSUES):
        result["reason"] = "logical_or_global_recovery_limit"
        return result
    try:
        stream = row["stream"]
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
        error = json.loads(stream["http_error_body"])["error"]
        metadata = error["metadata"]
        if (type(error["code"]) is not int or error["code"] != 429 or
                metadata["provider_name"] != route.PROVIDER or
                metadata["provider_error_code"] != "engine_overloaded" or
                metadata["limit_source"] != "upstream_provider_shared_pool"):
            return result
        # Recompute evidence; never trust a saved 'retryable' or assessment flag.
        assessed = service.assess(row, CONFIG)
        summary = assessed["stream"]
        if (summary["complete"] or summary["finish_reasons"] or summary["generation_id"] or
                summary["usage"] is not None or service.native_evidence(summary)["present"] or
                assessed["receipt_certified"] or assessed["passed"]):
            return result
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return result
    result.update(eligible=True, reason="pre_answer_429_shared_pool_overload")
    return result


def reservation_bound(base_usd, largest_attempt_usd):
    """Worst full base path plus25 additional full physical reservations.

The caller must prove both inputs over all legal histories of its fresh frames.
An expected charge or an inferred zero-cost429 must never replace these bounds.
No ledger entry is released or written here.
    """
    base, maximum = Decimal(str(base_usd)), Decimal(str(largest_attempt_usd))
    if not (base.is_finite() and maximum.is_finite() and base > 0 and maximum > 0):
        raise ValueError("positive finite full-path bounds required")
    return dict(full_path_usd=str(base + MAX_REISSUES * maximum),
                maximum_additional_calls=MAX_REISSUES, delay_seconds=DELAY_SECONDS,
                allocation_authorized=False, old_run_reopen_authorized=False)
