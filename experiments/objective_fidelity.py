"""Deterministic Paper 2 identification experiment for objective fidelity."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from agent_exploration.objective_metrics import evaluate_outcome
from agent_exploration.objective_protocols import INSTITUTIONS, run_institutions
from agent_exploration.objective_scenarios import PreferenceScenario, generate_objective_task


def run_objective_fidelity(
    *,
    n_tasks_per_scenario: int = 100,
    base_seed: int = 0,
    num_agents: int = 7,
    compromise_tolerance: float = 1.0,
) -> pd.DataFrame:
    if n_tasks_per_scenario < 1:
        raise ValueError("n_tasks_per_scenario must be positive")
    rows = []
    for scenario_index, scenario in enumerate(PreferenceScenario):
        for repetition in range(n_tasks_per_scenario):
            seed = base_seed + scenario_index * n_tasks_per_scenario + repetition
            task = generate_objective_task(
                seed=seed, scenario=scenario, num_agents=num_agents
            )
            for outcome in run_institutions(
                task, compromise_tolerance=compromise_tolerance
            ):
                record = evaluate_outcome(task, outcome)
                record.update({"scenario": scenario.value, "seed": seed})
                rows.append(record)
    results = pd.DataFrame(rows)
    private_loss = (
        results[results["institution"] == "private_ballot"]
        .set_index("task_id")["outcome_loss_mean"]
    )
    results["outcome_loss_delta_vs_private"] = results.apply(
        lambda row: (
            row["outcome_loss_mean"] - private_loss[row["task_id"]]
            if pd.notna(row["outcome_loss_mean"])
            else None
        ),
        axis=1,
    )
    return results


def summarize_objective_fidelity(results: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "baseline_error_mean",
        "final_error_mean",
        "institutional_drift_mean",
        "preference_retention_rate",
        "outcome_loss_mean",
        "outcome_loss_median",
        "outcome_loss_worst_group",
        "outcome_loss_delta_vs_private",
        "pareto_dominated",
    ]
    return (
        results.groupby(["scenario", "institution"], sort=False)[metrics]
        .mean(numeric_only=True)
        .reset_index()
    )


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the delegated-objective-fidelity identification layer"
    )
    parser.add_argument("--tasks", type=int, default=100)
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--agents", type=int, default=7)
    parser.add_argument("--compromise-tolerance", type=float, default=1.0)
    parser.add_argument(
        "--output", type=Path, default=Path("results/agent_exploration")
    )
    args = parser.parse_args(argv)

    results = run_objective_fidelity(
        n_tasks_per_scenario=args.tasks,
        base_seed=args.base_seed,
        num_agents=args.agents,
        compromise_tolerance=args.compromise_tolerance,
    )
    summary = summarize_objective_fidelity(results)
    args.output.mkdir(parents=True, exist_ok=True)
    long_path = args.output / "objective_fidelity_long.csv"
    summary_path = args.output / "objective_fidelity_summary.csv"
    results.to_csv(long_path, index=False)
    summary.to_csv(summary_path, index=False)
    print(f"Wrote {len(results)} rows to {long_path}")
    print(f"Wrote {len(summary)} rows to {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
