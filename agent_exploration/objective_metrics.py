"""Metrics separating representative error from institutional distortion."""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any, Iterable

from agent_exploration.objectives import (
    AgentAction,
    CollectiveOutcome,
    ObjectiveTask,
    preference_distance,
)


def _action_loss(task: ObjectiveTask, action: AgentAction) -> float:
    principal = task.principal_for(action.principal_id)
    alternative = task.alternative_for(action.alternative_id)
    return preference_distance(principal.ideal_point, alternative.position)


def evaluate_outcome(task: ObjectiveTask, outcome: CollectiveOutcome) -> dict[str, Any]:
    initial_by_agent = {a.agent_id: a for a in task.initial_actions}
    final_by_agent = {a.agent_id: a for a in outcome.final_actions}
    if set(initial_by_agent) != set(final_by_agent):
        raise ValueError("outcome must contain one final action for every agent")

    baseline_errors = []
    final_errors = []
    weights = []
    retained = 0
    for agent_id, initial in initial_by_agent.items():
        final = final_by_agent[agent_id]
        if final.principal_id != initial.principal_id:
            raise ValueError("an institution cannot reassign an agent's principal")
        principal = task.principal_for(initial.principal_id)
        baseline_errors.append(_action_loss(task, initial))
        final_errors.append(_action_loss(task, final))
        weights.append(principal.weight)
        retained += initial.alternative_id == final.alternative_id

    baseline_mean = _weighted_mean(baseline_errors, weights)
    final_mean = _weighted_mean(final_errors, weights)
    submitted = outcome.collective_choice_id is not None

    outcome_losses: list[float] = []
    group_losses: dict[str, list[tuple[float, float]]] = defaultdict(list)
    pareto_dominated = False
    if submitted:
        collective = task.alternative_for(outcome.collective_choice_id)
        for principal in task.principals:
            loss = preference_distance(principal.ideal_point, collective.position)
            outcome_losses.append(loss)
            group_losses[principal.group].append((loss, principal.weight))
        pareto_dominated = _is_pareto_dominated(task, outcome.collective_choice_id)

    group_means = {
        group: _weighted_mean(
            [loss for loss, _ in values], [weight for _, weight in values]
        )
        for group, values in group_losses.items()
    }
    record = {
        "task_id": task.task_id,
        "institution": outcome.institution,
        "collective_choice_id": outcome.collective_choice_id,
        "submitted": submitted,
        "baseline_error_mean": baseline_mean,
        "final_error_mean": final_mean,
        "institutional_drift_mean": final_mean - baseline_mean,
        "preference_retention_rate": retained / len(initial_by_agent),
        "outcome_loss_mean": (
            _weighted_mean(outcome_losses, [p.weight for p in task.principals])
            if submitted else None
        ),
        "outcome_loss_median": median(outcome_losses) if submitted else None,
        "outcome_loss_worst_group": max(group_means.values()) if group_means else None,
        "pareto_dominated": pareto_dominated if submitted else None,
        "groups": len(group_means),
        **outcome.metadata,
    }
    return record


def _weighted_mean(values: Iterable[float], weights: Iterable[float]) -> float:
    value_list = list(values)
    weight_list = list(weights)
    total_weight = sum(weight_list)
    if len(value_list) != len(weight_list) or not value_list or total_weight <= 0:
        raise ValueError("values and positive weights must have equal non-zero length")
    return sum(v * w for v, w in zip(value_list, weight_list)) / total_weight


def _is_pareto_dominated(task: ObjectiveTask, chosen_id: str) -> bool:
    chosen = task.alternative_for(chosen_id)
    chosen_losses = [
        preference_distance(p.ideal_point, chosen.position) for p in task.principals
    ]
    for alternative in task.alternatives:
        if alternative.alternative_id == chosen_id:
            continue
        candidate_losses = [
            preference_distance(p.ideal_point, alternative.position)
            for p in task.principals
        ]
        if all(c <= b for c, b in zip(candidate_losses, chosen_losses)) and any(
            c < b for c, b in zip(candidate_losses, chosen_losses)
        ):
            return True
    return False
