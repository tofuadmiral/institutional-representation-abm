"""Read-only account funding admission, distinct from research cost accounting.

Never purchases credits, prints credentials, certifies an older receipt or resets
the program ledger. Only whitelisted numeric observations are returned/saved.
Official API contracts: /api/v1/credits and /api/v1/key, checked 12 October 2026.
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
import time
from urllib.request import Request

from experiments import paper3_transport_diagnostic as diagnostic
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_recovery_policy as policy

CREDITS_URL = "https://openrouter.ai/api/v1/credits"
KEY_URL = "https://openrouter.ai/api/v1/key"


def _amount(value):
    institution.require(type(value) in (int, float, str, Decimal), "numeric funding amount required")
    number = Decimal(str(value))
    institution.require(number.is_finite() and number >= 0, "finite nonnegative funding amount required")
    return number


def certify(credits, key, required, *, observed_unix, now_unix):
    """Validate data without storing API response labels, identifiers or tokens."""
    institution.require(type(observed_unix) in (float, int) and type(now_unix) in (float, int) and
        math.isfinite(observed_unix) and math.isfinite(now_unix) and
        0 <= now_unix - observed_unix <= 60, "fresh authenticated funding required")
    needed = _amount(required)
    institution.require(needed > 0 and type(credits) is dict and type(key) is dict,
                        "explicit full funding requirement/data")
    total, used = _amount(credits["total_credits"]), _amount(credits["total_usage"])
    remaining = total - used
    institution.require(key["is_free_tier"] is False and remaining >= needed,
                        "full account funding unavailable; never shrink study")
    limit, key_remaining = key["limit"], key["limit_remaining"]
    if limit is None:
        institution.require(key_remaining is None, "inconsistent unlimited key evidence")
    else:
        institution.require(_amount(limit) >= _amount(key_remaining) >= needed,
                            "key limit cannot fund whole allocation")
    effective = key.get("effective_budget")
    effective_remaining = None
    if effective is not None:
        institution.require(type(effective) is dict, "effective key budget data")
        effective_remaining = _amount(effective["remaining_usd"])
        institution.require(effective_remaining >= needed, "effective budget cannot fund whole allocation")
    for item in key.get("budgets", []):
        institution.require(type(item) is dict and _amount(item["remaining_usd"]) >= needed,
                            "applicable key budget cannot fund whole allocation")
    expiry = key.get("expires_at")
    if expiry is not None:
        institution.require(type(expiry) is str, "key expiry evidence")
        expires = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        institution.require(expires.tzinfo is not None and expires.astimezone(timezone.utc).timestamp() >
            now_unix + policy.BLOCK_DEADLINE_SECONDS, "key expires before approved block deadline")
    return dict(observed_unix=observed_unix, account_remaining_usd=str(remaining),
        key_limit_usd=None if limit is None else str(_amount(limit)),
        key_remaining_usd=None if key_remaining is None else str(_amount(key_remaining)),
        effective_remaining_usd=None if effective_remaining is None else str(effective_remaining),
        required_usd=str(needed), account_funded=True, research_authority_extended=False,
        old_reservations_certified=False, credit_purchase=False)


def observe(secret, required, *, clock=time.time):
    """Exactly two authenticated GETs; never inference, retries or raw output."""
    institution.require(type(secret) is str and secret and not any(c.isspace() for c in secret),
                        "private credential required for funding observation")
    results = []
    for url in (CREDITS_URL, KEY_URL):
        request = Request(url, headers={"Authorization": "Bearer " + secret}, method="GET")
        with diagnostic.opener().open(request, timeout=20) as response:
            institution.require(response.status == 200, "funding HTTP success required")
            results.append(json.load(response)["data"])
    observed = clock()
    return certify(*results, required, observed_unix=observed, now_unix=clock())
