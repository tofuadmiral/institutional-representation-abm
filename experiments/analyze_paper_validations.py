"""Cross-model analysis for natural proposals and portfolio transfer validation."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from experiments.analyze_certificate_replications import (
    multi_state_tradeoffs,
    scenario_effects,
)
from experiments.prospective_certificate_gate import (
    BROAD_OVERRIDE,
    CERTIFICATE_GATE,
    _protected_losses,
    collect_multi_eligible_conflict_tasks,
    paired_certificate_effects,
)


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple:
    """Return a two-sided Wilson interval for a binomial proportion."""
    if n < 1:
        return float("nan"), float("nan")
    proportion = successes / n
    denominator = 1 + z**2 / n
    center = (proportion + z**2 / (2 * n)) / denominator
    half_width = (
        z
        * math.sqrt(proportion * (1 - proportion) / n + z**2 / (4 * n**2))
        / denominator
    )
    return center - half_width, center + half_width


def natural_state_summary(proposers: pd.DataFrame) -> pd.DataFrame:
    """Report observed benchmark-conditional proposal-state frequencies."""
    rows = []
    scopes = [(str(model), group) for model, group in proposers.groupby("model")]
    scopes.append(("pooled_models", proposers))
    for scope, scoped in scopes:
        for scenario in ("all", *sorted(scoped["scenario"].unique())):
            selected = (
                scoped if scenario == "all" else scoped[scoped["scenario"] == scenario]
            )
            for state in sorted(scoped["proposal_state"].unique()):
                successes = int((selected["proposal_state"] == state).sum())
                low, high = wilson_interval(successes, len(selected))
                rows.append(
                    {
                        "scope": scope,
                        "scenario": scenario,
                        "proposal_state": state,
                        "n": len(selected),
                        "count": successes,
                        "rate": successes / len(selected),
                        "ci_low": low,
                        "ci_high": high,
                    }
                )
    return pd.DataFrame(rows)


def natural_review_transitions(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Count improvements and harms relative to each natural proposal."""
    keys = ["model", "task_id", "scenario", "proposal_state"]
    wide = outcomes.pivot(
        index=keys,
        columns="institution",
        values=["protected_oracle_match", "constraint_followed"],
    ).reset_index()
    rows = []
    scopes = [(str(model), group) for model, group in wide.groupby(("model", ""))]
    scopes.append(("pooled_models", wide))
    for scope, scoped in scopes:
        for institution in (BROAD_OVERRIDE, CERTIFICATE_GATE):
            for metric in ("protected_oracle_match", "constraint_followed"):
                before = scoped[(metric, "no_review")].astype(bool)
                after = scoped[(metric, institution)].astype(bool)
                rows.append(
                    {
                        "scope": scope,
                        "institution": institution,
                        "metric": metric,
                        "n": len(scoped),
                        "proposal_rate": before.mean(),
                        "reviewed_rate": after.mean(),
                        "net_effect": after.astype(float).mean()
                        - before.astype(float).mean(),
                        "errors_corrected": int((~before & after).sum()),
                        "successes_spoiled": int((before & ~after).sum()),
                    }
                )
    return pd.DataFrame(rows)


def protected_minimizer_diagnostic(proposers: pd.DataFrame) -> pd.DataFrame:
    """Test whether spatial-task errors minimize the protected loss instead."""
    tasks = {
        task.task_id: (task, principal_ids, mandate)
        for _, _, task, principal_ids, mandate, _ in collect_multi_eligible_conflict_tasks(
            tasks_per_scenario=32,
            base_seed=95_000,
            num_agents=7,
        )
    }
    rows = []
    for record in proposers.itertuples(index=False):
        task, principal_ids, mandate = tasks[record.task_id]
        losses = _protected_losses(task, mandate)
        minimum = min(losses.values())
        rows.append(
            {
                "model": record.model,
                "task_id": record.task_id,
                "proposal_state": record.proposal_state,
                "protected_loss_minimizer": math.isclose(
                    losses[record.proposal_choice],
                    minimum,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                ),
                "aggregate_oracle": record.protected_oracle_match,
            }
        )
    diagnostic = pd.DataFrame(rows)
    return (
        diagnostic.groupby(["model", "proposal_state"], as_index=False)
        .agg(
            n=("task_id", "size"),
            protected_loss_minimizer_count=("protected_loss_minimizer", "sum"),
            aggregate_oracle_count=("aggregate_oracle", "sum"),
        )
        .sort_values(["model", "proposal_state"])
    )


def model_specific_effects(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Run task-clustered paired effects separately for each fixed model."""
    rows = []
    for model, scoped in outcomes.groupby("model"):
        effects = paired_certificate_effects(scoped)
        effects.insert(0, "model", model)
        rows.append(effects)
    return pd.concat(rows, ignore_index=True)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--natural-proposers", type=Path, nargs="+", required=True)
    parser.add_argument("--natural-outcomes", type=Path, nargs="+", required=True)
    parser.add_argument("--portfolio-outcomes", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    proposers = pd.concat(
        [pd.read_csv(path) for path in args.natural_proposers], ignore_index=True
    )
    natural_outcomes = pd.concat(
        [pd.read_csv(path) for path in args.natural_outcomes], ignore_index=True
    )
    portfolio_outcomes = pd.concat(
        [pd.read_csv(path) for path in args.portfolio_outcomes], ignore_index=True
    )
    args.output.mkdir(parents=True, exist_ok=True)
    natural_state_summary(proposers).to_csv(
        args.output / "natural_state_frequencies.csv", index=False
    )
    natural_review_transitions(natural_outcomes).to_csv(
        args.output / "natural_review_transitions.csv", index=False
    )
    protected_minimizer_diagnostic(proposers).to_csv(
        args.output / "natural_protected_minimizer_diagnostic.csv", index=False
    )
    model_specific_effects(natural_outcomes).to_csv(
        args.output / "natural_gate_effects.csv", index=False
    )
    model_specific_effects(portfolio_outcomes).to_csv(
        args.output / "portfolio_gate_effects.csv", index=False
    )
    portfolio_tradeoffs, portfolio_grid = multi_state_tradeoffs(portfolio_outcomes)
    portfolio_tradeoffs.to_csv(
        args.output / "portfolio_multi_state_tradeoffs.csv", index=False
    )
    portfolio_grid.to_csv(args.output / "portfolio_prevalence_grid.csv", index=False)
    scenario_effects(portfolio_outcomes).to_csv(
        args.output / "portfolio_stratum_effects.csv", index=False
    )
    print(
        f"Analyzed {len(proposers)} natural proposals and "
        f"{len(portfolio_outcomes)} portfolio outcomes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
