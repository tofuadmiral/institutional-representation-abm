"""Compare single authority, independent panel, and override review safeguards."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd
import numpy as np

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
from agent_exploration.objectives import AgentAction, ObjectiveTask, PolicyAlternative
from agent_exploration.protected_mandates import (
    LocalModelProtectedAuthority,
    ProtectedMandate,
    construct_protected_mandate,
    oracle_protected_choice,
)


SINGLE_AUTHORITY = "single_authority"
INDEPENDENT_PANEL = "independent_panel"
OVERRIDE_REVIEW = "override_review"

EXPANDED_ALTERNATIVES = tuple(
    PolicyAlternative(alternative_id, (position, 0.0))
    for alternative_id, position in (
        ("p_neg_150", -1.5),
        ("p_neg_100", -1.0),
        ("p_neg_050", -0.5),
        ("p_000", 0.0),
        ("p_pos_050", 0.5),
        ("p_pos_100", 1.0),
        ("p_pos_150", 1.5),
    )
)


def expand_policy_set(task: ObjectiveTask) -> ObjectiveTask:
    """Replace the three-option development menu with seven ordered positions."""
    actions = tuple(
        AgentAction(
            agent_id=action.agent_id,
            principal_id=action.principal_id,
            alternative_id=min(
                EXPANDED_ALTERNATIVES,
                key=lambda alternative: (
                    sum(
                        (x - y) ** 2
                        for x, y in zip(
                            task.principal_for(action.principal_id).ideal_point,
                            alternative.position,
                        )
                    ),
                    alternative.alternative_id,
                ),
            ).alternative_id,
        )
        for action in task.initial_actions
    )
    return replace(
        task,
        alternatives=EXPANDED_ALTERNATIVES,
        initial_actions=actions,
        status_quo_id="p_000",
    )


def aggregate_panel_choices(task: ObjectiveTask, choices: Sequence[str]) -> str:
    """Use plurality across three authority decisions, with status quo for a tie."""
    if len(choices) != 3:
        raise ValueError("independent panel requires exactly three choices")
    counts = Counter(choices)
    highest = max(counts.values())
    winners = [choice for choice, count in counts.items() if count == highest]
    return winners[0] if len(winners) == 1 else task.status_quo_id


def run_authority_safeguard_pilot(
    backend: ChatBackend,
    *,
    n_profiles_per_scenario: int = 4,
    base_seed: int = 70_000,
    num_agents: int = 7,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run three matched authority institutions on derived threshold constraints."""
    if n_profiles_per_scenario < 1:
        raise ValueError("n_profiles_per_scenario must be positive")
    outcomes: list[dict] = []
    decisions: list[dict] = []
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
                if mandate is None:
                    continue
                _run_matched_institutions(
                    task,
                    principal_ids,
                    mandate,
                    backend,
                    seed=seed,
                    outcomes=outcomes,
                    decisions=decisions,
                )
    return pd.DataFrame(outcomes), pd.DataFrame(decisions)


def _run_matched_institutions(
    task: ObjectiveTask,
    principal_ids: tuple[int, ...],
    mandate: ProtectedMandate,
    backend: ChatBackend,
    *,
    seed: int,
    outcomes: list[dict],
    decisions: list[dict],
) -> None:
    oracle = oracle_protected_choice(task, principal_ids, mandate)
    unconstrained = oracle_authority_choice(task, principal_ids)
    scores = authority_scores(task, principal_ids)

    direct, direct_error = _safe_decision(
        task,
        principal_ids,
        mandate,
        backend,
        authority_id="single",
        seed=seed * 10_000 + 1,
    )
    _record_decision(
        decisions,
        task,
        mandate,
        oracle,
        role="single",
        member_index=0,
        decision=direct,
        error=direct_error,
    )
    _record_outcome(
        outcomes,
        task,
        mandate,
        oracle,
        unconstrained,
        scores,
        institution=SINGLE_AUTHORITY,
        choice=direct.alternative_id if direct else None,
        component_valid=direct is not None,
        decision_calls=1,
    )

    panel = []
    panel_valid = True
    for member_index in range(3):
        decision, error = _safe_decision(
            task,
            principal_ids,
            mandate,
            backend,
            authority_id=f"panel-{member_index}",
            seed=seed * 10_000 + 100 + member_index,
        )
        _record_decision(
            decisions,
            task,
            mandate,
            oracle,
            role="panel_member",
            member_index=member_index,
            decision=decision,
            error=error,
        )
        if decision is None:
            panel_valid = False
        else:
            panel.append(decision.alternative_id)
    panel_choice = aggregate_panel_choices(task, panel) if panel_valid else None
    _record_outcome(
        outcomes,
        task,
        mandate,
        oracle,
        unconstrained,
        scores,
        institution=INDEPENDENT_PANEL,
        choice=panel_choice,
        component_valid=panel_valid,
        decision_calls=3,
        panel_choices=json.dumps(panel),
    )

    if direct is None:
        reviewer = None
        review_error = "review skipped because the first authority was invalid"
    else:
        reviewer, review_error = _safe_decision(
            task,
            principal_ids,
            mandate,
            backend,
            authority_id="reviewer",
            seed=seed * 10_000 + 200,
            proposed_choice=direct.alternative_id,
        )
    _record_decision(
        decisions,
        task,
        mandate,
        oracle,
        role="reviewer",
        member_index=0,
        decision=reviewer,
        error=review_error,
        proposed_choice=direct.alternative_id if direct else None,
    )
    review_choice = reviewer.alternative_id if reviewer else None
    _record_outcome(
        outcomes,
        task,
        mandate,
        oracle,
        unconstrained,
        scores,
        institution=OVERRIDE_REVIEW,
        choice=review_choice,
        component_valid=reviewer is not None,
        decision_calls=2,
        proposed_choice=direct.alternative_id if direct else None,
        proposal_overridden=(
            review_choice != direct.alternative_id
            if reviewer is not None and direct is not None
            else None
        ),
    )


