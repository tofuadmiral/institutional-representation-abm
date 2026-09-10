"""Cross-model analysis for the prospective certificate-gate replications."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from experiments.prospective_certificate_gate import (
    AGGREGATE_PRESSURE_VIOLATION,
    BROAD_OVERRIDE,
    CERTIFICATE_GATE,
    COMPLIANT_SUBOPTIMAL,
    ORACLE_CORRECT,
)


def _paired(outcomes: pd.DataFrame, metric: str) -> pd.DataFrame:
    return outcomes.pivot(
        index=["model", "task_id", "scenario", "proposal_state"],
        columns="institution",
        values=metric,
    ).reset_index()


def _break_even(correct_effect: float, violation_effect: float) -> float:
    """Failure prevalence where the expected gate-minus-broad effect is zero."""
    if correct_effect <= 0:
        return 0.0
    if violation_effect >= 0:
        return 1.0
    return correct_effect / (correct_effect - violation_effect)


def prevalence_tradeoffs(
    outcomes: pd.DataFrame,
    *,
    metric: str = "constraint_followed",
    bootstrap_repetitions: int = 10_000,
    bootstrap_seed: int = 202_609_08,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estimate conditional effects and implied upstream-failure thresholds."""
    paired = _paired(outcomes, metric)
    paired["difference"] = paired[CERTIFICATE_GATE].astype(float) - paired[
        BROAD_OVERRIDE
    ].astype(float)
    rng = np.random.default_rng(bootstrap_seed)
    summaries = []
    curves = []
    model_scopes: list[tuple[str, pd.DataFrame]] = [
        (str(model), group) for model, group in paired.groupby("model")
    ]
    model_scopes.append(("pooled_models", paired))
    for scope, scoped in model_scopes:
        correct = scoped[scoped["proposal_state"] == ORACLE_CORRECT]
        violation = scoped[scoped["proposal_state"] == AGGREGATE_PRESSURE_VIOLATION]
        correct_effect = float(correct["difference"].mean())
        violation_effect = float(violation["difference"].mean())
        threshold = _break_even(correct_effect, violation_effect)
        by_task = (
            scoped.groupby(["task_id", "proposal_state"])["difference"].mean().unstack()
        )
        task_ids = list(by_task.index)
        sampled_indices = rng.integers(
            0,
            len(task_ids),
            size=(bootstrap_repetitions, len(task_ids)),
        )
        correct_boot = by_task[ORACLE_CORRECT].to_numpy()[sampled_indices].mean(axis=1)
        violation_boot = (
            by_task[AGGREGATE_PRESSURE_VIOLATION]
            .to_numpy()[sampled_indices]
            .mean(axis=1)
        )
        boot_thresholds = np.array(
            [
                _break_even(float(correct_value), float(violation_value))
                for correct_value, violation_value in zip(
                    correct_boot, violation_boot, strict=True
                )
            ]
        )
        summaries.append(
            {
                "scope": scope,
                "metric": metric,
                "n_tasks": len(task_ids),
                "n_model_task_pairs": scoped[["model", "task_id"]]
                .drop_duplicates()
                .shape[0],
                "correct_proposal_effect": correct_effect,
                "violation_proposal_effect": violation_effect,
                "broad_corruptions_prevented": int((correct["difference"] == 1).sum()),
                "broad_repairs_blocked": int((violation["difference"] == -1).sum()),
                "break_even_violation_prevalence": threshold,
                "break_even_ci_low": float(np.quantile(boot_thresholds, 0.025)),
                "break_even_ci_high": float(np.quantile(boot_thresholds, 0.975)),
            }
        )
        for prevalence in np.linspace(0.0, 1.0, 101):
            curves.append(
                {
                    "scope": scope,
                    "metric": metric,
                    "violation_prevalence": prevalence,
                    "expected_gate_minus_broad": (
                        (1.0 - prevalence) * correct_effect
                        + prevalence * violation_effect
                    ),
                }
            )
    return pd.DataFrame(summaries), pd.DataFrame(curves)


def scenario_effects(
    outcomes: pd.DataFrame,
    *,
    metric: str = "constraint_followed",
) -> pd.DataFrame:
    """Report descriptive model-by-scenario conditional effects."""
    paired = _paired(outcomes, metric)
    paired["difference"] = paired[CERTIFICATE_GATE].astype(float) - paired[
        BROAD_OVERRIDE
    ].astype(float)
    return (
        paired.groupby(["model", "scenario", "proposal_state"], as_index=False)
        .agg(
            n=("task_id", "size"),
            broad_rate=(BROAD_OVERRIDE, "mean"),
            certificate_gate_rate=(CERTIFICATE_GATE, "mean"),
            effect=("difference", "mean"),
        )
        .sort_values(["model", "scenario", "proposal_state"])
    )


