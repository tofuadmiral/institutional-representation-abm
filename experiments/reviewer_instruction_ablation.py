"""Compare neutral proposal exposure with blind and anti-deference review."""

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


def run_neutral_proposal_decisions(
    backend: ChatBackend,
    safeguard_decisions: pd.DataFrame,
    *,
    n_profiles_per_scenario: int = 12,
    base_seed: int = 72_000,
    num_agents: int = 7,
    workers: int = 1,
) -> pd.DataFrame:
    """Expose the original proposal without anti-deference review language."""
    if n_profiles_per_scenario < 1:
        raise ValueError("n_profiles_per_scenario must be positive")
    if workers < 1:
        raise ValueError("workers must be positive")
    singles = safeguard_decisions[safeguard_decisions["role"] == "single"].copy()
    proposals = singles.set_index(["task_id", "conflict"])["model_choice"].to_dict()
    jobs = []
    for scenario_index, scenario in enumerate(PreferenceScenario):
        for repetition in range(n_profiles_per_scenario):
            seed = base_seed + scenario_index * n_profiles_per_scenario + repetition
            task = expand_policy_set(
                generate_objective_task(
                    seed=seed, scenario=scenario, num_agents=num_agents
                )
            )
            principal_ids = tuple(
                principal.principal_id for principal in task.principals
            )
            for conflict in (False, True):
                mandate = construct_protected_mandate(
                    task,
                    principal_ids,
                    conflict=conflict,
                    seed=seed * 100 + int(conflict),
                )
                if mandate is None:
                    continue
                key = (task.task_id, mandate.conflicts_with_unconstrained_optimum)
                if key not in proposals or pd.isna(proposals[key]):
                    raise ValueError(
                        f"missing valid single-authority proposal for {key}"
                    )
                jobs.append(
                    (
                        scenario.value,
                        seed,
                        task,
                        principal_ids,
                        mandate,
                        str(proposals[key]),
                    )
                )

    def evaluate(job):
        scenario, seed, task, principal_ids, mandate, proposed_choice = job
        oracle = oracle_protected_choice(task, principal_ids, mandate)
        try:
            decision = LocalModelProtectedAuthority(
                "neutral-proposal-reviewer", backend
            ).choose_policy(
                task,
                principal_ids,
                mandate,
                seed=seed * 10_000 + 200,
                reveal_allowed_policy_ids=False,
                proposed_choice=proposed_choice,
                proposal_instruction="neutral",
            )
        except (ValueError, RuntimeError) as exc:
            return {
                "task_id": task.task_id,
                "scenario": scenario,
                "seed": seed,
                "model": backend.model,
                "conflict": mandate.conflicts_with_unconstrained_optimum,
                "presented_order": None,
                "proposed_choice": proposed_choice,
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
            "proposed_choice": proposed_choice,
            "model_choice": decision.alternative_id,
            "protected_oracle_choice": oracle,
            "response_valid": True,
            "constraint_followed": decision.alternative_id
            in mandate.allowed_policy_ids,
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


def compare_reviewer_instructions(
    blind: pd.DataFrame,
    neutral: pd.DataFrame,
    safeguard_decisions: pd.DataFrame,
    *,
    bootstrap_repetitions: int = 10_000,
    bootstrap_seed: int = 202_609_08,
) -> pd.DataFrame:
    """Estimate paired arm contrasts with profile-clustered resampling."""
    anti = safeguard_decisions[safeguard_decisions["role"] == "reviewer"].copy()
    keys = ["task_id", "conflict"]
    merged = blind.merge(
        neutral,
        on=keys,
        suffixes=("_blind", "_neutral"),
        validate="one_to_one",
    )
    merged = merged.merge(anti, on=keys, validate="one_to_one")
    valid = (
        merged["response_valid_blind"]
        & merged["response_valid_neutral"]
        & merged["response_valid"]
    )
    merged = merged[valid].copy()
    if not (
        (merged["presented_order_blind"] == merged["presented_order_neutral"])
        & (merged["presented_order_blind"] == merged["presented_order"])
    ).all():
        raise ValueError("all reviewer arms must use identical option order")

    rng = np.random.default_rng(bootstrap_seed)
    rows = []
    contrasts = (
        ("neutral_minus_blind", "blind", "neutral"),
        ("anti_minus_neutral", "neutral", "anti"),
        ("anti_minus_blind", "blind", "anti"),
    )
    for scope_name, conflict in (
        ("all", None),
        ("compatible", False),
        ("conflict", True),
    ):
        scoped = merged if conflict is None else merged[merged["conflict"] == conflict]
        for metric in ("protected_oracle_match", "constraint_followed"):
            values = {
                "blind": scoped[f"{metric}_blind"].astype(float),
                "neutral": scoped[f"{metric}_neutral"].astype(float),
                "anti": scoped[metric].astype(float),
            }
            for contrast, left, right in contrasts:
                differences = values[right] - values[left]
                by_task = {
                    task_id: group.to_numpy()
                    for task_id, group in pd.Series(
                        differences.to_numpy(), index=scoped["task_id"]
                    ).groupby(level=0)
                }
                task_ids = list(by_task)
                boot = []
                for _ in range(bootstrap_repetitions):
                    sampled = rng.choice(task_ids, size=len(task_ids), replace=True)
                    boot.append(
                        float(
                            np.concatenate(
                                [by_task[task_id] for task_id in sampled]
                            ).mean()
                        )
                    )
                rows.append(
                    {
                        "model": str(scoped["model_blind"].iloc[0]),
                        "scope": scope_name,
                        "metric": metric,
                        "contrast": contrast,
                        "n_profiles": len(task_ids),
                        "n_profile_conditions": len(scoped),
                        "left_rate": float(values[left].mean()),
                        "right_rate": float(values[right].mean()),
                        "effect": float(differences.mean()),
                        "ci_low": float(np.quantile(boot, 0.025)),
                        "ci_high": float(np.quantile(boot, 0.975)),
                        "left_wrong_right_correct": int(
                            ((values[left] == 0) & (values[right] == 1)).sum()
                        ),
                        "left_correct_right_wrong": int(
                            ((values[left] == 1) & (values[right] == 0)).sum()
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--review-decisions", type=Path, required=True)
    parser.add_argument("--blind-decisions", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--profiles", type=int, default=12)
    parser.add_argument("--base-seed", type=int, default=72_000)
    parser.add_argument("--agents", type=int, default=7)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    safeguard = pd.read_csv(args.review_decisions)
    backend = CachedChatBackend(
        OpenAICompatibleLocalBackend(model=args.model, base_url=args.base_url),
        cache_dir=args.output / "completion_cache",
    )
    neutral = run_neutral_proposal_decisions(
        backend,
        safeguard,
        n_profiles_per_scenario=args.profiles,
        base_seed=args.base_seed,
        num_agents=args.agents,
        workers=args.workers,
    )
    comparison = compare_reviewer_instructions(
        pd.read_csv(args.blind_decisions), neutral, safeguard
    )
    args.output.mkdir(parents=True, exist_ok=True)
    neutral.to_csv(args.output / "neutral_proposal_decisions.csv", index=False)
    comparison.to_csv(args.output / "reviewer_instruction_effects.csv", index=False)
    print(f"Wrote {len(neutral)} neutral decisions and {len(comparison)} estimates")
    return 0 if neutral["response_valid"].all() else 2


if __name__ == "__main__":
    sys.exit(_main())
