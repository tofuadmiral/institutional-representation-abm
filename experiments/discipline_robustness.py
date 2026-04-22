"""Discipline-default robustness check.

The Phase B/C headline finding is that the `no_discipline` rescue magnitude
falls monotonically across four institutions in the same order as the
institutions' default `discipline_strength` (parl 0.8 > premier-pres 0.6 ==
president-parl 0.6 > rep 0.4). Because the ordering matches the defaults, the
monotone rescue pattern could be an artefact of the parameter choices rather
than a structural claim about institutional design.

This experiment varies the common discipline level D across a grid, setting
all four institutions' `discipline_strength=D`, and measures the rescue
magnitude:

    rescue(D, institution) = passage_rate(discipline=0) - passage_rate(discipline=D)

If the rescue ordering parl > premier-pres > president-parl > rep holds for
*most* values of D, the pattern is structural. If it flips or collapses for
off-default D values, the pattern was an artefact.
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
    ParliamentaryConfig,
    RepublicanConfig,
    premier_presidential_config,
    president_parliamentary_config,
)
from experiments.parameter_sweep import _simulate_with_config
from experiments.scenarios import (
    BASELINE,
    FRAGMENTED,
    ComparisonScenario,
    SCENARIOS_BY_NAME,
)

INSTITUTIONS = (
    "parliamentary", "republican", "premier_presidential", "president_parliamentary",
)

# Expected rescue ordering under fragmentation, by decreasing majority-dependence
# of the government-formation rule. This is the claim Phase F is designed to test.
MAJORITY_DEPENDENCE_ORDER = (
    "parliamentary",          # strict majority required, no alternative
    "premier_presidential",   # majority-driven, but president adds veto stage
    "president_parliamentary",# president can appoint minority cabinet
    "republican",             # no formation gate at all
)


def _config_with_discipline(institution: str, discipline: float):
    if institution == "parliamentary":
        return dataclasses.replace(ParliamentaryConfig(), discipline_strength=discipline)
    if institution == "republican":
        return dataclasses.replace(RepublicanConfig(), discipline_strength=discipline)
    if institution == "premier_presidential":
        return dataclasses.replace(premier_presidential_config(), discipline_strength=discipline)
    if institution == "president_parliamentary":
        return dataclasses.replace(president_parliamentary_config(), discipline_strength=discipline)
    raise ValueError(f"Unknown institution: {institution}")


def run_discipline_grid(
    discipline_values: Sequence[float],
    scenarios: Iterable[ComparisonScenario] = (BASELINE, FRAGMENTED),
    institutions: Sequence[str] = INSTITUTIONS,
    n_seeds: int = 100,
    base_seed: int = 0,
    n_jobs: int = -1,
) -> pd.DataFrame:
    """For each (D, institution, scenario), run N seeds. Returns long-form df."""
    jobs: List = []
    scenario_list = list(scenarios)
    for inst in institutions:
        for D in discipline_values:
            cfg = _config_with_discipline(inst, D)
            for scenario in scenario_list:
                for i in range(n_seeds):
                    jobs.append((inst, scenario, cfg, base_seed + i, D))

    def _task(inst, scenario, cfg, seed, D):
        row = _simulate_with_config(inst, scenario, cfg, seed)
        row["discipline_strength"] = D
        return row

    results = Parallel(n_jobs=n_jobs, backend="loky", verbose=0)(
        delayed(_task)(*j) for j in jobs
    )
    return pd.DataFrame(results)


def compute_rescue_deltas(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot on discipline_strength; compute rescue(D) = passage@0 - passage@D.

    Requires discipline=0.0 to be in the grid.
    """
    grouped = (
        df.groupby(["institution", "scenario", "discipline_strength"])["passage_rate"]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    # Extract the discipline=0 row per (institution, scenario) as a lookup
    baseline = (
        grouped[grouped["discipline_strength"] == 0.0]
        .set_index(["institution", "scenario"])["mean"]
        .to_dict()
    )
    if not baseline:
        raise ValueError("discipline_strength=0.0 must be in the grid to compute rescue")

    def _rescue(row):
        key = (row["institution"], row["scenario"])
        return float(baseline.get(key, float("nan")) - row["mean"])

    grouped["rescue_vs_zero"] = grouped.apply(_rescue, axis=1)
    return grouped


def check_monotone_ordering(
    rescue_df: pd.DataFrame,
    scenario: str,
    expected_order: Sequence[str] = MAJORITY_DEPENDENCE_ORDER,
) -> pd.DataFrame:
    """For each D > 0, check whether rescue values are ordered as expected.

    Returns a frame with one row per D giving the actual rescue ordering and
    whether it matches the expected order.
    """
    sub = rescue_df[
        (rescue_df["scenario"] == scenario) & (rescue_df["discipline_strength"] > 0)
    ]
    rows = []
    for D, g in sub.groupby("discipline_strength"):
        ordered = g.sort_values("rescue_vs_zero", ascending=False)
        actual_order = tuple(ordered["institution"].tolist())
        rescues = {r["institution"]: float(r["rescue_vs_zero"]) for _, r in ordered.iterrows()}
        monotone_expected = all(
            rescues[expected_order[i]] >= rescues[expected_order[i + 1]]
            for i in range(len(expected_order) - 1)
        )
        rows.append({
            "scenario": scenario,
            "discipline_strength": D,
            "actual_order_best_to_worst": actual_order,
            "matches_expected_order": monotone_expected,
            **{f"rescue_{inst}": rescues[inst] for inst in expected_order},
        })
    return pd.DataFrame(rows)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Discipline-default robustness check"
    )
    parser.add_argument(
        "--discipline-values",
        nargs="+", type=float,
        default=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
    )
    parser.add_argument("--scenarios", nargs="+", default=["baseline", "fragmented"])
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--jobs", type=int, default=-1)
    parser.add_argument("--output", type=Path, default=Path("results/phase_f/"))
    args = parser.parse_args(argv)

    args.output.mkdir(parents=True, exist_ok=True)
    scenarios = [SCENARIOS_BY_NAME[n] for n in args.scenarios]

    print(
        f"Running {len(INSTITUTIONS)} institutions × {len(scenarios)} scenarios × "
        f"{len(args.discipline_values)} D values × {args.seeds} seeds = "
        f"{len(INSTITUTIONS) * len(scenarios) * len(args.discipline_values) * args.seeds} simulations",
        flush=True,
    )
    df = run_discipline_grid(
        discipline_values=args.discipline_values,
        scenarios=scenarios,
        n_seeds=args.seeds,
        base_seed=args.base_seed,
        n_jobs=args.jobs,
    )
    long_path = args.output / "discipline_grid_long.csv"
    df.to_csv(long_path, index=False)
    print(f"Wrote {len(df)} rows to {long_path}")

    deltas = compute_rescue_deltas(df)
    deltas_path = args.output / "discipline_rescue_deltas.csv"
    deltas.to_csv(deltas_path, index=False)
    print(f"Wrote {len(deltas)} rows to {deltas_path}")

    for scenario_name in args.scenarios:
        orderings = check_monotone_ordering(deltas, scenario_name)
        order_path = args.output / f"discipline_ordering_{scenario_name}.csv"
        orderings.to_csv(order_path, index=False)
        print(f"Wrote {len(orderings)} rows to {order_path}")

    return 0


if __name__ == "__main__":
    sys.exit(_main())
