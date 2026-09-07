"""Matched local-LLM pilot: private binding ballot versus peer exposure."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from agent_exploration.llm_protocols import (
    PUBLIC_VOTE_EXPOSURE,
    generate_model_baseline,
    run_model_open_deliberation,
    run_model_private_ballot,
    run_model_public_vote_exposure,
)
from agent_exploration.local_models import (
    CachedChatBackend,
    ChatBackend,
    OpenAICompatibleLocalBackend,
)
from agent_exploration.objective_metrics import evaluate_outcome
from agent_exploration.objective_scenarios import PreferenceScenario, generate_objective_task
from agent_exploration.objectives import preference_distance


def run_llm_institutional_pilot(
    backend: ChatBackend,
    *,
    n_tasks_per_scenario: int = 1,
    base_seed: int = 10_000,
    num_agents: int = 7,
    workers: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run matched treatments and return outcome, action, and error records."""
    if n_tasks_per_scenario < 1:
        raise ValueError("n_tasks_per_scenario must be positive")
    outcome_rows: list[dict] = []
    action_rows: list[dict] = []
    error_rows: list[dict] = []

    for scenario_index, scenario in enumerate(PreferenceScenario):
        for repetition in range(n_tasks_per_scenario):
            seed = base_seed + scenario_index * n_tasks_per_scenario + repetition
            oracle_task = generate_objective_task(
                seed=seed,
                scenario=scenario,
                num_agents=num_agents,
            )
            try:
                model_task, baseline_logs = generate_model_baseline(
                    oracle_task, backend, seed=seed, workers=workers
                )
                private, private_logs = run_model_private_ballot(
                    model_task, backend, seed=seed, workers=workers
                )
                public_votes, public_vote_logs = run_model_public_vote_exposure(
                    model_task, backend, seed=seed, workers=workers
                )
                deliberation, deliberation_logs = run_model_open_deliberation(
                    model_task, backend, seed=seed, workers=workers
                )
            except (ValueError, RuntimeError) as exc:
                error_rows.append(
                    {
                        "task_id": oracle_task.task_id,
                        "scenario": scenario.value,
                        "seed": seed,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )
                continue

            private_metrics = evaluate_outcome(model_task, private)
            private_loss = private_metrics["outcome_loss_mean"]
            for outcome, logs in (
                (private, private_logs),
                (public_votes, public_vote_logs),
                (deliberation, deliberation_logs),
            ):
                metrics = evaluate_outcome(model_task, outcome)
                metrics.update(
                    {
                        "scenario": scenario.value,
                        "seed": seed,
                        "model": backend.model,
                        "num_agents": num_agents,
                        "outcome_loss_delta_vs_private": (
                            metrics["outcome_loss_mean"] - private_loss
                        ),
                    }
                )
                outcome_rows.append(metrics)
                action_rows.extend(
                    _annotate_action_logs(
                        oracle_task,
                        model_task,
                        logs,
                        scenario=scenario,
                        seed=seed,
                        model=backend.model,
                    )
                )

            action_rows.extend(
                _annotate_action_logs(
                    oracle_task,
                    model_task,
                    baseline_logs,
                    scenario=scenario,
                    seed=seed,
                    model=backend.model,
                )
            )

    return (
        pd.DataFrame(outcome_rows),
        pd.DataFrame(action_rows),
        pd.DataFrame(error_rows),
    )


def _annotate_action_logs(
    oracle_task,
    model_task,
    logs: list[dict],
    *,
    scenario: PreferenceScenario,
    seed: int,
    model: str,
) -> list[dict]:
    rows = []
    for log in logs:
        agent_id = log["agent_id"]
        principal = model_task.principal_for(log["principal_id"])
        oracle = oracle_task.action_for_agent(agent_id)
        initial = model_task.action_for_agent(agent_id)
        final = model_task.alternative_for(log["final_choice"])
        initial_alternative = model_task.alternative_for(initial.alternative_id)
        row = dict(log)
        row.update(
            {
                "task_id": model_task.task_id,
                "scenario": scenario.value,
                "seed": seed,
                "model": model,
                "principal_group": principal.group,
                "principal_weight": principal.weight,
                "principal_ideal_point": json.dumps(principal.ideal_point),
                "oracle_choice": oracle.alternative_id,
                "initial_oracle_match": initial.alternative_id
                == oracle.alternative_id,
                "initial_loss": preference_distance(
                    principal.ideal_point, initial_alternative.position
                ),
                "final_loss": preference_distance(
                    principal.ideal_point, final.position
                ),
            }
        )
        row["individual_drift"] = row["final_loss"] - row["initial_loss"]
        rows.append(row)
    return rows


def summarize_pilot(outcomes: pd.DataFrame) -> pd.DataFrame:
    if outcomes.empty:
        return pd.DataFrame()
    metrics = [
        "institutional_drift_mean",
        "preference_retention_rate",
        "outcome_loss_mean",
        "outcome_loss_worst_group",
        "outcome_loss_delta_vs_private",
    ]
    return (
        outcomes.groupby(["scenario", "institution"], sort=False)[metrics]
        .mean(numeric_only=True)
        .reset_index()
    )


def summarize_action_effects(actions: pd.DataFrame) -> pd.DataFrame:
    """Summarize observable vote changes by scenario, treatment, and group."""
    if actions.empty:
        return pd.DataFrame()
    binding = actions[actions["stage"] == "binding_vote"].copy()
    binding["positive_fidelity_loss"] = binding["individual_drift"] > 1e-12
    return (
        binding.groupby(
            ["scenario", "institution", "principal_group"], sort=False
        )
        .agg(
            n=("agent_id", "size"),
            vote_change_rate=("changed_choice", "mean"),
            positive_fidelity_loss_rate=("positive_fidelity_loss", "mean"),
            mean_individual_drift=("individual_drift", "mean"),
        )
        .reset_index()
    )


def paired_treatment_effects(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Return task-matched treatment differences without inference."""
    if outcomes.empty:
        return pd.DataFrame()
    metrics = [
        "institutional_drift_mean",
        "preference_retention_rate",
        "outcome_loss_mean",
        "outcome_loss_worst_group",
    ]
    index = ["task_id", "scenario", "seed"]
    pivoted = outcomes.pivot(index=index, columns="institution", values=metrics)
    available = set(outcomes["institution"])
    contrasts = []
    if {"private_ballot", PUBLIC_VOTE_EXPOSURE}.issubset(available):
        contrasts.append(
            (PUBLIC_VOTE_EXPOSURE, "private_ballot", "public_votes_minus_private")
        )
    if {PUBLIC_VOTE_EXPOSURE, "open_deliberation"}.issubset(available):
        contrasts.append(
            ("open_deliberation", PUBLIC_VOTE_EXPOSURE, "arguments_minus_votes")
        )
    if {"private_ballot", "open_deliberation"}.issubset(available):
        contrasts.append(
            ("open_deliberation", "private_ballot", "open_minus_private")
        )
    rows = []
    for keys, values in pivoted.iterrows():
        row = dict(zip(index, keys))
        for treatment, reference, label in contrasts:
            for metric in metrics:
                row[f"{metric}_{label}"] = (
                    values[(metric, treatment)] - values[(metric, reference)]
                )
        rows.append(row)
    return pd.DataFrame(rows)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run matched local-LLM private and peer-exposure treatments"
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--tasks", type=int, default=1)
    parser.add_argument("--base-seed", type=int, default=10_000)
    parser.add_argument("--agents", type=int, default=7)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/agent_exploration/llm_institutional_pilot"),
    )
    args = parser.parse_args(argv)

    backend = CachedChatBackend(
        OpenAICompatibleLocalBackend(model=args.model, base_url=args.base_url),
        cache_dir=args.output / "completion_cache",
    )
    outcomes, actions, errors = run_llm_institutional_pilot(
        backend,
        n_tasks_per_scenario=args.tasks,
        base_seed=args.base_seed,
        num_agents=args.agents,
        workers=args.workers,
    )
    summary = summarize_pilot(outcomes)
    action_summary = summarize_action_effects(actions)
    paired_effects = paired_treatment_effects(outcomes)
    args.output.mkdir(parents=True, exist_ok=True)
    outcomes.to_csv(args.output / "llm_institutional_outcomes.csv", index=False)
    actions.to_csv(args.output / "llm_institutional_actions.csv", index=False)
    errors.to_csv(args.output / "llm_institutional_errors.csv", index=False)
    summary.to_csv(args.output / "llm_institutional_summary.csv", index=False)
    action_summary.to_csv(
        args.output / "llm_institutional_action_summary.csv", index=False
    )
    paired_effects.to_csv(
        args.output / "llm_institutional_paired_effects.csv", index=False
    )
    print(
        f"Wrote {len(outcomes)} outcomes, {len(actions)} action records, "
        f"and {len(errors)} errors to {args.output}"
    )
    return 0 if errors.empty else 2


if __name__ == "__main__":
    sys.exit(_main())
