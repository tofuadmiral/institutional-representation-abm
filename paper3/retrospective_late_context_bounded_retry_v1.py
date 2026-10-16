"""Prospective 16-task gate: at most3 identical reissues/action and9 total.

Only the immutable predecessor's exact answerless shared-pool429 evidence
predicate is reused. No content/receipt retries, reset of an old controller,
old-run continuation, provider fallback, or implicit launch authority.
"""
from copy import deepcopy
from decimal import Decimal

from paper3 import retrospective_contract_recovery as predecessor

MAX_REISSUES_PER_ACTION = 3
MAX_REISSUES = 9
MAX_PHYSICAL = 25
COOLDOWNS = (300, 600, 1200)


def eligibility(row, *, logical_attempt, recoveries_used):
    result = dict(eligible=False, reason="prospective_attempt_or_total_limit",
                  delay_seconds=None)
    if (type(logical_attempt) is not int or
            not 1 <= logical_attempt <= MAX_REISSUES_PER_ACTION or
            type(recoveries_used) is not int or not 0 <= recoveries_used < MAX_REISSUES):
        return result
    evidence = predecessor.eligibility(row, logical_attempt=1, recoveries_used=0)
    result.update(evidence)
    if evidence["eligible"]:
        result["delay_seconds"] = COOLDOWNS[logical_attempt - 1]
    return result


def physical(case, attempt):
    if type(attempt) is not int or not 1 <= attempt <= 4:
        raise ValueError("four prospectively assigned physical slots")
    if {"logical_id", "logical_attempt"} & set(case["context"]):
        raise ValueError("reserved context")
    return dict(**{k: deepcopy(v) for k, v in case.items() if k not in ("id", "context")},
        id=case["id"] + f"-a{attempt}", context=dict(**deepcopy(case["context"]),
        logical_id=case["id"], logical_attempt=attempt))


def bound(cases):
    reserves = [Decimal(case["reserved_usd"]) for case in cases]
    return sum(reserves, Decimal(0)) + MAX_REISSUES * max(reserves)
