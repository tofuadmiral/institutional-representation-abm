"""Map the structural effects of the frozen authority rules without an LLM."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from agent_exploration.authority import oracle_authority_choice
from agent_exploration.objective_metrics import evaluate_outcome
from agent_exploration.objective_protocols import collective_choice, private_ballot
from agent_exploration.objective_scenarios import (
    PreferenceScenario,
    generate_objective_task,
)
from agent_exploration.objectives import AgentAction, CollectiveOutcome, ObjectiveTask


ORACLE_DELEGATED_AUTHORITY = "oracle_delegated_authority"
ORACLE_COALITION_AUTHORITY = "oracle_coalition_authority"


def oracle_delegated_authority(task: ObjectiveTask) -> CollectiveOutcome:
    """Choose the global weighted-loss optimum and bind every representative."""
    principal_ids = tuple(principal.principal_id for principal in task.principals)
    choice = oracle_authority_choice(task, principal_ids)
    return CollectiveOutcome(
        institution=ORACLE_DELEGATED_AUTHORITY,
        final_actions=tuple(
            AgentAction(action.agent_id, action.principal_id, choice)
            for action in task.initial_actions
        ),
        collective_choice_id=choice,
        metadata={"effective_decision_makers": 1},
    )


def oracle_coalition_authority(task: ObjectiveTask) -> CollectiveOutcome:
    """Choose each coalition's weighted-loss optimum and bind its members."""
    members: dict[str, list[int]] = {}
    for action in task.initial_actions:
        coalition = task.coalition_by_agent[action.agent_id]
        members.setdefault(coalition, []).append(action.principal_id)
    platforms = {
        coalition: oracle_authority_choice(task, principal_ids)
        for coalition, principal_ids in sorted(members.items())
    }
    actions = tuple(
        AgentAction(
            action.agent_id,
            action.principal_id,
            platforms[task.coalition_by_agent[action.agent_id]],
        )
        for action in task.initial_actions
    )
    return CollectiveOutcome(
        institution=ORACLE_COALITION_AUTHORITY,
        final_actions=actions,
        collective_choice_id=collective_choice(task, actions),
        metadata={
            "effective_decision_makers": len(platforms),
            "coalition_platforms": platforms,
        },
    )


def run_oracle_landscape(
    *,
    n_profiles_per_scenario: int = 1_000,
    base_seed: int = 50_000,
    num_agents: int = 7,
) -> pd.DataFrame:
    """Evaluate exact institution-specific outcomes on synthetic profiles."""
    if n_profiles_per_scenario < 1:
        raise ValueError("n_profiles_per_scenario must be positive")
    rows: list[dict] = []
    for scenario_index, scenario in enumerate(PreferenceScenario):
        for repetition in range(n_profiles_per_scenario):
            seed = base_seed + scenario_index * n_profiles_per_scenario + repetition
            task = generate_objective_task(
                seed=seed,
                scenario=scenario,
                num_agents=num_agents,
            )
            private = private_ballot(task)
            private_metrics = evaluate_outcome(task, private)
            for outcome in (
                private,
                oracle_delegated_authority(task),
                oracle_coalition_authority(task),
            ):
                metrics = evaluate_outcome(task, outcome)
                metrics.update(
                    {
                        "scenario": scenario.value,
                        "seed": seed,
                        "num_agents": num_agents,
                        "private_collective_choice_id": private.collective_choice_id,
                        "collective_choice_changed_vs_private": (
                            outcome.collective_choice_id
                            != private.collective_choice_id
                        ),
                        "structural_loss_delta_vs_private": (
                            metrics["outcome_loss_mean"]
                            - private_metrics["outcome_loss_mean"]
                        ),
                        "worst_group_loss_delta_vs_private": (
                            metrics["outcome_loss_worst_group"]
                            - private_metrics["outcome_loss_worst_group"]
                        ),
                    }
                )
                rows.append(metrics)
    return pd.DataFrame(rows)


def summarize_oracle_landscape(results: pd.DataFrame) -> pd.DataFrame:
    """Summarize profile-level structural effects without pseudo-replication."""
    return (
        results.groupby(["scenario", "institution"], sort=False)
        .agg(
            n_profiles=("task_id", "size"),
            outcome_change_rate=("collective_choice_changed_vs_private", "mean"),
            mean_structural_loss=("structural_loss_delta_vs_private", "mean"),
            median_structural_loss=("structural_loss_delta_vs_private", "median"),
            mean_worst_group_loss_delta=(
                "worst_group_loss_delta_vs_private",
                "mean",
            ),
            mean_preference_retention=("preference_retention_rate", "mean"),
            pareto_violation_rate=("pareto_dominated", "mean"),
        )
        .reset_index()
    )


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=int, default=1_000)
    parser.add_argument("--base-seed", type=int, default=50_000)
    parser.add_argument("--agents", type=int, default=7)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/agent_exploration/authority_oracle_landscape"),
    )
    args = parser.parse_args(argv)
    results = run_oracle_landscape(
        n_profiles_per_scenario=args.profiles,
        base_seed=args.base_seed,
        num_agents=args.agents,
    )
    summary = summarize_oracle_landscape(results)
    args.output.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.output / "oracle_authority_outcomes.csv", index=False)
    summary.to_csv(args.output / "oracle_authority_summary.csv", index=False)
    print(f"Wrote {len(results)} outcomes and {len(summary)} summary rows")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
