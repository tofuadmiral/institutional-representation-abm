"""Prospective, content-blind transport eligibility; no network or execution.

Not applicable to any closed gate. A future gate must separately freeze fresh
cases, at most two recoveries total and one per case, identical request bytes,
both reservations, independent audit and budget before using this policy.
Incomplete EOF's cause may be unknown. Recovery is not evidence it was random.
"""
import json

from paper3 import hosted_reasoning_calls as transport

MAX_RECOVERIES = 2
MAX_ATTEMPTS_PER_CASE = 2
REISSUE_DELAY_SECONDS = 30
TRANSIENT_HTTP = frozenset((408, 429, 500, 502, 503, 504))
TRANSIENT_EXCEPTIONS = frozenset(("TimeoutError", "ConnectionResetError",
                                "RemoteDisconnected", "IncompleteRead", "URLError", "HTTPError"))


def pre_answer_only(trace):
    """Inspect envelope keys, never decode/score actual tool arguments/content.

Recover no final-content or tool-call fragments, even without a finish marker.
This deliberately excludes ambiguous partially delivered answers. Native
reasoning alone is not a controller action. Mirror the existing SSE grouping.
"""
    pending = []
    for line in [*trace["lines"], ""]:
        if line.startswith("data:"):
            pending.append(line[5:].lstrip(" "))
        elif not line and pending:
            payload, pending = "\n".join(pending), []
            if payload == "[DONE]":
                continue
            frame = json.loads(payload)
            for choice in frame.get("choices") or []:
                if type(choice.get("index")) is not int or choice["index"] != 0:
                    return False
                delta = choice.get("delta") or {}
                if not isinstance(delta, dict):
                    return False
                if any(delta.get(key) for key in ("content", "tool_calls", "function_call", "refusal")):
                    return False
    return True


def eligibility(row, config, *, attempt_number, recoveries_used):
    """Inspect framing, identity and safety only; never read an answer or score.

Completed/length/errored-terminal responses never qualify, even if wrong,
invalid, lack reasoning, have bad billing or contain unusable tool arguments.
No successful finish marker may be discarded to obtain a different sample.
The caller must separately enforce request identity, costs and source closure.
"""
    if (type(attempt_number) is not int or attempt_number != 1 or
            type(recoveries_used) is not int or not 0 <= recoveries_used < MAX_RECOVERIES):
        return dict(eligible=False, reason="attempt_or_global_limit")
    if row.get("instrument_error") or not isinstance(row.get("stream"), dict):
        return dict(eligible=False, reason="instrument_or_missing_trace")
    trace = row["stream"]
    if trace.get("secret_redacted") or trace.get("error_body_redacted"):
        return dict(eligible=False, reason="redaction_or_safety")
    summary = transport.stream_summary(trace, config)
    if summary["complete"] or summary["finish_reasons"] or summary["done_markers"]:
        return dict(eligible=False, reason="terminal_response_not_recoverable")
    if summary["malformed_frames"] or summary["error_frames"] or summary["frames_after_done"]:
        return dict(eligible=False, reason="malformed_or_explicit_error_frame")
    if not pre_answer_only(trace):
        return dict(eligible=False, reason="answer_fragment_or_choice_conflict")
    if (len(summary["ids"]) > 1 or len(summary["models"]) > 1 or
            not set(summary["models"]) <= set(config["models"]) or
            not set(summary["providers"]) <= {config["provider"]}):
        return dict(eligible=False, reason="route_or_identity_conflict")
    status, error = trace.get("http_status"), trace.get("error_type")
    if error is not None and error not in TRANSIENT_EXCEPTIONS:
        return dict(eligible=False, reason="unclassified_exception")
    if status in TRANSIENT_HTTP:
        return dict(eligible=True, reason="transient_http_no_terminal")
    if status is None and error in TRANSIENT_EXCEPTIONS - {"HTTPError"}:
        return dict(eligible=True, reason="connection_exception_no_terminal")
    if status == 200 and summary["models"] and summary["providers"] and len(summary["ids"]) == 1:
        return dict(eligible=True, reason="pinned_incomplete_eof_cause_unknown")
    return dict(eligible=False, reason="unclassified_or_unpinned_failure")
