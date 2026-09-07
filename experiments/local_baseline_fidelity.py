"""Validate local-model representation fidelity before multi-agent treatment."""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from agent_exploration.local_models import (
    CachedChatBackend,
    ChatBackend,
    OpenAICompatibleLocalBackend,
)
from agent_exploration.objective_scenarios import PreferenceScenario, generate_objective_task
from agent_exploration.objectives import preference_distance
from agent_exploration.representatives import LocalModelRepresentative


def run_local_baseline_fidelity(
    backend: ChatBackend,
    *,
    n_tasks_per_scenario: int = 5,
    base_seed: int = 0,
    num_agents: int = 7,
    workers: int = 1,
) -> pd.DataFrame:
    """Compare model choices with the mechanically nearest alternative."""
    if n_tasks_per_scenario < 1:
        raise ValueError("n_tasks_per_scenario must be positive")
    if workers < 1:
        raise ValueError("workers must be positive")
    jobs = []
    for scenario_index, scenario in enumerate(PreferenceScenario):
        for repetition in range(n_tasks_per_scenario):
            seed = base_seed + scenario_index * n_tasks_per_scenario + repetition
            task = generate_objective_task(
                seed=seed, scenario=scenario, num_agents=num_agents
            )
            for agent_id, principal in enumerate(task.principals):
                jobs.append((scenario, seed, task, agent_id, principal))

    def evaluate(job):
        scenario, seed, task, agent_id, principal = job
        representative = LocalModelRepresentative(agent_id, principal, backend)
        presented_alternatives = list(task.alternatives)
        order_rng = random.Random(seed * 10_000 + agent_id)
        order_rng.shuffle(presented_alternatives)
        presented_ids = [a.alternative_id for a in presented_alternatives]
        oracle = task.action_for_agent(agent_id)
        oracle_alternative = task.alternative_for(oracle.alternative_id)
        oracle_loss = preference_distance(
            principal.ideal_point, oracle_alternative.position
        )
        row = {
            "task_id": task.task_id,
            "scenario": scenario.value,
            "seed": seed,
            "agent_id": agent_id,
            "principal_id": principal.principal_id,
            "model": backend.model,
            "presented_order": json.dumps(presented_ids),
            "oracle_presented_position": presented_ids.index(oracle.alternative_id) + 1,
            "oracle_choice": oracle.alternative_id,
            "oracle_loss": oracle_loss,
        }
        try:
            action = representative.choose_initial_action(presented_alternatives)
        except (ValueError, RuntimeError) as exc:
            row.update(
                {
                    "response_valid": False,
                    "model_choice": None,
                    "model_presented_position": None,
                    "exact_choice_match": False,
                    "exact_choice_match_valid": None,
                    "model_loss": None,
                    "excess_representation_loss": None,
                    "rationale": "",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
            return row

        chosen = task.alternative_for(action.alternative_id)
        chosen_loss = preference_distance(principal.ideal_point, chosen.position)
        exact_match = action.alternative_id == oracle.alternative_id
        row.update(
            {
                "response_valid": True,
                "model_choice": action.alternative_id,
                "model_presented_position": presented_ids.index(action.alternative_id)
                + 1,
                "exact_choice_match": exact_match,
                "exact_choice_match_valid": exact_match,
                "model_loss": chosen_loss,
                "excess_representation_loss": chosen_loss - oracle_loss,
                "rationale": action.rationale,
                "error_type": None,
                "error_message": None,
            }
        )
        return row

    if workers == 1:
        rows = [evaluate(job) for job in jobs]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            rows = list(executor.map(evaluate, jobs))
    return pd.DataFrame(rows)


def summarize_local_baseline(results: pd.DataFrame) -> pd.DataFrame:
    return (
        results.groupby(["scenario", "model"], sort=False)
        .agg(
            n=("task_id", "size"),
            valid_response_rate=("response_valid", "mean"),
            exact_choice_accuracy=("exact_choice_match", "mean"),
            valid_choice_accuracy=("exact_choice_match_valid", "mean"),
            mean_model_loss=("model_loss", "mean"),
            mean_excess_representation_loss=("excess_representation_loss", "mean"),
        )
        .reset_index()
    )


def assess_baseline_gate(
    results: pd.DataFrame,
    *,
    min_exact_accuracy: float = 0.95,
    max_invalid_rate: float = 0.01,
    max_position_accuracy_gap: float = 0.05,
) -> dict:
    """Apply the predeclared fidelity and option-order stopping rules."""
    position_accuracy = (
        results.groupby("oracle_presented_position")["exact_choice_match"]
        .mean()
        .sort_index()
    )
    position_gap = float(position_accuracy.max() - position_accuracy.min())
    exact_accuracy = float(results["exact_choice_match"].mean())
    invalid_rate = float(1.0 - results["response_valid"].mean())
    passed = (
        exact_accuracy >= min_exact_accuracy
        and invalid_rate < max_invalid_rate
        and position_gap <= max_position_accuracy_gap
    )
    return {
        "passed": bool(passed),
        "n": int(len(results)),
        "exact_choice_accuracy": exact_accuracy,
        "invalid_response_rate": invalid_rate,
        "accuracy_by_oracle_position": {
            str(int(position)): float(accuracy)
            for position, accuracy in position_accuracy.items()
        },
        "position_accuracy_gap": position_gap,
        "thresholds": {
            "min_exact_accuracy": min_exact_accuracy,
            "max_invalid_rate_exclusive": max_invalid_rate,
            "max_position_accuracy_gap": max_position_accuracy_gap,
        },
    }


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an open-weight local model as a representative"
    )
    parser.add_argument("--model", required=True, help="Model id exposed by local server")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--tasks", type=int, default=5)
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--agents", type=int, default=7)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--output", type=Path, default=Path("results/agent_exploration")
    )
    args = parser.parse_args(argv)

    backend = CachedChatBackend(
        OpenAICompatibleLocalBackend(model=args.model, base_url=args.base_url),
        cache_dir=args.output / "completion_cache",
    )
    results = run_local_baseline_fidelity(
        backend,
        n_tasks_per_scenario=args.tasks,
        base_seed=args.base_seed,
        num_agents=args.agents,
        workers=args.workers,
    )
    summary = summarize_local_baseline(results)
    gate = assess_baseline_gate(results)
    args.output.mkdir(parents=True, exist_ok=True)
    long_path = args.output / "local_baseline_fidelity_long.csv"
    summary_path = args.output / "local_baseline_fidelity_summary.csv"
    gate_path = args.output / "local_baseline_gate.json"
    results.to_csv(long_path, index=False)
    summary.to_csv(summary_path, index=False)
    gate_path.write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {len(results)} rows to {long_path}")
    print(f"Wrote {len(summary)} rows to {summary_path}")
    print(f"Wrote baseline gate to {gate_path}: {'PASS' if gate['passed'] else 'FAIL'}")
    return 0 if gate["passed"] else 2


if __name__ == "__main__":
    sys.exit(_main())
