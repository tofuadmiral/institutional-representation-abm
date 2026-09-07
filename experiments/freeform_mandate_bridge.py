"""Bridge test: free-form peer arguments with incomplete versus complete mandates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from agent_exploration.llm_protocols import (
    generate_model_baseline,
    run_model_freeform_mandate_bridge,
)
from agent_exploration.local_models import (
    CachedChatBackend,
    ChatBackend,
    OpenAICompatibleLocalBackend,
)
from agent_exploration.objective_metrics import evaluate_outcome
from agent_exploration.objective_protocols import collective_choice
from agent_exploration.objective_scenarios import (
    PreferenceScenario,
    generate_objective_task,
)
from agent_exploration.objectives import preference_distance


def run_freeform_mandate_bridge(
    backend: ChatBackend,
    *,
    n_tasks: int = 12,
    base_seed: int = 40_000,
    num_agents: int = 7,
    workers: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run matched mandate arms with one shared set of free-form statements."""
    if n_tasks < 1:
        raise ValueError("n_tasks must be positive")
    outcomes: list[dict] = []
    actions: list[dict] = []
    errors: list[dict] = []

    for repetition in range(n_tasks):
        seed = base_seed + repetition
        oracle_task = generate_objective_task(
            seed=seed,
            scenario=PreferenceScenario.INTENSE_MINORITY,
            num_agents=num_agents,
        )
        try:
            # Generate the peer statements once using the original incomplete
            # mandate. Both treatment arms receive these exact same statements.
            model_task, _ = generate_model_baseline(
                oracle_task,
                backend,
                seed=seed,
                workers=workers,
                include_priority_weight=False,
            )
            if any(
                model_task.action_for_agent(agent_id).alternative_id
                != oracle_task.action_for_agent(agent_id).alternative_id
                for agent_id in range(num_agents)
            ):
                raise ValueError("bridge baseline did not match the oracle")

            baseline_choice = collective_choice(model_task, model_task.initial_actions)
            for mandate_complete in (False, True):
                outcome, logs = run_model_freeform_mandate_bridge(
                    model_task,
                    backend,
                    seed=seed,
                    mandate_complete=mandate_complete,
                    workers=workers,
                )
                metrics = evaluate_outcome(model_task, outcome)
                metrics.update(
                    {
                        "seed": seed,
                        "model": backend.model,
                        "num_agents": num_agents,
                        "mandate_complete": mandate_complete,
                        "baseline_collective_choice": baseline_choice,
                        "collective_choice_changed": (
                            outcome.collective_choice_id != baseline_choice
                        ),
                    }
                )
                outcomes.append(metrics)
                actions.extend(
                    _annotate_logs(model_task, logs, seed, backend.model)
                )
        except (ValueError, RuntimeError) as exc:
            errors.append(
                {
                    "task_id": oracle_task.task_id,
                    "seed": seed,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )

    return pd.DataFrame(outcomes), pd.DataFrame(actions), pd.DataFrame(errors)


def _annotate_logs(task, logs: list[dict], seed: int, model: str) -> list[dict]:
    rows = []
    for log in logs:
        principal = task.principal_for(log["principal_id"])
        initial = task.alternative_for(log["initial_choice"])
        final = task.alternative_for(log["final_choice"])
        row = dict(log)
        row.update(
            {
                "task_id": task.task_id,
                "seed": seed,
                "model": model,
                "principal_group": principal.group,
                "principal_weight": principal.weight,
                "principal_ideal_point": json.dumps(principal.ideal_point),
                "initial_loss": preference_distance(
                    principal.ideal_point, initial.position
                ),
                "final_loss": preference_distance(
                    principal.ideal_point, final.position
                ),
            }
        )
        row["individual_drift"] = row["final_loss"] - row["initial_loss"]
        rows.append(row)
    return rows


def summarize_bridge(
    outcomes: pd.DataFrame, actions: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if outcomes.empty:
        return pd.DataFrame(), pd.DataFrame()
    outcome_summary = (
        outcomes.groupby(["mandate_complete", "institution"], sort=False)
        .agg(
            n_tasks=("task_id", "size"),
            mean_institutional_drift=("institutional_drift_mean", "mean"),
            mean_retention=("preference_retention_rate", "mean"),
            collective_change_rate=("collective_choice_changed", "mean"),
            mean_outcome_loss=("outcome_loss_mean", "mean"),
        )
        .reset_index()
    )
    action_summary = (
        actions.groupby(["mandate_complete", "principal_group"], sort=False)
        .agg(
            n=("agent_id", "size"),
            votes_changed=("changed_choice", "sum"),
            vote_change_rate=("changed_choice", "mean"),
            mean_individual_drift=("individual_drift", "mean"),
        )
        .reset_index()
    )
    return outcome_summary, action_summary


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--tasks", type=int, default=12)
    parser.add_argument("--base-seed", type=int, default=40_000)
    parser.add_argument("--agents", type=int, default=7)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/agent_exploration/freeform_mandate_bridge"),
    )
    args = parser.parse_args(argv)
    backend = CachedChatBackend(
        OpenAICompatibleLocalBackend(model=args.model, base_url=args.base_url),
        cache_dir=args.output / "completion_cache",
    )
    outcomes, actions, errors = run_freeform_mandate_bridge(
        backend,
        n_tasks=args.tasks,
        base_seed=args.base_seed,
        num_agents=args.agents,
        workers=args.workers,
    )
    outcome_summary, action_summary = summarize_bridge(outcomes, actions)
    args.output.mkdir(parents=True, exist_ok=True)
    outcomes.to_csv(args.output / "bridge_outcomes.csv", index=False)
    actions.to_csv(args.output / "bridge_actions.csv", index=False)
    errors.to_csv(args.output / "bridge_errors.csv", index=False)
    outcome_summary.to_csv(args.output / "bridge_outcome_summary.csv", index=False)
    action_summary.to_csv(args.output / "bridge_action_summary.csv", index=False)
    print(
        f"Wrote {len(outcomes)} outcomes, {len(actions)} actions, "
        f"and {len(errors)} errors to {args.output}"
    )
    return 0 if errors.empty else 2


if __name__ == "__main__":
    sys.exit(_main())
