"""Pilot LLM operation of delegated and coalition authority nodes."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from agent_exploration.llm_protocols import (
    MODEL_COALITION_AUTHORITY,
    MODEL_DELEGATED_AUTHORITY,
    run_model_coalition_authority,
    run_model_delegated_authority,
)
from agent_exploration.local_models import (
    CachedChatBackend,
    ChatBackend,
    OpenAICompatibleLocalBackend,
)
from agent_exploration.objective_metrics import evaluate_outcome
from agent_exploration.objective_protocols import PRIVATE_BALLOT, private_ballot
from agent_exploration.objective_scenarios import (
    PreferenceScenario,
    generate_objective_task,
)
from agent_exploration.objectives import AgentAction, CollectiveOutcome
from experiments.authority_structure_pilot import _validate_baseline_choices


def run_authority_operation_pilot(
    baseline_choices: pd.DataFrame,
    backend: ChatBackend,
    *,
    tasks_per_scenario: int = 4,
    workers: int = 1,
    include_aggregate_scores: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run matched private, delegated, and coalition authority conditions."""
    if tasks_per_scenario < 1:
        raise ValueError("tasks_per_scenario must be positive")
    _validate_baseline_choices(baseline_choices)
    selected = _select_tasks(baseline_choices, tasks_per_scenario)
    outcomes: list[dict] = []
    decisions: list[dict] = []
    errors: list[dict] = []

    for task_id, task_rows in selected.groupby("task_id", sort=False):
        task_rows = task_rows.sort_values("agent_id")
        scenario = PreferenceScenario(str(task_rows["scenario"].iloc[0]))
        seed = int(task_rows["seed"].iloc[0])
        num_agents = len(task_rows)
        oracle_task = generate_objective_task(
            seed=seed,
            scenario=scenario,
            num_agents=num_agents,
        )
        if oracle_task.task_id != task_id:
            raise ValueError(f"baseline task id does not match regenerated task: {task_id}")
        model_task = replace(
            oracle_task,
            initial_actions=tuple(
                AgentAction(
                    agent_id=int(row.agent_id),
                    principal_id=int(row.principal_id),
                    alternative_id=str(row.model_choice),
                    rationale=(
                        str(row.rationale) if pd.notna(row.rationale) else ""
                    ),
                )
                for row in task_rows.itertuples(index=False)
            ),
        )
        try:
            private = private_ballot(model_task)
            delegated, delegated_logs = run_model_delegated_authority(
                model_task,
                backend,
                seed=seed * 10_000 + 1,
                include_aggregate_scores=include_aggregate_scores,
            )
            coalition, coalition_logs = run_model_coalition_authority(
                model_task,
                backend,
                seed=seed * 10_000 + 2,
                workers=workers,
                include_aggregate_scores=include_aggregate_scores,
            )
        except (ValueError, RuntimeError) as exc:
            errors.append(
                {
                    "task_id": task_id,
                    "scenario": scenario.value,
                    "seed": seed,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
            continue

        oracle_private = private_ballot(oracle_task)
        oracle_by_institution = {
            PRIVATE_BALLOT: oracle_private,
            MODEL_DELEGATED_AUTHORITY: _oracle_delegated_outcome(
                model_task, delegated
            ),
            MODEL_COALITION_AUTHORITY: _oracle_coalition_outcome(
                model_task, coalition
            ),
        }
        private_model_loss = evaluate_outcome(model_task, private)["outcome_loss_mean"]
        private_oracle_loss = evaluate_outcome(
            oracle_task, oracle_private
        )["outcome_loss_mean"]

        for outcome in (private, delegated, coalition):
            oracle_outcome = oracle_by_institution[outcome.institution]
            model_metrics = evaluate_outcome(model_task, outcome)
            oracle_metrics = evaluate_outcome(model_task, oracle_outcome)
            if outcome.institution == PRIVATE_BALLOT:
                node_accuracy = float(task_rows["exact_choice_match"].mean())
                model_calls = num_agents
            else:
                node_accuracy = float(outcome.metadata["authority_node_accuracy"])
                model_calls = int(outcome.metadata["decision_model_calls"])
            model_metrics.update(
                {
                    "scenario": scenario.value,
                    "seed": seed,
                    "model": backend.model,
                    "num_agents": num_agents,
                    "decision_model_calls": model_calls,
                    "authority_node_accuracy": node_accuracy,
                    "oracle_collective_choice_id": oracle_outcome.collective_choice_id,
                    "collective_choice_oracle_match": (
                        outcome.collective_choice_id
                        == oracle_outcome.collective_choice_id
                    ),
                    "structural_loss_delta_vs_private": (
                        oracle_metrics["outcome_loss_mean"] - private_oracle_loss
                    ),
                    "model_execution_loss": (
                        model_metrics["outcome_loss_mean"]
                        - oracle_metrics["outcome_loss_mean"]
                    ),
                    "total_loss_delta_vs_private": (
                        model_metrics["outcome_loss_mean"] - private_model_loss
                    ),
                    "aggregate_scores_visible": include_aggregate_scores,
                }
            )
            outcomes.append(model_metrics)

        for log in delegated_logs + coalition_logs:
            log.update(
                {
                    "task_id": task_id,
                    "scenario": scenario.value,
                    "seed": seed,
                    "model": backend.model,
                }
            )
            decisions.append(log)

    return pd.DataFrame(outcomes), pd.DataFrame(decisions), pd.DataFrame(errors)


def _select_tasks(baseline: pd.DataFrame, tasks_per_scenario: int) -> pd.DataFrame:
    selected_ids = []
    for _, rows in baseline.groupby("scenario", sort=False):
        selected_ids.extend(rows["task_id"].drop_duplicates().head(tasks_per_scenario))
    return baseline[baseline["task_id"].isin(selected_ids)].copy()


def _oracle_delegated_outcome(task, model_outcome) -> CollectiveOutcome:
    choice = str(model_outcome.metadata["oracle_collective_choice_id"])
    return CollectiveOutcome(
        institution=MODEL_DELEGATED_AUTHORITY,
        final_actions=tuple(
            AgentAction(action.agent_id, action.principal_id, choice)
            for action in task.initial_actions
        ),
        collective_choice_id=choice,
    )


def _oracle_coalition_outcome(task, model_outcome) -> CollectiveOutcome:
    platforms = dict(model_outcome.metadata["oracle_coalition_platforms"])
    actions = tuple(
        AgentAction(
            action.agent_id,
            action.principal_id,
            platforms[task.coalition_by_agent[action.agent_id]],
        )
        for action in task.initial_actions
    )
    return CollectiveOutcome(
        institution=MODEL_COALITION_AUTHORITY,
        final_actions=actions,
        collective_choice_id=str(model_outcome.metadata["oracle_collective_choice_id"]),
    )


def summarize_authority_operation(outcomes: pd.DataFrame) -> pd.DataFrame:
    if outcomes.empty:
        return pd.DataFrame()
    return (
        outcomes.groupby(["scenario", "institution"], sort=False)
        .agg(
            n_tasks=("task_id", "size"),
            authority_node_accuracy=("authority_node_accuracy", "mean"),
            collective_choice_accuracy=("collective_choice_oracle_match", "mean"),
            mean_structural_loss=("structural_loss_delta_vs_private", "mean"),
            mean_model_execution_loss=("model_execution_loss", "mean"),
            mean_total_loss_delta=("total_loss_delta_vs_private", "mean"),
            mean_preference_retention=("preference_retention_rate", "mean"),
            mean_worst_group_loss=("outcome_loss_worst_group", "mean"),
            mean_decision_model_calls=("decision_model_calls", "mean"),
        )
        .reset_index()
    )


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--tasks-per-scenario", type=int, default=4)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--hide-aggregate-scores",
        action="store_true",
        help="Require the model to sum per-principal losses itself",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/agent_exploration/authority_operation_pilot"),
    )
    args = parser.parse_args(argv)
    backend = CachedChatBackend(
        OpenAICompatibleLocalBackend(model=args.model, base_url=args.base_url),
        cache_dir=args.output / "completion_cache",
    )
    outcomes, decisions, errors = run_authority_operation_pilot(
        pd.read_csv(args.baseline),
        backend,
        tasks_per_scenario=args.tasks_per_scenario,
        workers=args.workers,
        include_aggregate_scores=not args.hide_aggregate_scores,
    )
    summary = summarize_authority_operation(outcomes)
    args.output.mkdir(parents=True, exist_ok=True)
    outcomes.to_csv(args.output / "authority_operation_outcomes.csv", index=False)
    decisions.to_csv(args.output / "authority_operation_decisions.csv", index=False)
    errors.to_csv(args.output / "authority_operation_errors.csv", index=False)
    summary.to_csv(args.output / "authority_operation_summary.csv", index=False)
    print(
        f"Wrote {len(outcomes)} outcomes, {len(decisions)} authority decisions, "
        f"and {len(errors)} errors to {args.output}"
    )
    return 0 if errors.empty else 2


if __name__ == "__main__":
    sys.exit(_main())
