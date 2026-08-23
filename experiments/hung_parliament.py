"""Hung-parliament behaviour comparison: cohesive obstruction vs personal vote.

Motivation (Phase H review): under fragmentation no coalition can form for
the majority-driven institutions, so `government_coalition` is empty. The
original code applied the opposition-whip branch to *every* MP in that case,
which produces near-zero passage. That behaviour was an undocumented edge
case, not a finding about coalition formation per se.

This experiment makes the edge case a measured variant via
`hung_parliament_behavior`:

    cohesive_obstruction  — every MP counts as "opposition" and is whipped
        against bills (anti-system blocs, Weimar-style polarised obstruction)
    personal_vote         — with no whip in play every MP reverts to their own
        preference (issue-by-issue majorities; Strøm-style minority governance)

The decomposition separates two mechanisms that observational studies cannot:
government-formation failure (both variants share it) and cohesive opposition
obstruction (only the first variant has it). If passage collapses only under
cohesive_obstruction, formation failure alone does not halt legislation.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd
from joblib import Parallel, delayed

from config import (
    HUNG_COHESIVE_OBSTRUCTION,
    HUNG_PERSONAL_VOTE,
    ParliamentaryConfig,
    RepublicanConfig,
    premier_presidential_config,
    president_parliamentary_config,
)
from experiments.multiseed_comparison import INSTITUTION_NAMES, _build_model, _generate_bills
from experiments.scenarios import DEFAULT_SCENARIOS, ComparisonScenario

INSTITUTIONS = INSTITUTION_NAMES

# Institutions whose government formation can fail outright (empty coalition).
MAJORITY_DRIVEN_INSTITUTIONS = ("parliamentary", "premier_presidential")

VARIANTS = (HUNG_COHESIVE_OBSTRUCTION, HUNG_PERSONAL_VOTE)


def _config_with_variant(institution: str, variant: str):
    if institution == "parliamentary":
        return dataclasses.replace(ParliamentaryConfig(), hung_parliament_behavior=variant)
    if institution == "republican":
        # No formation gate: the flag cannot bind. Included as a reference row.
        return RepublicanConfig()
    if institution == "premier_presidential":
        return dataclasses.replace(
            premier_presidential_config(), hung_parliament_behavior=variant,
        )
    if institution == "president_parliamentary":
        # President-driven formation always appoints at least a minority
        # cabinet, so the flag cannot bind here either.
        return president_parliamentary_config()
    raise ValueError(f"Unknown institution: {institution}")


def _simulate_variant(institution: str, scenario: ComparisonScenario, config, seed: int):
    """Replicate the `_simulate_one` flow (bills drawn up-front) so results are
    directly comparable with the paper's main tables."""
    model = _build_model(institution, scenario, seed)
    # Swap in the variant config without re-drawing agents.
    model.config = config
    bills = _generate_bills(model, scenario)
    bills_passed = sum(1 for b in bills if model.pass_legislation(b))
    return {
        "institution": institution,
        "scenario": scenario.name,
        "seed": seed,
        "bills_processed": len(bills),
        "passage_rate": bills_passed / max(len(bills), 1),
    }


def run_hung_parliament_comparison(
    scenarios: Iterable[ComparisonScenario] = DEFAULT_SCENARIOS,
    institutions: Sequence[str] = INSTITUTIONS,
    variants: Sequence[str] = VARIANTS,
    n_seeds: int = 200,
    base_seed: int = 0,
    n_jobs: int = -1,
) -> pd.DataFrame:
    """Run N seeds per (scenario, institution, variant). Long-form DataFrame."""
    jobs: List = []
    for scenario in scenarios:
        for inst in institutions:
            for variant in variants:
                cfg = _config_with_variant(inst, variant)
                for i in range(n_seeds):
                    jobs.append((inst, scenario, cfg, base_seed + i, variant))

    def _task(inst, scenario, cfg, seed, variant):
        row = _simulate_variant(inst, scenario, cfg, seed)
        row["hung_parliament_behavior"] = variant
        return row

    results = Parallel(n_jobs=n_jobs, backend="loky", verbose=0)(
        delayed(_task)(*j) for j in jobs
    )
    return pd.DataFrame(results)


