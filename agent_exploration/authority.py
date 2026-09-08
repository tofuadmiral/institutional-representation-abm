"""LLM and oracle decisions at institutionally authorized decision nodes."""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from typing import Sequence

from agent_exploration.local_models import ChatBackend
from agent_exploration.objectives import (
    ObjectiveTask,
    PolicyAlternative,
    preference_distance,
)
from agent_exploration.representatives import parse_choice


WEIGHTED_LOSS_MANDATE = "minimize_total_weighted_loss"


@dataclass(frozen=True)
class AuthorityDecision:
    authority_id: str
    principal_ids: tuple[int, ...]
    alternative_id: str
    rationale: str
    presented_order: tuple[str, ...]


@dataclass
class LocalModelAuthority:
    authority_id: str
    backend: ChatBackend

    def choose_policy(
        self,
        task: ObjectiveTask,
        principal_ids: Sequence[int],
        *,
        seed: int,
        include_aggregate_scores: bool = True,
    ) -> AuthorityDecision:
        """Execute a declared aggregation mandate for the supplied principals."""
        if not principal_ids:
            raise ValueError("an authority must represent at least one principal")
        ordered = list(task.alternatives)
        random.Random(seed).shuffle(ordered)
        prompt = authority_choice_prompt(
            task,
            principal_ids,
            ordered,
            include_aggregate_scores=include_aggregate_scores,
        )
        raw = self.backend.generate(
            [
                {
                    "role": "system",
                    "content": (
                        "You are an authorized institutional decision maker. "
                        "Execute the supplied numerical aggregation rule exactly. "
                        "Return only valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=32,
        )
        choice, rationale = parse_choice(
            raw, {alternative.alternative_id for alternative in task.alternatives}
        )
        return AuthorityDecision(
            authority_id=self.authority_id,
            principal_ids=tuple(principal_ids),
            alternative_id=choice,
            rationale=rationale,
            presented_order=tuple(a.alternative_id for a in ordered),
        )


def authority_choice_prompt(
    task: ObjectiveTask,
    principal_ids: Sequence[int],
    alternatives: Sequence[PolicyAlternative],
    *,
    include_aggregate_scores: bool = True,
) -> str:
    """Render anonymous numerical preferences without political group labels."""
    policies = [
        {"id": alternative.alternative_id, "position": list(alternative.position)}
        for alternative in alternatives
    ]
    principals = []
    for principal_id in principal_ids:
        principal = task.principal_for(principal_id)
        record = {
            "principal_id": principal.principal_id,
            "ideal_point": list(principal.ideal_point),
            "priority_weight": principal.weight,
        }
        if not include_aggregate_scores:
            record["weighted_losses"] = [
                {
                    "policy_id": alternative.alternative_id,
                    "weighted_loss": rounded_weighted_loss(
                        principal.weight,
                        principal.ideal_point,
                        alternative.position,
                    ),
                }
                for alternative in alternatives
            ]
        principals.append(record)
    if include_aggregate_scores:
        aggregate_scores = authority_scores(task, principal_ids)
        score_text = (
            "The controlling decision table is "
            f"{json.dumps(aggregate_scores, sort_keys=True)}. These are exact "
            "precomputed total weighted losses; use this table directly and do "
            "not recalculate it. "
        )
        mandate_text = (
            "Your binding mandate is to choose the policy with the lowest total "
            "weighted loss in the controlling decision table. "
        )
    else:
        score_text = (
            "Calculate each policy's total by summing its weighted_loss across "
            "the records. "
        )
        mandate_text = (
            "Your binding mandate is to choose the policy with the lowest sum of "
            "weighted_loss across every principal in your authority. "
        )
    return (
        f"{score_text}Your authority covers principals {list(principal_ids)}. The available "
        f"policies, in arbitrary order, are {json.dumps(policies)}. The entrusted "
        f"preference records are {json.dumps(principals)}. {mandate_text}"
        "If multiple policies have the same minimum "
        f"sum, choose the status quo '{task.status_quo_id}' if it is tied; otherwise "
        "choose the alphabetically first policy id. Respond with exactly "
        '{"choice":"<policy id>"}. Do not include arithmetic, a rationale, or any '
        "other text."
    )


def oracle_authority_choice(
    task: ObjectiveTask,
    principal_ids: Sequence[int],
) -> str:
    """Return the exact choice under the numerical mandate shown to the model."""
    if not principal_ids:
        raise ValueError("an authority must represent at least one principal")
    scores = authority_scores(task, principal_ids)
    minimum = min(scores.values())
    winners = sorted(
        policy_id
        for policy_id, score in scores.items()
        if math.isclose(score, minimum, rel_tol=0.0, abs_tol=1e-9)
    )
    if task.status_quo_id in winners:
        return task.status_quo_id
    return winners[0]


def authority_scores(
    task: ObjectiveTask,
    principal_ids: Sequence[int],
) -> dict[str, float]:
    """Sum the same rounded weighted losses supplied in the model prompt."""
    if not principal_ids:
        raise ValueError("an authority must represent at least one principal")
    return {
        alternative.alternative_id: sum(
            rounded_weighted_loss(
                task.principal_for(principal_id).weight,
                task.principal_for(principal_id).ideal_point,
                alternative.position,
            )
            for principal_id in principal_ids
        )
        for alternative in task.alternatives
    }


def rounded_weighted_loss(
    weight: float,
    ideal_point: tuple[float, ...],
    policy_position: tuple[float, ...],
) -> float:
    return round(weight * preference_distance(ideal_point, policy_position), 6)