def _safe_decision(
    task: ObjectiveTask,
    principal_ids: tuple[int, ...],
    mandate: ProtectedMandate,
    backend: ChatBackend,
    *,
    authority_id: str,
    seed: int,
    proposed_choice: str | None = None,
):
    try:
        return (
            LocalModelProtectedAuthority(authority_id, backend).choose_policy(
                task,
                principal_ids,
                mandate,
                seed=seed,
                reveal_allowed_policy_ids=False,
                proposed_choice=proposed_choice,
            ),
            None,
        )
    except (ValueError, RuntimeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _record_decision(
    rows: list[dict],
    task: ObjectiveTask,
    mandate: ProtectedMandate,
    oracle: str,
    *,
    role: str,
    member_index: int,
    decision,
    error: str | None,
    proposed_choice: str | None = None,
) -> None:
    choice = decision.alternative_id if decision else None
    rows.append(
        {
            "task_id": task.task_id,
            "scenario": task.task_id.removeprefix("objective-").rsplit("-", 1)[0],
            "seed": int(task.task_id.rsplit("-", 1)[1]),
            "role": role,
            "member_index": member_index,
            "conflict": mandate.conflicts_with_unconstrained_optimum,
            "protected_principal_id": mandate.principal_id,
            "max_weighted_loss": mandate.max_weighted_loss,
            "presented_order": (
                json.dumps(decision.presented_order) if decision else None
            ),
            "proposed_choice": proposed_choice,
            "model_choice": choice,
            "protected_oracle_choice": oracle,
            "response_valid": decision is not None,
            "constraint_followed": (
                choice in mandate.allowed_policy_ids if choice is not None else False
            ),
            "protected_oracle_match": choice == oracle,
            "format_normalized": (
                decision.format_normalized if decision is not None else False
            ),
            "error": error,
        }
    )


def _record_outcome(
    rows: list[dict],
    task: ObjectiveTask,
    mandate: ProtectedMandate,
    oracle: str,
    unconstrained: str,
    scores: dict[str, float],
    *,
    institution: str,
    choice: str | None,
    component_valid: bool,
    decision_calls: int,
    **metadata,
) -> None:
    compliant = choice in mandate.allowed_policy_ids if choice is not None else False
    rows.append(
        {
            "task_id": task.task_id,
            "scenario": task.task_id.removeprefix("objective-").rsplit("-", 1)[0],
            "seed": int(task.task_id.rsplit("-", 1)[1]),
            "model": "",
            "institution": institution,
            "conflict": mandate.conflicts_with_unconstrained_optimum,
            "protected_principal_id": mandate.principal_id,
            "unconstrained_oracle_choice": unconstrained,
            "protected_oracle_choice": oracle,
            "aggregate_sacrifice_required": scores[oracle] - scores[unconstrained],
            "response_valid": component_valid,
            "collective_choice": choice,
            "constraint_followed": compliant,
            "protected_oracle_match": choice == oracle,
            "aggregate_regret_if_compliant": (
                scores[choice] - scores[oracle] if compliant and choice else None
            ),
            "decision_calls": decision_calls,
            **metadata,
        }
    )


def summarize_authority_safeguards(outcomes: pd.DataFrame) -> pd.DataFrame:
    return (
        outcomes.groupby(["scenario", "institution", "conflict"], sort=False)
        .agg(
            n=("task_id", "size"),
            valid_response_rate=("response_valid", "mean"),
            constraint_following_rate=("constraint_followed", "mean"),
            protected_oracle_accuracy=("protected_oracle_match", "mean"),
            mean_regret_if_compliant=("aggregate_regret_if_compliant", "mean"),
            mean_decision_calls=("decision_calls", "mean"),
        )
        .reset_index()
    )


def paired_safeguard_effects(
    outcomes: pd.DataFrame,
    *,
    bootstrap_repetitions: int = 10_000,
    bootstrap_seed: int = 202_609_08,
) -> pd.DataFrame:
    """Estimate paired effects while resampling whole synthetic profiles."""
    if bootstrap_repetitions < 1:
        raise ValueError("bootstrap_repetitions must be positive")
    rows: list[dict] = []
    scopes = (("all", None), ("compatible", False), ("conflict", True))
    models = outcomes["model"].unique() if "model" in outcomes else [""]
    rng = np.random.default_rng(bootstrap_seed)
    for model in models:
        model_rows = outcomes[outcomes["model"] == model] if model else outcomes
        for scope_name, conflict in scopes:
            scoped = (
                model_rows
                if conflict is None
                else model_rows[model_rows["conflict"] == conflict]
            )
            for metric in ("protected_oracle_match", "constraint_followed"):
                wide = scoped.pivot(
                    index=["task_id", "conflict"],
                    columns="institution",
                    values=metric,
                ).dropna()
                if SINGLE_AUTHORITY not in wide:
                    continue
                for comparison in (INDEPENDENT_PANEL, OVERRIDE_REVIEW):
                    if comparison not in wide:
                        continue
                    paired = wide[[SINGLE_AUTHORITY, comparison]].astype(float)
                    differences = paired[comparison] - paired[SINGLE_AUTHORITY]
                    by_task = {
                        task_id: group.to_numpy()
                        for task_id, group in differences.groupby(level="task_id")
                    }
                    task_ids = list(by_task)
                    boot = []
                    for _ in range(bootstrap_repetitions):
                        sampled = rng.choice(task_ids, size=len(task_ids), replace=True)
                        values = np.concatenate([by_task[task_id] for task_id in sampled])
                        boot.append(float(values.mean()))
                    rows.append(
                        {
                            "model": model,
                            "scope": scope_name,
                            "metric": metric,
                            "comparison": comparison,
                            "n_profiles": len(task_ids),
                            "n_profile_conditions": len(paired),
                            "single_rate": float(paired[SINGLE_AUTHORITY].mean()),
                            "comparison_rate": float(paired[comparison].mean()),
                            "paired_difference": float(differences.mean()),
                            "ci_low": float(np.quantile(boot, 0.025)),
                            "ci_high": float(np.quantile(boot, 0.975)),
                            "single_wrong_comparison_right": int(
                                (
                                    (paired[SINGLE_AUTHORITY] == 0)
                                    & (paired[comparison] == 1)
                                ).sum()
                            ),
                            "single_right_comparison_wrong": int(
                                (
                                    (paired[SINGLE_AUTHORITY] == 1)
                                    & (paired[comparison] == 0)
                                ).sum()
                            ),
                        }
                    )
    return pd.DataFrame(rows)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--profiles", type=int, default=4)
    parser.add_argument("--base-seed", type=int, default=70_000)
    parser.add_argument("--agents", type=int, default=7)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/agent_exploration/authority_safeguard_pilot"),
    )
    args = parser.parse_args(argv)
    backend = CachedChatBackend(
        OpenAICompatibleLocalBackend(model=args.model, base_url=args.base_url),
        cache_dir=args.output / "completion_cache",
    )
    outcomes, decisions = run_authority_safeguard_pilot(
        backend,
        n_profiles_per_scenario=args.profiles,
        base_seed=args.base_seed,
        num_agents=args.agents,
    )
    outcomes["model"] = args.model
    decisions["model"] = args.model
    summary = summarize_authority_safeguards(outcomes)
    paired = paired_safeguard_effects(outcomes)
    args.output.mkdir(parents=True, exist_ok=True)
    outcomes.to_csv(args.output / "authority_safeguard_outcomes.csv", index=False)
    decisions.to_csv(args.output / "authority_safeguard_decisions.csv", index=False)
    summary.to_csv(args.output / "authority_safeguard_summary.csv", index=False)
    paired.to_csv(args.output / "authority_safeguard_paired_effects.csv", index=False)
    print(
        f"Wrote {len(outcomes)} outcomes, {len(decisions)} decisions, and "
        f"{len(paired)} paired estimates"
    )
    return 0 if outcomes["response_valid"].all() else 2


if __name__ == "__main__":
    sys.exit(_main())
