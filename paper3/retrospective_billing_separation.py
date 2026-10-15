"""Prospective scientific transport validity separate from certified expense.

Only four scheduled, unredacted HTTP404 receipt absences are tolerated. The
complete worst-case charge remains accounted; no new inference or receipt retry.
Never use this adapter to change the verdict of a started historical run.
"""
from paper3 import hosted_reasoning_calls as base

VERSION = "four_404_full_reservation_v1"
OFFSETS = [0, 20, 40, 60]


def absent_observation(observation):
    return (type(observation.get("http_status")) is int and observation["http_status"] == 404
        and observation.get("error_type") == "HTTPError" and observation.get("data") is None
        and observation.get("secret_redacted") is False)


def assess(row, config):
    original = base.assess(row, config)
    receipts = row.get("receipts", [])
    absent = (original["reasons"] == ["receipt:unavailable, invalid or conflicting"]
        and len(receipts) == 4
        and [r.get("scheduled_offset_seconds") for r in receipts] == OFFSETS
        and all(absent_observation(r) for r in receipts))
    certified_sequence = (original["passed"] and 1 <= len(receipts) <= 4
        and [r.get("scheduled_offset_seconds") for r in receipts] == OFFSETS[:len(receipts)]
        and all(absent_observation(r) for r in receipts[:-1])
        and type(receipts[-1].get("http_status")) is int and receipts[-1]["http_status"] == 200)
    passed = certified_sequence or absent
    reasons = list(original["reasons"])
    if original["passed"] and not certified_sequence:
        reasons.append("receipt:unapproved observation sequence")
    return dict(**{k: v for k, v in original.items() if k not in ("passed","reasons")},
        reasons=reasons,
        passed=passed, billing_passed=original["passed"],
        billing_separation=dict(version=VERSION, four_404_absence=absent,
            receipt_sequence_allowed=certified_sequence or absent,
            scientific_transport_passed=passed,
            uncertified_full_reservation=absent and not original["receipt_certified"]))
