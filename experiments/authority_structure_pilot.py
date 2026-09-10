"""Apply authority structures to one frozen set of local-model choices."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from agent_exploration.objective_metrics import evaluate_outcome
from agent_exploration.objective_protocols import (
    coalition_discipline,
    delegated_leader,
    private_ballot,
)
from agent_exploration.objective_scenarios import (
    PreferenceScenario,
    generate_objective_task,
)
from agent_exploration.objectives import AgentAction, preference_distance


AUTHORITY_INSTITUTIONS = (
    private_ballot,
    delegated_leader,
    coalition_discipline,
)


def run_authority_structure_pilot(
    baseline_choices: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare authority rules using identical, already-generated LLM choices."""
    _validate_baseline_choices(baseline_choices)
    outcome_rows: list[dict] = []
    action_rows: list[dict] = []

    for task_id, task_rows in baseline_choices.groupby("task_id", sort=False):
        task_rows = task_rows.sort_values("agent_id")
        scenario = PreferenceScenario(str(task_rows["scenario"].iloc[0]))
        seed = int(task_rows["seed"].iloc[0])
        model = str(task_rows["model"].iloc[0])
        num_agents = len(task_rows)
        oracle_task = generate_objective_task(
            seed=seed,
            scenario=scenario,
            num_agents=num_agents,
        )
        if oracle_task.task_id != task_id:
            raise ValueError(f"baseline task id does not match regenerated task: {task_id}")

        model_actions = tuple(
            AgentAction(
                agent_id=int(row.agent_id),
                principal_id=int(row.principal_id),
                alternative_id=str(row.model_choice),
                rationale=str(row.rationale) if pd.notna(row.rationale) else "",
            )
            for row in task_rows.itertuples(index=False)
        )
        model_task = replace(oracle_task, initial_actions=model_actions)
        private_loss = evaluate_outcome(
            model_task, private_ballot(model_task)
        )["outcome_loss_mean"]

        for institution in AUTHORITY_INSTITUTIONS:
            outcome = institution(model_task)
            metrics = evaluate_outcome(model_task, outcome)
            metrics.update(
                {
                    "scenario": scenario.value,
                    "seed": seed,
                    "model": model,
                    "num_agents": num_agents,
                    "outcome_loss_delta_vs_private": (
                        metrics["outcome_loss_mean"] - private_loss
                    ),
                    "behavioral_reconsideration": False,
                }
            )
            outcome_rows.append(metrics)
            action_rows.extend(
                _action_records(
                    model_task,
                    outcome,
                    scenario=scenario.value,
                    seed=seed,
                    model=model,
                )
            )

    return pd.DataFrame(outcome_rows), pd.DataFrame(action_rows)


def _validate_baseline_choices(baseline_choices: pd.DataFrame) -> None:
    required = {
        "task_id",
        "scenario",
        "seed",
        "agent_id",
        "principal_id",
        "model",
        "model_choice",
        "response_valid",
        "rationale",
    }
    missing = required - set(baseline_choices.columns)
    if missing:
        raise ValueError(f"baseline choices missing columns: {sorted(missing)}")
    if baseline_choices.empty:
        raise ValueError("baseline choices must not be empty")
    if not baseline_choices["response_valid"].astype(bool).all():
        raise ValueError("authority pilot requires valid baseline responses")
    duplicated = baseline_choices.duplicated(["task_id", "agent_id"])
    if duplicated.any():
        raise ValueError("each task must contain one baseline choice per agent")


def _action_records(task, outcome, *, scenario: str, seed: int, model: str) -> list[dict]:
    rows = []
    for final in outcome.final_actions:
        initial = task.action_for_agent(final.agent_id)
        principal = task.principal_for(final.principal_id)
        initial_policy = task.alternative_for(initial.alternative_id)
        final_policy = task.alternative_for(final.alternative_id)
        initial_loss = preference_distance(principal.ideal_point, initial_policy.position)
        final_loss = preference_distance(principal.ideal_point, final_policy.position)
        rows.append(
            {
                "task_id": task.task_id,
                "scenario": scenario,
                "seed": seed,
                "model": model,
                "institution": outcome.institution,
                "agent_id": final.agent_id,
                "principal_id": final.principal_id,
                "principal_group": principal.group,
                "principal_weight": principal.weight,
                "principal_ideal_point": json.dumps(principal.ideal_point),
                "coalition": task.coalition_by_agent[final.agent_id],
                "leader": final.agent_id == task.leader_id,
                "initial_choice": initial.alternative_id,
                "effective_choice": final.alternative_id,
                "institutionally_displaced": (
                    initial.alternative_id != final.alternative_id
                ),
                "initial_loss": initial_loss,
                "effective_loss": final_loss,
                "institutional_displacement_loss": final_loss - initial_loss,
                "behavioral_reconsideration": False,
            }
        )
    return rows


def summarize_authority_pilot(
    outcomes: pd.DataFrame, actions: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    outcome_summary = (
        outcomes.groupby(["scenario", "institution"], sort=False)
        .agg(
            n_tasks=("task_id", "size"),
            mean_institutional_displacement=("institutional_drift_mean", "mean"),
            mean_preference_retention=("preference_retention_rate", "mean"),
            mean_outcome_loss=("outcome_loss_mean", "mean"),
            mean_worst_group_loss=("outcome_loss_worst_group", "mean"),
            mean_loss_delta_vs_private=("outcome_loss_delta_vs_private", "mean"),
            mean_effective_decision_makers=("effective_decision_makers", "mean"),
        )
        .reset_index()
    )
    action_summary = (
        actions.groupby(
            ["scenario", "institution", "principal_group"], sort=False
        )
        .agg(
            n=("agent_id", "size"),
            displacement_rate=("institutionally_displaced", "mean"),
            mean_displacement_loss=("institutional_displacement_loss", "mean"),
        )
        .reset_index()
    )
    return outcome_summary, action_summary


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/agent_exploration/authority_structure_pilot"),
    )
    args = parser.parse_args(argv)

    baseline_choices = pd.read_csv(args.baseline)
    outcomes, actions = run_authority_structure_pilot(baseline_choices)
    outcome_summary, action_summary = summarize_authority_pilot(outcomes, actions)
    args.output.mkdir(parents=True, exist_ok=True)
    outcomes.to_csv(args.output / "authority_outcomes.csv", index=False)
    actions.to_csv(args.output / "authority_actions.csv", index=False)
    outcome_summary.to_csv(args.output / "authority_outcome_summary.csv", index=False)
    action_summary.to_csv(args.output / "authority_action_summary.csv", index=False)
    print(
        f"Wrote {len(outcomes)} outcomes and {len(actions)} effective-action records "
        f"to {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
