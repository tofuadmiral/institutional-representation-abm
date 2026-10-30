"""Explicit billing-only amendment; frozen economic/validator code is reused.

Temporary receipt GET failures do not regenerate a model response. All four
scheduled observations are retained, and uncertified charges keep the full bound.
No archived response, verdict, ledger entry or source file is overwritten.
"""

from copy import deepcopy
from types import FunctionType, SimpleNamespace

from paper3 import hosted_reasoning_calls as base
from paper3 import retrospective_billing_calls as native
from paper3 import retrospective_billing_separation as previous
from paper3 import retrospective_deepinfra_classifier_v1 as classifier
from paper3 import retrospective_deepinfra_execution_v1 as engine
from paper3 import retrospective_deepinfra_failure_v1 as failure

VERSION = "receipt-get-transient-recovery-v1"
OFFSETS = previous.OFFSETS


def bind(function, **replacements):
    """Same code object; explicit dependency injection, no source/global mutation."""
    bound = FunctionType(function.__code__, dict(function.__globals__, **replacements),
                         function.__name__, function.__defaults__, function.__closure__)
    bound.__kwdefaults__ = function.__kwdefaults__
    return bound


def temporary(observation):
    if (observation.get("secret_redacted") is not False
            or observation.get("data") is not None):
        return False
    status, error = observation.get("http_status"), observation.get("error_type")
    return ((status is None and error in ("TimeoutError", "URLError",
                "ConnectionResetError", "RemoteDisconnected"))
            or (type(status) is int and status in (500, 502, 503, 504)
                and error == "HTTPError"))


def benign(observation):
    return previous.absent_observation(observation) or temporary(observation)


def assess(row, config):
    original = previous.assess(row, config)
    if original["passed"]:
        return original  # Existing valid evidence has exactly its old assessment.
    receipts = row.get("receipts", [])
    raw = base.assess(row, config)
    prefix = (1 <= len(receipts) <= 4
              and [o.get("scheduled_offset_seconds") for o in receipts]
              == OFFSETS[:len(receipts)])
    certified = (prefix and raw["passed"] and all(benign(o) for o in receipts[:-1])
                 and type(receipts[-1].get("http_status")) is int
                 and receipts[-1]["http_status"] == 200)
    absent = (prefix and len(receipts) == 4 and all(benign(o) for o in receipts)
              and raw["reasons"] == ["receipt:unavailable, invalid or conflicting"])
    # Partial streams, route/native/usage errors, authentication, malformed or
    # conflicting HTTP200 receipts never pass this narrower billing-only rule.
    if not (certified or absent):
        return original
    return dict(raw, passed=True, reasons=[], billing_passed=raw["passed"],
                billing_separation=dict(version=VERSION,
                    receipt_sequence_allowed=True, scientific_transport_passed=True,
                    uncertified_full_reservation=absent,
                    temporary_get_failures=sum(temporary(o) for o in receipts)))


service = SimpleNamespace(assess=assess, native_evidence=native.native_evidence)
classify_action = bind(classifier.classify, service=service)
classify = bind(failure.classify,
                previous=SimpleNamespace(classify=classify_action, CONFIG=classifier.CONFIG))
execute = bind(engine.execute, classify=classify)


class Calls(native.Calls):
    # Transport/POST/reservation code is the exact frozen code object. Only the
    # receipt continuation predicate and final billing assessor differ.
    one = bind(native.Calls.one, assess=assess, absent_observation=benign)


def recovered_view(row, supplement):
    """A derived, disclosed view; the historical raw row remains byte-identical."""
    view = deepcopy(row)
    view["receipts"] += deepcopy(supplement["observations"])
    view["assessment"] = assess(view, classifier.CONFIG)
    view["billing_recovery"] = dict(
        version=VERSION, amendment_protocol=supplement["amendment_protocol"],
        original=supplement["original"],
        original_assessment=deepcopy(row["assessment"]),
        original_result=deepcopy(row["result"]),
        historical_full_reservation_retained=True,
        no_model_request=True)
    return view
