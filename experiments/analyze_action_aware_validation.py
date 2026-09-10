"""Analyze the frozen action-aware reviewer validation across models."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from experiments.action_aware_reviewer_validation import (
    ACTION_AWARE_BROAD,
    BASE_SEED,
    BOOTSTRAP_REPETITIONS,
    BOOTSTRAP_SEED,
    EVIDENCE_GATE,
    NUM_AGENTS,
    TASKS_PER_SCENARIO,
    paired_effects,
)
from experiments.prospective_certificate_gate import (
    BROAD_OVERRIDE,
    collect_multi_eligible_conflict_tasks,
)


def recommendation_diagnostics(reviews: pd.DataFrame) -> pd.DataFrame:
    """Measure recommendation quality separately from binding disposition."""
    task_mandates = {
        task.task_id: mandate
        for _, _, task, _, mandate, _ in collect_multi_eligible_conflict_tasks(
            tasks_per_scenario=TASKS_PER_SCENARIO,
            base_seed=BASE_SEED,
            num_agents=NUM_AGENTS,
        )
    }
    diagnosed = reviews.copy()
    diagnosed["recommendation_exact"] = (
        diagnosed["recommended_policy_id"] == diagnosed["protected_oracle_choice"]
    )
    diagnosed["recommendation_compliant"] = diagnosed.apply(
        lambda row: (
            row["response_valid"]
            and row["recommended_policy_id"]
            in task_mandates[row["task_id"]].allowed_policy_ids
        ),
        axis=1,
    )
    diagnosed["recommendation_changes_proposal"] = (
        diagnosed["recommended_policy_id"] != diagnosed["proposal_choice"]
    )
    return (
        diagnosed.groupby(["model", "proposal_state", "disposition"], as_index=False)
        .agg(
            n=("task_id", "size"),
            recommendation_exact_rate=("recommendation_exact", "mean"),
            recommendation_compliance_rate=("recommendation_compliant", "mean"),
            recommendation_change_rate=("recommendation_changes_proposal", "mean"),
        )
        .sort_values(["model", "proposal_state", "disposition"])
    )


def disposition_summary(reviews: pd.DataFrame) -> pd.DataFrame:
    """Report parse and disposition rates without pooling models."""
    rows = []
    for (model, state), scoped in reviews.groupby(["model", "proposal_state"]):
        valid = scoped[scoped["response_valid"]]
        row = {
            "model": model,
            "proposal_state": state,
            "n": len(scoped),
            "parse_rate": scoped["response_valid"].mean(),
            "certificate_fields_valid_rate": scoped[
                "certificate_fields_valid"
            ].mean(),
        }
        for disposition in ("retain", "replace", "escalate"):
            row[f"{disposition}_rate"] = (
                (valid["disposition"] == disposition).mean()
                if len(valid)
                else float("nan")
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["model", "proposal_state"])


def institutional_summary(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Report action-aware broad and gate outcome rates by model and state."""
    return (
        outcomes[outcomes["institution"].isin((ACTION_AWARE_BROAD, EVIDENCE_GATE))]
        .groupby(["model", "proposal_state", "institution"], as_index=False)
        .agg(
            n=("task_id", "size"),
            exact_rate=("protected_oracle_match", "mean"),
            compliance_rate=("constraint_followed", "mean"),
            override_rate=("proposal_overridden", "mean"),
        )
        .sort_values(["model", "proposal_state", "institution"])
    )


def model_specific_gate_effects(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Compute paired task-cluster effects separately for each model."""
    rows = []
    for model, scoped in outcomes.groupby("model"):
        effects = paired_effects(scoped)
        effects.insert(0, "model", model)
        rows.append(effects)
    return pd.concat(rows, ignore_index=True)


def matched_schema_effects(
    action_outcomes: pd.DataFrame,
    forced_outcomes: pd.DataFrame,
) -> pd.DataFrame:
    """Compare action-aware broad review with forced-recommendation broad review."""
    action = action_outcomes[action_outcomes["institution"] == ACTION_AWARE_BROAD]
    forced = forced_outcomes[forced_outcomes["institution"] == BROAD_OVERRIDE]
    keys = ["model", "task_id", "proposal_state"]
    merged = action.merge(
        forced,
        on=keys,
        suffixes=("_action", "_forced"),
        validate="one_to_one",
    )
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    rows = []
    for (model, state), scoped in merged.groupby(["model", "proposal_state"]):
        for metric in ("protected_oracle_match", "constraint_followed"):
            action_values = scoped[f"{metric}_action"].astype(float).to_numpy()
            forced_values = scoped[f"{metric}_forced"].astype(float).to_numpy()
            differences = action_values - forced_values
            boot = np.empty(BOOTSTRAP_REPETITIONS)
            for index in range(BOOTSTRAP_REPETITIONS):
                sampled = rng.integers(0, len(scoped), size=len(scoped))
                boot[index] = differences[sampled].mean()
            rows.append(
                {
                    "model": model,
                    "proposal_state": state,
                    "metric": metric,
                    "n_tasks": len(scoped),
                    "forced_broad_rate": forced_values.mean(),
                    "action_aware_broad_rate": action_values.mean(),
                    "effect": differences.mean(),
                    "ci_low": np.quantile(boot, 0.025),
                    "ci_high": np.quantile(boot, 0.975),
                    "forced_wrong_action_correct": int((differences == 1).sum()),
                    "forced_correct_action_wrong": int((differences == -1).sum()),
                }
            )
    return pd.DataFrame(rows)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action-reviews", type=Path, nargs="+", required=True)
    parser.add_argument("--action-outcomes", type=Path, nargs="+", required=True)
    parser.add_argument("--forced-outcomes", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    reviews = pd.concat(
        [pd.read_csv(path) for path in args.action_reviews], ignore_index=True
    )
    action_outcomes = pd.concat(
        [pd.read_csv(path) for path in args.action_outcomes], ignore_index=True
    )
    forced_outcomes = pd.concat(
        [pd.read_csv(path) for path in args.forced_outcomes], ignore_index=True
    )
    args.output.mkdir(parents=True, exist_ok=True)
    disposition_summary(reviews).to_csv(
        args.output / "disposition_summary.csv", index=False
    )
    recommendation_diagnostics(reviews).to_csv(
        args.output / "recommendation_diagnostics.csv", index=False
    )
    institutional_summary(action_outcomes).to_csv(
        args.output / "institutional_summary.csv", index=False
    )
    model_specific_gate_effects(action_outcomes).to_csv(
        args.output / "gate_effects.csv", index=False
    )
    matched_schema_effects(action_outcomes, forced_outcomes).to_csv(
        args.output / "matched_schema_effects.csv", index=False
    )
    print(f"Analyzed {len(reviews)} reviews across {reviews['model'].nunique()} models")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
