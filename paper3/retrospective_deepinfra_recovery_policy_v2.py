"""Fresh-run overload policy: unchanged finite retry/spending/answer safeguards.

Use only under a new prospective freeze. No old transport or old result changes.
"""
from paper3 import retrospective_deepinfra_recovery_evidence_v2 as evidence
from paper3 import retrospective_deepinfra_recovery_policy_v1 as previous

VERSION = "paper3-deepinfra-semantic-recovery-v2"
MAX_REISSUES_PER_ACTION = previous.MAX_REISSUES_PER_ACTION
MAX_REISSUES_PER_BLOCK = previous.MAX_REISSUES_PER_BLOCK
COOLDOWNS = previous.COOLDOWNS
BLOCK_DEADLINE_SECONDS = previous.BLOCK_DEADLINE_SECONDS
admission_open = previous.admission_open
verify_identical_wire = previous.verify_identical_wire
physical_slots = previous.physical_slots


def specification():
    return dict(previous.specification(), version=VERSION,
        evidence_version=evidence.VERSION, honors_retry_after=True,
        diagnostic_metadata_is_not_exact_message_whitelist=True)


def eligibility(row, *, physical_attempt, block_reissues_used,
                block_started_unix, detected_unix):
    result = dict(eligible=False, reason="prospective_attempt_or_block_limit",
        policy_version=VERSION, original_attempt_must_be_retained=True,
        full_failed_reservation_retained=True, new_protocol_required=True,
        old_run_reopen_authorized=False, allocation_authorized=False,
        launch_authorized=False, delay_seconds=None, not_before_unix=None,
        deadline_unix=None, retry_after_seconds=None)
    if (type(physical_attempt) is not int or
            not 1 <= physical_attempt <= MAX_REISSUES_PER_ACTION or
            type(block_reissues_used) is not int or
            not 0 <= block_reissues_used < MAX_REISSUES_PER_BLOCK):
        return result
    try:
        start = previous._time(block_started_unix)
        detected = previous._time(detected_unix)
        if detected < start:
            raise ValueError("detection predates start")
    except (ValueError, OverflowError):
        result["reason"] = "invalid_clock_evidence"
        return result
    verdict = evidence.eligibility(row)
    if not verdict["eligible"]:
        result["reason"] = verdict["reason"]
        return result
    retry_after = verdict["retry_after_seconds"]
    delay = max(COOLDOWNS[physical_attempt - 1], retry_after or 0)
    deadline, not_before = start + BLOCK_DEADLINE_SECONDS, detected + delay
    result.update(delay_seconds=delay, not_before_unix=not_before,
                  deadline_unix=deadline, retry_after_seconds=retry_after)
    if not_before >= deadline:
        result["reason"] = "required_cooldown_exceeds_block_deadline"
        return result
    result.update(eligible=True, reason="verified_preanswer_shared_pool_overload")
    return result
