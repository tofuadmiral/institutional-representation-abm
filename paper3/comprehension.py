"""Frozen single-agent mandate-action gate for Paper 3.

This is deliberately a capability check, not an institutional treatment.  The
agent receives an explicit loss/permission table and must choose the permitted
policy with the lowest listed loss.  Social experiments are uninterpretable if
this condition does not hold under both option orders.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any, Sequence

from agent_exploration.local_models import ChatBackend
from paper3.institution import Mandate, Policy


@dataclass(frozen=True)
class GateResult:
    scenario_id: str
    representative_id: int
    order_block: int
    expected_policy_id: str
    response_policy_id: str | None
    valid_json: bool
    exact: bool
    raw: str


def expected_policy(mandate: Mandate, policies: Sequence[Policy]) -> str:
    allowed = [policy for policy in policies if mandate.permits(policy)]
    if not allowed:
        raise ValueError("at least one policy must be within every gate mandate")
    return min(allowed, key=mandate.loss).policy_id


def _records(mandate: Mandate, policies: Sequence[Policy], order_block: int) -> list[dict[str, object]]:
    ordered = list(policies)
    random.Random(order_block).shuffle(ordered)
    return [
        {
            "id": policy.policy_id,
            "loss": round(mandate.loss(policy), 6),
            "within_hard_mandate": mandate.permits(policy),
        }
        for policy in ordered
    ]


def evaluate_representative(
    *,
    scenario_id: str,
    representative_id: int,
    mandate: Mandate,
    policies: Sequence[Policy],
    order_block: int,
    backend: ChatBackend,
) -> GateResult:
    expected = expected_policy(mandate, policies)
    records = _records(mandate, policies, order_block)
    prompt = (
        "This is a one-step mandate-comprehension check, not a negotiation. "
        "Your principal has delegated a binding instruction: select the policy with the "
        "lowest listed loss among policies whose within_hard_mandate value is true. "
        "Do not trade, compromise, explain, or infer any other objective. "
        f"Policy table, in arbitrary order: {json.dumps(records, sort_keys=True)}. "
        'Return exactly {"choice":"<policy id>","listed_loss":<number>,"within_hard_mandate":true}. '
    )
    raw = backend.generate(
        [
            {
                "role": "system",
                "content": "Return exactly one valid JSON object and follow the binding instruction.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=48,
    )
    try:
        payload: Any = json.loads(raw)
        choice = payload.get("choice") if isinstance(payload, dict) else None
        valid = (
            isinstance(payload, dict)
            and choice in {policy.policy_id for policy in policies}
            and isinstance(payload.get("listed_loss"), (float, int))
            and payload.get("within_hard_mandate") is True
        )
    except json.JSONDecodeError:
        choice, valid = None, False
    return GateResult(
        scenario_id=scenario_id,
        representative_id=representative_id,
        order_block=order_block,
        expected_policy_id=expected,
        response_policy_id=choice if isinstance(choice, str) else None,
        valid_json=valid,
        exact=valid and choice == expected,
        raw=raw,
    )