def summarize_variants(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse to mean/std/count per (scenario, institution, variant), plus
    the personal-vote minus obstruction delta."""
    grouped = (
        df.groupby(["scenario", "institution", "hung_parliament_behavior"])["passage_rate"]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    means = grouped.set_index(["scenario", "institution", "hung_parliament_behavior"])["mean"]

    def _delta(row) -> float:
        key = (row["scenario"], row["institution"])
        personal = means.get(key + (HUNG_PERSONAL_VOTE,), float("nan"))
        obstructed = means.get(key + (HUNG_COHESIVE_OBSTRUCTION,), float("nan"))
        return float(personal - obstructed)

    grouped["delta_personal_minus_obstruction"] = grouped.apply(_delta, axis=1)
    return grouped


def plot_hung_parliament_bars(summary: pd.DataFrame, out_path: Path) -> Path:
    """Grouped bars of mean passage rate by institution and variant, one panel
    per scenario. Highlights where the flag can and cannot bind."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scenarios = list(dict.fromkeys(summary["scenario"]))
    institutions = [i for i in INSTITUTIONS if i in set(summary["institution"])]
    colors = {HUNG_COHESIVE_OBSTRUCTION: "#D04A3A", HUNG_PERSONAL_VOTE: "#1F4E79"}
    labels = {
        HUNG_COHESIVE_OBSTRUCTION: "cohesive obstruction",
        HUNG_PERSONAL_VOTE: "personal vote",
    }

    fig, axes = plt.subplots(1, len(scenarios), figsize=(4.2 * len(scenarios), 3.6),
                             sharey=True)
    if len(scenarios) == 1:
        axes = [axes]

    for ax, scen in zip(axes, scenarios):
        sub = summary[summary["scenario"] == scen]
        width = 0.38
        xs = range(len(institutions))
        for k, variant in enumerate(VARIANTS):
            vals = [
                float(sub[(sub["institution"] == i)
                          & (sub["hung_parliament_behavior"] == variant)]["mean"].iloc[0])
                if len(sub[(sub["institution"] == i)
                           & (sub["hung_parliament_behavior"] == variant)]) else 0.0
                for i in institutions
            ]
            ax.bar([x + (k - 0.5) * width for x in xs], vals, width=width,
                   label=labels[variant], color=colors[variant])
        ax.set_title(scen.replace("_", " "))
        ax.set_xticks(list(xs))
        ax.set_xticklabels([i.replace("_", "\n") for i in institutions], fontsize=8)
        ax.set_ylim(0, 1)
        ax.spines[["top", "right"]].set_visible(False)

    axes[0].set_ylabel("Mean passage rate")
    axes[-1].legend(loc="upper right", fontsize=9, frameon=False)
    fig.suptitle("Hung-parliament behaviour: formation failure vs cohesive obstruction",
                 fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Hung-parliament behaviour comparison")
    parser.add_argument("--scenarios", nargs="+", default=["all"])
    parser.add_argument("--seeds", type=int, default=200)
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--jobs", type=int, default=-1)
    parser.add_argument("--output", type=Path, default=Path("results/phase_h/"))
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args(argv)

    args.output.mkdir(parents=True, exist_ok=True)
    if "all" in args.scenarios:
        scenarios = list(DEFAULT_SCENARIOS)
    else:
        from experiments.scenarios import SCENARIOS_BY_NAME
        scenarios = [SCENARIOS_BY_NAME[n] for n in args.scenarios]

    print(
        f"Running {len(scenarios)} scenarios × {len(INSTITUTIONS)} institutions × "
        f"{len(VARIANTS)} variants × {args.seeds} seeds = "
        f"{len(scenarios) * len(INSTITUTIONS) * len(VARIANTS) * args.seeds} simulations",
        flush=True,
    )

    df = run_hung_parliament_comparison(
        scenarios=scenarios,
        n_seeds=args.seeds,
        base_seed=args.base_seed,
        n_jobs=args.jobs,
    )
    long_path = args.output / "hung_parliament_long.csv"
    df.to_csv(long_path, index=False)
    print(f"Wrote {len(df)} rows to {long_path}")

    summary = summarize_variants(df)
    summary_path = args.output / "hung_parliament_summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Wrote {len(summary)} rows to {summary_path}")

    if not args.no_plots:
        fig_path = plot_hung_parliament_bars(summary, Path("docs/figures/hung_parliament_comparison.png"))
        print(f"Wrote figure {fig_path}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
