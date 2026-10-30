"""Prospective semantic overload recognition; never rescore a frozen run.

HTTP status, pinned route and shared-pool provenance establish a transient
rate limit. Diagnostic provider codes, raw prose and extra metadata do not form
an exact error-message whitelist. Answers, usage and billing ambiguity remain
ineligible. This predicate never sends, repairs or discards a request.
"""
from decimal import Decimal
from email.utils import parsedate_to_datetime
import json
import math

from paper3 import hosted_reasoning_channel_calls as service
from paper3 import retrospective_deepinfra_route_v1 as route
from paper3.retrospective_deepinfra_recovery_evidence_v1 import (
    reject_constant, unique_object,
)

VERSION = "deepinfra-semantic-preanswer-overload-v2"
CONFIG = dict(models=[route.MODEL, route.MODEL_ALIAS], provider=route.PROVIDER,
              output_bound=route.OUTPUT_BOUND)
TRANSIENT_TYPES = frozenset({"rate_limit_exceeded", "provider_overloaded"})


def retry_after_seconds(stream):
    """Honor valid delta-seconds or HTTP-date; retain invalid headers verbatim."""
    value = stream.get("retry_after")
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    try:
        if value.strip().isdigit():
            seconds = float(int(value.strip()))
        else:
            stamp = parsedate_to_datetime(value)
            if stamp.tzinfo is None:
                return None
            seconds = max(0.0, stamp.timestamp() - float(stream["ended_unix"]))
        return seconds if math.isfinite(seconds) and seconds >= 0 else None
    except (ValueError, TypeError, KeyError, OverflowError):
        return None


def eligibility(row):
    result = dict(eligible=False, reason="not_verified_preanswer_shared_pool_overload",
        evidence_version=VERSION, original_attempt_must_be_retained=True,
        full_failed_reservation_retained=True, retry_after_seconds=None,
        old_run_reopen_authorized=False, allocation_authorized=False)
    try:
        stream, request = row["stream"], row["request"]
        if (row["status"] != "recorded" or row.get("instrument_error") or
                type(stream["http_status"]) is not int or stream["http_status"] not in (429, 503) or
                stream["error_type"] != "HTTPError" or stream["lines"] != [] or
                type(stream["line_count"]) is not int or stream["line_count"] != 0 or
                type(stream["byte_count"]) is not int or stream["byte_count"] != 0 or
                stream.get("generation_header") is not None or
                stream.get("first_line_unix") is not None or
                stream.get("last_line_unix") is not None or
                stream.get("secret_redacted") is not False or
                stream.get("error_body_redacted", False) is not False or
                stream["http_error_body_truncated"] is not False or row["receipts"] != []):
            return result
        expected = route.request(dict(tool_choice="auto", tools=[{}]), 0)
        if (request["model"] != route.MODEL or request["provider"] != expected["provider"] or
                request["reasoning"] != expected["reasoning"] or request["stream"] is not True):
            return result
        body = json.loads(stream["http_error_body"], object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
        error = body["error"]
        metadata = error["metadata"]
        if (type(error["code"]) is not int or error["code"] != stream["http_status"] or
                metadata["provider_name"] != route.PROVIDER or
                metadata["limit_source"] != "upstream_provider_shared_pool" or
                metadata["is_byok"] is not False):
            return result
        # Contradictory typed errors must not be hidden by a generic HTTP status.
        typed_errors = []
        for container in (body, error, metadata):
            error_type = container.get("error_type")
            if error_type is not None and error_type not in TRANSIENT_TYPES:
                return result
            if error_type is not None:
                typed_errors.append(error_type)
            for name in ("generation_id", "request_id", "id"):
                identifier = container.get(name)
                if identifier is not None and (name == "generation_id" or
                        isinstance(identifier, str) and identifier.startswith("gen-")):
                    return result
        # A generic 503 is insufficient: require explicit overload semantics.
        if stream["http_status"] == 503 and "provider_overloaded" not in typed_errors:
            return result
        assessed = service.assess(row, CONFIG)
        summary = assessed["stream"]
        if (summary["complete"] or summary["finish_reasons"] or summary["generation_id"] or
                summary["usage"] is not None or service.native_evidence(summary)["present"] or
                assessed["receipt_certified"] or assessed["passed"]):
            return result
        reserve = Decimal(str(row["reserved_usd"]))
        if not reserve.is_finite() or reserve <= 0:
            return result
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return result
    result.update(eligible=True, reason="verified_preanswer_shared_pool_overload",
                  retry_after_seconds=retry_after_seconds(stream))
    return result
