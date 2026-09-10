"""Recombine fixed reviewer decisions under alternative authority rules."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd


BROAD_OVERRIDE = "broad_override"
VIOLATION_ONLY_OVERRIDE = "violation_only_override"
MECHANICAL_ENFORCEMENT = "mechanical_enforcement"


def apply_reviewer_authority_rules(decisions: pd.DataFrame) -> pd.DataFrame:
    """Hold decisions fixed and vary when a reviewer has binding authority."""
    keys = ["task_id", "conflict"]
    single = decisions[decisions["role"] == "single"].copy()
    reviewer = decisions[decisions["role"] == "reviewer"].copy()
    matched = single.merge(
        reviewer,
        on=keys,
        suffixes=("_single", "_reviewer"),
        validate="one_to_one",
    )
    if not (
        matched["response_valid_single"] & matched["response_valid_reviewer"]
    ).all():
        raise ValueError("authority-rule analysis requires valid matched decisions")

    rows = []
    for record in matched.to_dict(orient="records"):
        proposal_violates = not bool(record["constraint_followed_single"])
        rules = {
            BROAD_OVERRIDE: record["model_choice_reviewer"],
            VIOLATION_ONLY_OVERRIDE: (
                record["model_choice_reviewer"]
                if proposal_violates
                else record["model_choice_single"]
            ),
            MECHANICAL_ENFORCEMENT: (
                record["protected_oracle_choice_single"]
                if proposal_violates
                else record["model_choice_single"]
            ),
        }
        for rule, final_choice in rules.items():
            if final_choice == record["model_choice_single"]:
                constraint_followed = bool(record["constraint_followed_single"])
            elif final_choice == record["model_choice_reviewer"]:
                constraint_followed = bool(record["constraint_followed_reviewer"])
            else:
                constraint_followed = True
            rows.append(
                {
                    "task_id": record["task_id"],
                    "scenario": record["scenario_single"],
                    "conflict": record["conflict"],
                    "model": record.get("model_single", ""),
                    "authority_rule": rule,
                    "proposal_choice": record["model_choice_single"],
                    "reviewer_choice": record["model_choice_reviewer"],
                    "final_choice": final_choice,
                    "protected_oracle_choice": record["protected_oracle_choice_single"],
                    "proposal_violates_constraint": proposal_violates,
                    "reviewer_authorized": (
                        rule == BROAD_OVERRIDE
                        or (rule == VIOLATION_ONLY_OVERRIDE and proposal_violates)
                    ),
                    "constraint_followed": constraint_followed,
                    "protected_oracle_match": final_choice
                    == record["protected_oracle_choice_single"],
                }
            )
    return pd.DataFrame(rows)


def summarize_authority_rules(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Summarize outcome fidelity for each recombined authority rule."""
    return (
        outcomes.groupby("authority_rule", as_index=False)
        .agg(
            n=("task_id", "size"),
            exact_rate=("protected_oracle_match", "mean"),
            compliance_rate=("constraint_followed", "mean"),
            reviewer_authorization_rate=("reviewer_authorized", "mean"),
        )
        .sort_values("authority_rule")
        .reset_index(drop=True)
    )


def paired_gate_effects(
    outcomes: pd.DataFrame,
    *,
    bootstrap_repetitions: int = 10_000,
    bootstrap_seed: int = 202_609_08,
) -> pd.DataFrame:
    """Compare gated rules with broad override using profile-clustered intervals."""
    wide = outcomes.pivot(
        index=["task_id", "conflict"],
        columns="authority_rule",
        values=["protected_oracle_match", "constraint_followed"],
    )
    rng = np.random.default_rng(bootstrap_seed)
    rows = []
    for rule in (VIOLATION_ONLY_OVERRIDE, MECHANICAL_ENFORCEMENT):
        for metric in ("protected_oracle_match", "constraint_followed"):
            differences = wide[(metric, rule)].astype(float) - wide[
                (metric, BROAD_OVERRIDE)
            ].astype(float)
            indexed = pd.Series(
                differences.to_numpy(),
                index=wide.index.get_level_values("task_id"),
            )
            by_task = {
                task_id: group.to_numpy() for task_id, group in indexed.groupby(level=0)
            }
            task_ids = list(by_task)
            boot = []
            for _ in range(bootstrap_repetitions):
                sampled = rng.choice(task_ids, size=len(task_ids), replace=True)
                boot.append(
                    float(
                        np.concatenate([by_task[task_id] for task_id in sampled]).mean()
                    )
                )
            rows.append(
                {
                    "comparison": f"{rule}_minus_{BROAD_OVERRIDE}",
                    "metric": metric,
                    "n_profiles": len(task_ids),
                    "n_profile_conditions": len(differences),
                    "effect": float(differences.mean()),
                    "ci_low": float(np.quantile(boot, 0.025)),
                    "ci_high": float(np.quantile(boot, 0.975)),
                    "broad_wrong_rule_correct": int((differences == 1).sum()),
                    "broad_correct_rule_wrong": int((differences == -1).sum()),
                }
            )
    return pd.DataFrame(rows)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    outcomes = apply_reviewer_authority_rules(pd.read_csv(args.decisions))
    summary = summarize_authority_rules(outcomes)
    effects = paired_gate_effects(outcomes)
    args.output.mkdir(parents=True, exist_ok=True)
    outcomes.to_csv(args.output / "reviewer_authority_outcomes.csv", index=False)
    summary.to_csv(args.output / "reviewer_authority_summary.csv", index=False)
    effects.to_csv(args.output / "reviewer_authority_effects.csv", index=False)
    print(f"Wrote {len(outcomes)} recombined outcomes and {len(effects)} estimates")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
