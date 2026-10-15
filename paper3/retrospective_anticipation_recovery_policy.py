"""Prospective bounded recovery, not a transport runner or launch authority.

Reuses only the immutable predecessor's strict *evidence* predicate. The old
one-reissue limit remains intact in that predecessor. New limits must be frozen
with a distinct controller, physical-attempt audit and budget adapter before use.
No network, ledger writes, response repair or old-run continuation occurs here.
"""
from hashlib import sha256
import math
import re

from paper3 import retrospective_contract_recovery as predecessor

VERSION = "paper3-anticipation-bounded-recovery-v2"
MAX_REISSUES_PER_ACTION = 3
MAX_REISSUES_PER_BLOCK = 40
COOLDOWNS = (300, 600, 1200)
BLOCK_DEADLINE_SECONDS = 86400


def specification():
    return dict(version=VERSION, maximum_reissues_per_action=MAX_REISSUES_PER_ACTION,
        maximum_reissues_per_block=MAX_REISSUES_PER_BLOCK,
        maximum_physical_per_action=MAX_REISSUES_PER_ACTION + 1,
        cooldown_seconds=COOLDOWNS, block_deadline_seconds=BLOCK_DEADLINE_SECONDS,
        workers=1, inference_repair=False, provider_fallback=False,
        old_run_reopen_authorized=False, allocation_authorized=False,
        launch_authorized=False)


def _time(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("finite nonnegative timestamp required")
    return value


def admission_open(*, started_unix, now_unix):
    """A deadline prevents new admissions; it never discards a received answer."""
    start, now = _time(started_unix), _time(now_unix)
    if now < start:
        raise ValueError("clock predates block start")
    return now < start + BLOCK_DEADLINE_SECONDS


def eligibility(row, *, physical_attempt, block_reissues_used,
                block_started_unix, detected_unix):
    """Plan only a new identical attempt after a certified answerless failure.

The predecessor's attempt/counter arguments are fixed solely to invoke its
preserved answerless-error predicate. Actual prospective limits are checked
here, independently; neither the row nor its request/evidence is rewritten.
Stored retryable/assessment flags never establish eligibility.
"""
    result = dict(eligible=False, reason="prospective_attempt_or_block_limit",
        policy_version=VERSION, original_attempt_must_be_retained=True,
        full_failed_reservation_retained=True, new_protocol_required=True,
        old_run_reopen_authorized=False, allocation_authorized=False,
        launch_authorized=False, delay_seconds=None, not_before_unix=None,
        deadline_unix=None)
    if (type(physical_attempt) is not int or
            not 1 <= physical_attempt <= MAX_REISSUES_PER_ACTION or
            type(block_reissues_used) is not int or
            not 0 <= block_reissues_used < MAX_REISSUES_PER_BLOCK):
        return result
    try:
        start, detected = _time(block_started_unix), _time(detected_unix)
        if detected < start:
            raise ValueError("detection predates block start")
    except (ValueError, OverflowError):
        result["reason"] = "invalid_clock_evidence"
        return result
    evidence = predecessor.eligibility(row, logical_attempt=1, recoveries_used=0)
    if not evidence["eligible"]:
        result["reason"] = evidence["reason"]
        return result
    delay = COOLDOWNS[physical_attempt - 1]
    deadline = start + BLOCK_DEADLINE_SECONDS
    not_before = detected + delay
    result.update(delay_seconds=delay, not_before_unix=not_before,
                  deadline_unix=deadline)
    # Equal-to-deadline admission is closed too. Never shorten a cooldown.
    if not_before >= deadline:
        result["reason"] = "required_cooldown_exceeds_block_deadline"
        return result
    result.update(eligible=True, reason="pinned_pre_answer_429_shared_pool")
    return result


def verify_identical_wire(original, reissue, expected_sha256):
    """Verify the exact serialized body (including seed), not JSON equivalence."""
    if (type(original) is not str or type(reissue) is not str or
            type(expected_sha256) is not str or
            not re.fullmatch(r"[a-f0-9]{64}", expected_sha256)):
        raise ValueError("exact wire strings and SHA256 required")
    if original != reissue or sha256(original.encode()).hexdigest() != expected_sha256:
        raise ValueError("changed request wire/seed; no reissue")
    return True


def physical_slots(logical_id):
    """Declare every potential slot; a block-wide cap still limits paid attempts."""
    if type(logical_id) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", logical_id):
        raise ValueError("safe bounded logical identifier required")
    return tuple(f"{logical_id}-a{attempt}" for attempt in range(1, 5))
