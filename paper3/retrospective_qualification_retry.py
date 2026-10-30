"""One prospective, answerless AtlasCloud rate-limit reissue per qualification.

Never reuse on an old run. Retain both independent physical reservations;
unchanged wire and seed, shared 300-second cooldown, no content retries.
"""
from decimal import Decimal

from paper3 import retrospective_contract_recovery as original

MAX_REISSUES = 1
MAX_PHYSICAL = 25
DELAY_SECONDS = 300


def eligibility(row, *, logical_attempt, recoveries_used):
    result = original.eligibility(row, logical_attempt=logical_attempt,
                                  recoveries_used=0)
    if type(recoveries_used) is not int or recoveries_used != 0:
        result.update(eligible=False, reason="single_stage_reissue_exhausted")
    return result


def bound(cases):
    reserves = [Decimal(case["reserved_usd"]) for case in cases]
    return sum(reserves, Decimal(0)) + max(reserves)


def physical(case, attempt):
    if type(attempt) is not int or attempt not in (1, 2):
        raise ValueError("two physical slots only")
    return dict(**{k: v for k, v in case.items() if k not in ("id", "context")},
        id=case["id"] + f"-a{attempt}", context=dict(**case["context"],
        logical_id=case["id"], logical_attempt=attempt))
