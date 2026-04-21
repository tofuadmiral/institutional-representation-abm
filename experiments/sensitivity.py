"""Morris screening + Sobol variance decomposition over institution configs.

The 6 parameters that move output metrics most are identified by Morris first
(cheap: ~140 design points). Sobol then confirms with proper variance
decomposition (2048 design points per institution at N=256). Baseline scenario
only -- sweeping scenarios would multiply cost without adding signal.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from SALib.analyze import morris as morris_analyze
from SALib.analyze import sobol as sobol_analyze
from SALib.sample.morris import sample as morris_sample
from SALib.sample.sobol import sample as sobol_sample

from bills.bill import Bill
from config import ParliamentaryConfig, RepublicanConfig
from experiments.scenarios import BASELINE, ComparisonScenario, SCENARIOS_BY_NAME
from institutions.parliamentary import ParliamentaryModel
from institutions.republican import RepublicanModel

INSTITUTION_PROBLEMS: Dict[str, Dict[str, Any]] = {
    "parliamentary": {
        "num_vars": 6,
        "names": [
            "discipline_strength",
            "confidence_threshold",
            "committee_gatekeeping_power",
            "opposition_discipline_multiplier",
            "num_parties",
            "num_constituencies",
        ],
        "bounds": [
            [0.0, 1.0],
            [0.4, 0.7],
            [0.0, 1.0],
            [0.3, 1.0],
            [2, 6],
            [3, 10],
        ],
    },
    "republican": {
        "num_vars": 6,
        "names": [
            "discipline_strength",
            "executive_opposition_rate",
            "max_veto_probability",
            "committee_gatekeeping_power",
            "num_parties",
            "num_constituencies",
        ],
        "bounds": [
            [0.0, 1.0],
            [0.0, 1.0],
            [0.0, 1.0],
            [0.0, 1.0],
            [2, 6],
            [3, 10],
        ],
    },
}

INTEGER_PARAMS = {"num_parties", "num_constituencies"}


def _apply_params(
    institution: str,
    scenario: ComparisonScenario,
    sample: Sequence[float],
) -> Tuple[Any, ComparisonScenario]:
    """Map a SALib sample vector to (config, scenario) overrides."""
    problem = INSTITUTION_PROBLEMS[institution]
    raw = dict(zip(problem["names"], sample))

    scenario_overrides: Dict[str, Any] = {}
    if "num_parties" in raw:
        scenario_overrides["num_parties"] = int(round(raw.pop("num_parties")))
    if "num_constituencies" in raw:
        scenario_overrides["num_constituencies"] = int(round(raw.pop("num_constituencies")))

    modified_scenario = dataclasses.replace(scenario, **scenario_overrides)

    if institution == "parliamentary":
        modified_config = dataclasses.replace(ParliamentaryConfig(), **raw)
    elif institution == "republican":
        modified_config = dataclasses.replace(RepublicanConfig(), **raw)
    else:
        raise ValueError(f"Unknown institution: {institution}")

    return modified_config, modified_scenario


def _simulate_one_sample(
    institution: str,
    config: Any,
    scenario: ComparisonScenario,
    seed: int,
) -> float:
    if institution == "parliamentary":
        model = ParliamentaryModel(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=config,
            seed=seed,
        )
    else:
        model = RepublicanModel(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=config,
            seed=seed,
        )

    low, high = scenario.bill_ideology_range
    bills_passed = 0
    for i in range(scenario.num_bills):
        bill = Bill(
            bill_id=i,
            ideology=(model.random.uniform(low, high), model.random.uniform(low, high)),
            salience=model.random.uniform(0.3, 1.0),
        )
        if model.pass_legislation(bill):
            bills_passed += 1
    return bills_passed / max(scenario.num_bills, 1)


def _design_point(
    institution: str,
    scenario: ComparisonScenario,
    sample: Sequence[float],
    sample_idx: int,
    seeds: Sequence[int],
) -> Dict[str, Any]:
    """One design point averaged over `seeds` replications."""
    config, modified_scenario = _apply_params(institution, scenario, sample)
    passage_rates = [
        _simulate_one_sample(institution, config, modified_scenario, s) for s in seeds
    ]
    row: Dict[str, Any] = {
        "institution": institution,
        "scenario": scenario.name,
        "sample_idx": sample_idx,
        "passage_rate": float(np.mean(passage_rates)),
        "passage_rate_std": float(np.std(passage_rates)),
        "n_seeds": len(seeds),
    }
    for name, val in zip(INSTITUTION_PROBLEMS[institution]["names"], sample):
        row[name] = float(val)
    return row


def _dispatch_samples(
    institution: str,
    scenario: ComparisonScenario,
    samples: np.ndarray,
    base_seed: int,
    seeds_per_sample: int,
    seed_offset: int,
    n_jobs: int,
    verbose: int,
) -> pd.DataFrame:
    jobs = [
        (
            institution,
            scenario,
            samples[i],
            i,
            [base_seed + seed_offset + i * seeds_per_sample + k for k in range(seeds_per_sample)],
        )
        for i in range(len(samples))
    ]
    results = Parallel(n_jobs=n_jobs, backend="loky", verbose=verbose)(
        delayed(_design_point)(*job) for job in jobs
    )
    return pd.DataFrame(results)


def run_morris(
    institution: str,
    scenario: ComparisonScenario = BASELINE,
    n_trajectories: int = 20,
    num_levels: int = 4,
    seeds_per_sample: int = 3,
    base_seed: int = 0,
    n_jobs: int = -1,
    verbose: int = 0,
) -> pd.DataFrame:
    problem = INSTITUTION_PROBLEMS[institution]
    samples = morris_sample(problem, N=n_trajectories, num_levels=num_levels, seed=base_seed)
    return _dispatch_samples(
        institution, scenario, samples,
        base_seed, seeds_per_sample, seed_offset=1000,
        n_jobs=n_jobs, verbose=verbose,
    )


def analyze_morris(df: pd.DataFrame, institution: str, num_levels: int = 4) -> pd.DataFrame:
    problem = INSTITUTION_PROBLEMS[institution]
    df_sorted = df.sort_values("sample_idx")
    X = df_sorted[problem["names"]].to_numpy()
    Y = df_sorted["passage_rate"].to_numpy()
    Si = morris_analyze.analyze(problem, X, Y, num_levels=num_levels)
    out = pd.DataFrame({
        "parameter": problem["names"],
        "mu": Si["mu"],
        "mu_star": Si["mu_star"],
        "sigma": Si["sigma"],
        "mu_star_conf": Si["mu_star_conf"],
    })
    out["institution"] = institution
    return out


def run_sobol(
    institution: str,
    scenario: ComparisonScenario = BASELINE,
    n_samples: int = 256,
    calc_second_order: bool = False,
    seeds_per_sample: int = 3,
    base_seed: int = 0,
    n_jobs: int = -1,
    verbose: int = 0,
) -> pd.DataFrame:
    problem = INSTITUTION_PROBLEMS[institution]
    samples = sobol_sample(
        problem, N=n_samples, calc_second_order=calc_second_order, seed=base_seed,
    )
    return _dispatch_samples(
        institution, scenario, samples,
        base_seed, seeds_per_sample, seed_offset=10_000,
        n_jobs=n_jobs, verbose=verbose,
    )


def analyze_sobol(
    df: pd.DataFrame, institution: str, calc_second_order: bool = False,
) -> pd.DataFrame:
    problem = INSTITUTION_PROBLEMS[institution]
    df_sorted = df.sort_values("sample_idx")
    Y = df_sorted["passage_rate"].to_numpy()
    Si = sobol_analyze.analyze(problem, Y, calc_second_order=calc_second_order)
    out = pd.DataFrame({
        "parameter": problem["names"],
        "S1": Si["S1"],
        "S1_conf": Si["S1_conf"],
        "ST": Si["ST"],
        "ST_conf": Si["ST_conf"],
    })
    out["institution"] = institution
    return out


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Sensitivity analysis via Morris + Sobol.")
    parser.add_argument("--institutions", nargs="+", default=["parliamentary", "republican"])
    parser.add_argument("--scenario", default="baseline", choices=list(SCENARIOS_BY_NAME))
    parser.add_argument("--morris-trajectories", type=int, default=20)
    parser.add_argument(
        "--sobol-samples", type=int, default=256,
        help="Sobol base N (ideally a power of 2).",
    )
    parser.add_argument("--seeds-per-sample", type=int, default=3)
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--jobs", type=int, default=-1)
    parser.add_argument("--output", type=Path, default=Path("results/phase_b/"))
    parser.add_argument("--skip-morris", action="store_true")
    parser.add_argument("--skip-sobol", action="store_true")
    parser.add_argument("--verbose", type=int, default=5)
    args = parser.parse_args(argv)

    args.output.mkdir(parents=True, exist_ok=True)
    scenario = SCENARIOS_BY_NAME[args.scenario]

    morris_long: List[pd.DataFrame] = []
    morris_results: List[pd.DataFrame] = []
    sobol_long: List[pd.DataFrame] = []
    sobol_results: List[pd.DataFrame] = []

    for inst in args.institutions:
        if not args.skip_morris:
            print(f"Running Morris: {inst} x {scenario.name}", flush=True)
            df = run_morris(
                inst, scenario,
                n_trajectories=args.morris_trajectories,
                seeds_per_sample=args.seeds_per_sample,
                base_seed=args.base_seed,
                n_jobs=args.jobs,
                verbose=args.verbose,
            )
            morris_long.append(df)
            morris_results.append(analyze_morris(df, inst))
        if not args.skip_sobol:
            print(f"Running Sobol: {inst} x {scenario.name}", flush=True)
            df = run_sobol(
                inst, scenario,
                n_samples=args.sobol_samples,
                seeds_per_sample=args.seeds_per_sample,
                base_seed=args.base_seed,
                n_jobs=args.jobs,
                verbose=args.verbose,
            )
            sobol_long.append(df)
            sobol_results.append(analyze_sobol(df, inst))

    if morris_long:
        pd.concat(morris_long, ignore_index=True).to_csv(
            args.output / "morris_long.csv", index=False,
        )
        pd.concat(morris_results, ignore_index=True).to_csv(
            args.output / "morris_results.csv", index=False,
        )
        print(f"Wrote Morris results to {args.output}")
    if sobol_long:
        pd.concat(sobol_long, ignore_index=True).to_csv(
            args.output / "sobol_long.csv", index=False,
        )
        pd.concat(sobol_results, ignore_index=True).to_csv(
            args.output / "sobol_results.csv", index=False,
        )
        print(f"Wrote Sobol results to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
