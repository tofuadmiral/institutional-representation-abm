"""Compare proposal-aware review with a matched blind second decision."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from agent_exploration.local_models import (
    CachedChatBackend,
    ChatBackend,
    OpenAICompatibleLocalBackend,
)
from agent_exploration.objective_scenarios import (
    PreferenceScenario,
    generate_objective_task,
)
from agent_exploration.protected_mandates import (
    LocalModelProtectedAuthority,
    construct_protected_mandate,
    oracle_protected_choice,
)
from experiments.authority_safeguard_pilot import expand_policy_set


def run_blind_redecision(
    backend: ChatBackend,
    *,
    n_profiles_per_scenario: int = 12,
    base_seed: int = 72_000,
    num_agents: int = 7,
    workers: int = 1,
) -> pd.DataFrame:
    """Repeat the reviewer-position decision without exposing the proposal."""
    if n_profiles_per_scenario < 1:
        raise ValueError("n_profiles_per_scenario must be positive")
    if workers < 1:
        raise ValueError("workers must be positive")
    jobs = []
    for scenario_index, scenario in enumerate(PreferenceScenario):
        for repetition in range(n_profiles_per_scenario):
            seed = base_seed + scenario_index * n_profiles_per_scenario + repetition
            task = expand_policy_set(
                generate_objective_task(
                    seed=seed,
                    scenario=scenario,
                    num_agents=num_agents,
                )
            )
            principal_ids = tuple(principal.principal_id for principal in task.principals)
            for conflict in (False, True):
                mandate = construct_protected_mandate(
                    task,
                    principal_ids,
                    conflict=conflict,
                    seed=seed * 100 + int(conflict),
                )
                if mandate is not None:
                    jobs.append((scenario.value, seed, task, principal_ids, mandate))

    def evaluate(job):
        scenario, seed, task, principal_ids, mandate = job
        oracle = oracle_protected_choice(task, principal_ids, mandate)
        try:
            decision = LocalModelProtectedAuthority("blind-review-control", backend).choose_policy(
                task,
                principal_ids,
                mandate,
                seed=seed * 10_000 + 200,
                reveal_allowed_policy_ids=False,
            )
        except (ValueError, RuntimeError) as exc:
            return {
                "task_id": task.task_id,
                "scenario": scenario,
                "seed": seed,
                "model": backend.model,
                "conflict": mandate.conflicts_with_unconstrained_optimum,
                "presented_order": None,
                "model_choice": None,
                "protected_oracle_choice": oracle,
                "response_valid": False,
                "constraint_followed": False,
                "protected_oracle_match": False,
                "format_normalized": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {
            "task_id": task.task_id,
            "scenario": scenario,
            "seed": seed,
            "model": backend.model,
            "conflict": mandate.conflicts_with_unconstrained_optimum,
            "presented_order": json.dumps(decision.presented_order),
            "model_choice": decision.alternative_id,
            "protected_oracle_choice": oracle,
            "response_valid": True,
            "constraint_followed": decision.alternative_id in mandate.allowed_policy_ids,
            "protected_oracle_match": decision.alternative_id == oracle,
            "format_normalized": decision.format_normalized,
            "error": None,
        }

    if workers == 1:
        rows = [evaluate(job) for job in jobs]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            rows = list(executor.map(evaluate, jobs))
    return pd.DataFrame(rows)


def compare_proposal_review(
    blind: pd.DataFrame,
    safeguard_decisions: pd.DataFrame,
    *,
    bootstrap_repetitions: int = 10_000,
    bootstrap_seed: int = 202_609_08,
) -> pd.DataFrame:
    """Estimate proposal-exposure effects with profile-clustered resampling."""
    reviewer = safeguard_decisions[safeguard_decisions["role"] == "reviewer"].copy()
    keys = ["task_id", "conflict"]
    merged = blind.merge(
        reviewer,
        on=keys,
        suffixes=("_blind", "_proposal"),
        validate="one_to_one",
    )
    valid = merged["response_valid_blind"] & merged["response_valid_proposal"]
    merged = merged[valid].copy()
    if not (
        merged["presented_order_blind"] == merged["presented_order_proposal"]
    ).all():
        raise ValueError("blind and proposal-aware decisions must use identical order")
    rng = np.random.default_rng(bootstrap_seed)
    rows = []
    model_column = "model_blind" if "model_blind" in merged else "model"
    for scope_name, conflict in (("all", None), ("compatible", False), ("conflict", True)):
        scoped = merged if conflict is None else merged[merged["conflict"] == conflict]
        for metric in ("protected_oracle_match", "constraint_followed"):
            blind_values = scoped[f"{metric}_blind"].astype(float)
            proposal_values = scoped[f"{metric}_proposal"].astype(float)
            differences = proposal_values - blind_values
            indexed = pd.Series(differences.to_numpy(), index=scoped["task_id"])
            by_task = {
                task_id: group.to_numpy()
                for task_id, group in indexed.groupby(level=0)
            }
            task_ids = list(by_task)
            boot = []
            for _ in range(bootstrap_repetitions):
                sampled = rng.choice(task_ids, size=len(task_ids), replace=True)
                values = np.concatenate([by_task[task_id] for task_id in sampled])
                boot.append(float(values.mean()))
            rows.append(
                {
                    "model": str(scoped[model_column].iloc[0]),
                    "scope": scope_name,
                    "metric": metric,
                    "n_profiles": len(task_ids),
                    "n_profile_conditions": len(scoped),
                    "blind_rate": float(blind_values.mean()),
                    "proposal_review_rate": float(proposal_values.mean()),
                    "proposal_effect": float(differences.mean()),
                    "ci_low": float(np.quantile(boot, 0.025)),
                    "ci_high": float(np.quantile(boot, 0.975)),
                    "blind_wrong_proposal_right": int(
                        ((blind_values == 0) & (proposal_values == 1)).sum()
                    ),
                    "blind_right_proposal_wrong": int(
                        ((blind_values == 1) & (proposal_values == 0)).sum()
                    ),
                }
            )
    return pd.DataFrame(rows)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--review-decisions", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--profiles", type=int, default=12)
    parser.add_argument("--base-seed", type=int, default=72_000)
    parser.add_argument("--agents", type=int, default=7)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    backend = CachedChatBackend(
        OpenAICompatibleLocalBackend(model=args.model, base_url=args.base_url),
        cache_dir=args.output / "completion_cache",
    )
    blind = run_blind_redecision(
        backend,
        n_profiles_per_scenario=args.profiles,
        base_seed=args.base_seed,
        num_agents=args.agents,
        workers=args.workers,
    )
    comparison = compare_proposal_review(
        blind,
        pd.read_csv(args.review_decisions),
    )
    args.output.mkdir(parents=True, exist_ok=True)
    blind.to_csv(args.output / "blind_redecision.csv", index=False)
    comparison.to_csv(args.output / "proposal_review_effects.csv", index=False)
    print(f"Wrote {len(blind)} blind decisions and {len(comparison)} estimates")
    return 0 if blind["response_valid"].all() else 2


if __name__ == "__main__":
    sys.exit(_main())
