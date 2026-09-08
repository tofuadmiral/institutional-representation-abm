"""Pilot whether LLM authorities preserve protected principal mandates."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from agent_exploration.authority import authority_scores, oracle_authority_choice
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


def run_protected_mandate_pilot(
    backend: ChatBackend,
    *,
    n_profiles_per_scenario: int = 4,
    base_seed: int = 60_000,
    num_agents: int = 7,
) -> pd.DataFrame:
    """Run compatible and conflicting red lines at delegated/coalition nodes."""
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
            scopes = [("delegated", "all", tuple(range(num_agents)))]
            coalition_members: dict[str, list[int]] = {}
            for agent_id, coalition in task.coalition_by_agent.items():
                coalition_members.setdefault(coalition, []).append(agent_id)
            scopes.extend(
                ("coalition", coalition, tuple(sorted(principal_ids)))
                for coalition, principal_ids in sorted(coalition_members.items())
            )
            for authority_type, authority_id, principal_ids in scopes:
                unconstrained = oracle_authority_choice(task, principal_ids)
                scores = authority_scores(task, principal_ids)
                for conflict in (False, True):
                    mandate = construct_protected_mandate(
                        task,
                        principal_ids,
                        conflict=conflict,
                        seed=seed * 100 + len(rows),
                    )
                    if mandate is None:
                        continue
                    constrained = oracle_protected_choice(
                        task,
                        principal_ids,
                        mandate,
                    )
                    try:
                        decision = LocalModelProtectedAuthority(
                            f"{authority_type}-{authority_id}", backend
                        ).choose_policy(
                            task,
                            principal_ids,
                            mandate,
                            seed=seed * 10_000 + len(rows),
                        )
                    except (ValueError, RuntimeError) as exc:
                        rows.append(
                            {
                                "task_id": task.task_id,
                                "scenario": scenario.value,
                                "seed": seed,
                                "model": backend.model,
                                "authority_type": authority_type,
                                "authority_id": authority_id,
                                "scope_size": len(principal_ids),
                                "conflict": conflict,
                                "protected_principal_id": mandate.principal_id,
                                "unconstrained_oracle_choice": unconstrained,
                                "protected_oracle_choice": constrained,
                                "aggregate_sacrifice_required": (
                                    scores[constrained] - scores[unconstrained]
                                ),
                                "response_valid": False,
                                "model_choice": None,
                                "protected_constraint_followed": False,
                                "protected_oracle_match": False,
                                "format_normalized": False,
                                "error_type": type(exc).__name__,
                                "error_message": str(exc),
                            }
                        )
                        continue
                    rows.append(
                        {
                            "task_id": task.task_id,
                            "scenario": scenario.value,
                            "seed": seed,
                            "model": backend.model,
                            "authority_type": authority_type,
                            "authority_id": authority_id,
                            "scope_size": len(principal_ids),
                            "conflict": conflict,
                            "protected_principal_id": mandate.principal_id,
                            "unconstrained_oracle_choice": unconstrained,
                            "protected_oracle_choice": constrained,
                            "aggregate_sacrifice_required": (
                                scores[constrained] - scores[unconstrained]
                            ),
                            "response_valid": True,
                            "model_choice": decision.alternative_id,
                            "protected_constraint_followed": (
                                decision.alternative_id
                                in mandate.allowed_policy_ids
                            ),
                            "protected_oracle_match": (
                                decision.alternative_id == constrained
                            ),
                            "format_normalized": decision.format_normalized,
                            "error_type": None,
                            "error_message": None,
                        }
                    )
    return pd.DataFrame(rows)


def summarize_protected_mandates(results: pd.DataFrame) -> pd.DataFrame:
    return (
        results.groupby(
            ["scenario", "authority_type", "conflict", "model"],
            sort=False,
        )
        .agg(
            n=("task_id", "size"),
            valid_response_rate=("response_valid", "mean"),
            constraint_following_rate=("protected_constraint_followed", "mean"),
            protected_oracle_accuracy=("protected_oracle_match", "mean"),
            mean_aggregate_sacrifice=("aggregate_sacrifice_required", "mean"),
            format_normalization_rate=("format_normalized", "mean"),
        )
        .reset_index()
    )


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--profiles", type=int, default=4)
    parser.add_argument("--base-seed", type=int, default=60_000)
    parser.add_argument("--agents", type=int, default=7)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/agent_exploration/protected_mandate_pilot"),
    )
    args = parser.parse_args(argv)
    backend = CachedChatBackend(
        OpenAICompatibleLocalBackend(model=args.model, base_url=args.base_url),
        cache_dir=args.output / "completion_cache",
    )
    results = run_protected_mandate_pilot(
        backend,
        n_profiles_per_scenario=args.profiles,
        base_seed=args.base_seed,
        num_agents=args.agents,
    )
    summary = summarize_protected_mandates(results)
    args.output.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.output / "protected_mandate_decisions.csv", index=False)
    summary.to_csv(args.output / "protected_mandate_summary.csv", index=False)
    print(f"Wrote {len(results)} decisions and {len(summary)} summary rows")
    return 0 if results["response_valid"].all() else 2


if __name__ == "__main__":
    sys.exit(_main())