def multi_state_tradeoffs(
    outcomes: pd.DataFrame,
    *,
    metric: str = "protected_oracle_match",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Summarize jurisdiction effects and their three-state prevalence region.

    The simplex grid is descriptive: proposal-state prevalences are not estimated
    by the fault-injection experiment. It makes the base-rate dependence explicit
    rather than averaging over the experiment's artificial balanced mixture.
    """
    paired = _paired(outcomes, metric)
    paired["difference"] = paired[CERTIFICATE_GATE].astype(float) - paired[
        BROAD_OVERRIDE
    ].astype(float)
    scopes: list[tuple[str, pd.DataFrame]] = [
        (str(model), group) for model, group in paired.groupby("model")
    ]
    scopes.append(("pooled_models", paired))
    summaries = []
    grid = []
    states = (ORACLE_CORRECT, AGGREGATE_PRESSURE_VIOLATION, COMPLIANT_SUBOPTIMAL)
    for scope, scoped in scopes:
        effects = {
            state: float(
                scoped.loc[scoped["proposal_state"] == state, "difference"].mean()
            )
            for state in states
        }
        correct_effect = effects[ORACLE_CORRECT]
        suboptimal_effect = effects[COMPLIANT_SUBOPTIMAL]
        if correct_effect > 0 and suboptimal_effect < 0:
            minimum_correct_share = -suboptimal_effect / (
                correct_effect - suboptimal_effect
            )
        elif correct_effect > 0 and suboptimal_effect >= 0:
            minimum_correct_share = 0.0
        else:
            minimum_correct_share = float("nan")
        summaries.append(
            {
                "scope": scope,
                "metric": metric,
                "n_model_task_pairs": scoped[["model", "task_id"]]
                .drop_duplicates()
                .shape[0],
                **{f"{state}_effect": effects[state] for state in states},
                "minimum_correct_share_among_nonviolations": minimum_correct_share,
            }
        )
        for correct_pct in range(101):
            for violation_pct in range(101 - correct_pct):
                suboptimal_pct = 100 - correct_pct - violation_pct
                expected = (
                    correct_pct * effects[ORACLE_CORRECT]
                    + violation_pct * effects[AGGREGATE_PRESSURE_VIOLATION]
                    + suboptimal_pct * effects[COMPLIANT_SUBOPTIMAL]
                ) / 100.0
                grid.append(
                    {
                        "scope": scope,
                        "metric": metric,
                        "correct_prevalence": correct_pct / 100.0,
                        "violation_prevalence": violation_pct / 100.0,
                        "compliant_suboptimal_prevalence": suboptimal_pct / 100.0,
                        "expected_gate_minus_broad": expected,
                        "gate_preferred": expected > 0,
                    }
                )
    return pd.DataFrame(summaries), pd.DataFrame(grid)


def audit_schema_effects(
    protected_only: pd.DataFrame,
    dual_objective: pd.DataFrame,
) -> pd.DataFrame:
    """Paired dual-minus-protected audit-schema effects on reviewer outcomes."""
    keys = ["model", "task_id", "scenario", "proposal_state", "institution"]
    metrics = ("protected_oracle_match", "constraint_followed")
    left = protected_only[keys + list(metrics)].copy()
    right = dual_objective[keys + list(metrics)].copy()
    merged = left.merge(
        right,
        on=keys,
        how="inner",
        validate="one_to_one",
        suffixes=("_protected_only", "_dual_objective"),
    )
    expected = len(left)
    if len(merged) != expected or len(right) != expected:
        raise ValueError("audit-schema inputs do not contain the same paired rows")
    rows = []
    scopes: list[tuple[str, pd.DataFrame]] = [
        (str(model), group) for model, group in merged.groupby("model")
    ]
    scopes.append(("pooled_models", merged))
    for scope, scope_rows in scopes:
        for institution in (BROAD_OVERRIDE, CERTIFICATE_GATE):
            institution_rows = scope_rows[scope_rows["institution"] == institution]
            for proposal_state in (
                "all",
                *institution_rows["proposal_state"].unique(),
            ):
                scoped = (
                    institution_rows
                    if proposal_state == "all"
                    else institution_rows[
                        institution_rows["proposal_state"] == proposal_state
                    ]
                )
                for metric in metrics:
                    protected_col = f"{metric}_protected_only"
                    dual_col = f"{metric}_dual_objective"
                    rows.append(
                        {
                            "scope": scope,
                            "institution": institution,
                            "proposal_state": proposal_state,
                            "metric": metric,
                            "n": len(scoped),
                            "protected_only_rate": scoped[protected_col].mean(),
                            "dual_objective_rate": scoped[dual_col].mean(),
                            "dual_minus_protected": (
                                scoped[dual_col].astype(float)
                                - scoped[protected_col].astype(float)
                            ).mean(),
                        }
                    )
    return pd.DataFrame(rows)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", type=Path, nargs="+", required=True)
    parser.add_argument("--dual-outcomes", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    outcomes = pd.concat(
        [pd.read_csv(path) for path in args.outcomes],
        ignore_index=True,
    )
    tradeoffs, curve = prevalence_tradeoffs(outcomes)
    scenarios = scenario_effects(outcomes)
    multi_summary = pd.DataFrame()
    multi_grid = pd.DataFrame()
    if COMPLIANT_SUBOPTIMAL in set(outcomes["proposal_state"]):
        multi_summary, multi_grid = multi_state_tradeoffs(outcomes)
    args.output.mkdir(parents=True, exist_ok=True)
    tradeoffs.to_csv(args.output / "prevalence_tradeoffs.csv", index=False)
    curve.to_csv(args.output / "prevalence_curve.csv", index=False)
    scenarios.to_csv(args.output / "scenario_effects.csv", index=False)
    if not multi_summary.empty:
        multi_summary.to_csv(args.output / "multi_state_tradeoffs.csv", index=False)
        multi_grid.to_csv(args.output / "multi_state_prevalence_grid.csv", index=False)
    if args.dual_outcomes:
        dual = pd.concat(
            [pd.read_csv(path) for path in args.dual_outcomes], ignore_index=True
        )
        audit_schema_effects(outcomes, dual).to_csv(
            args.output / "audit_schema_effects.csv", index=False
        )
    print(
        f"Wrote {len(tradeoffs)} tradeoff rows, {len(curve)} curve points, "
        f"and {len(scenarios)} scenario rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
