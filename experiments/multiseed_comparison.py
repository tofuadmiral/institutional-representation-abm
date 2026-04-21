from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd
from joblib import Parallel, delayed

from agents.constituency import ConstituencyAgent
from agents.legislator import LegislatorAgent
from analysis.aggregate import pairwise_tests, summarize
from analysis.plots import render_all
from bills.bill import Bill
from config import ParliamentaryConfig, RepublicanConfig
from experiments.scenarios import (
    ComparisonScenario,
    DEFAULT_SCENARIOS,
    SCENARIOS_BY_NAME,
)
from institutions.parliamentary import ParliamentaryModel
from institutions.republican import RepublicanModel

INSTITUTION_NAMES = ("parliamentary", "republican")


def _build_model(institution: str, scenario: ComparisonScenario, seed: int):
    if institution == "parliamentary":
        return ParliamentaryModel(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=ParliamentaryConfig(),
            seed=seed,
        )
    if institution == "republican":
        return RepublicanModel(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=RepublicanConfig(),
            seed=seed,
        )
    raise ValueError(f"Unknown institution: {institution}")


def _generate_bills(model, scenario: ComparisonScenario) -> List[Bill]:
    low, high = scenario.bill_ideology_range
    bills: List[Bill] = []
    for i in range(scenario.num_bills):
        ideology = (model.random.uniform(low, high), model.random.uniform(low, high))
        bills.append(
            Bill(
                bill_id=i,
                ideology=ideology,
                salience=model.random.uniform(0.3, 1.0),
            )
        )
    return bills


def _representation_metrics(model) -> Dict[str, float]:
    legislators = [a for a in model.schedule.agents if isinstance(a, LegislatorAgent)]
    constituencies = {
        a.unique_id: a for a in model.schedule.agents if isinstance(a, ConstituencyAgent)
    }

    if not legislators or not constituencies:
        return {
            "avg_representation_distance": 0.0,
            "representation_inequality": 0.0,
            "perfect_representation_rate": 0.0,
        }

    distances: List[float] = []
    for legislator in legislators:
        if legislator.constituency_id in constituencies:
            constituency = constituencies[legislator.constituency_id]
            dist = (
                (legislator.ideology[0] - constituency.ideology[0]) ** 2
                + (legislator.ideology[1] - constituency.ideology[1]) ** 2
            ) ** 0.5
            distances.append(dist)

    if not distances:
        return {
            "avg_representation_distance": 0.0,
            "representation_inequality": 0.0,
            "perfect_representation_rate": 0.0,
        }

    avg_distance = sum(distances) / len(distances)
    variance = (
        sum((d - avg_distance) ** 2 for d in distances) / len(distances)
        if len(distances) > 1
        else 0.0
    )
    perfect_rate = sum(1 for d in distances if d < 0.2) / len(distances)

    return {
        "avg_representation_distance": avg_distance,
        "representation_inequality": variance,
        "perfect_representation_rate": perfect_rate,
    }


def _simulate_one(
    scenario: ComparisonScenario,
    institution: str,
    seed: int,
) -> Dict[str, Any]:
    """Run a single (scenario, institution, seed) simulation and return a row of metrics."""
    model = _build_model(institution, scenario, seed)
    bills = _generate_bills(model, scenario)

    bills_passed = 0
    for bill in bills:
        if model.pass_legislation(bill):
            bills_passed += 1

    committee_stats = model.get_committee_stats()
    rep_metrics = _representation_metrics(model)

    row: Dict[str, Any] = {
        "scenario": scenario.name,
        "institution": institution,
        "seed": seed,
        "bills_processed": len(bills),
        "bills_passed": bills_passed,
        "passage_rate": bills_passed / len(bills) if bills else 0.0,
        "committee_kill_rate": committee_stats.get("avg_kill_rate", 0.0),
        "committee_amendment_rate": committee_stats.get("avg_amendment_rate", 0.0),
        "total_committee_bills": committee_stats.get("total_bills_considered", 0),
        **rep_metrics,
        "num_legislators": scenario.num_legislators,
        "num_parties": scenario.num_parties,
    }

    if institution == "parliamentary":
        gov = model.get_government_stats()
        row.update(
            {
                "government_formed": gov["government_formed"],
                "coalition_size": gov["coalition_size"],
                "confidence_votes_passed": gov["confidence_votes_passed"],
                "confidence_votes_failed": gov["confidence_votes_failed"],
                "bills_vetoed": 0,
                "gridlock_events": 0,
                "divided_government": None,
                "veto_rate": 0.0,
                "discipline_strength": model.config.discipline_strength,
            }
        )
    else:
        sys_stats = model.get_system_stats()
        sep_stats = model.get_separation_of_powers_stats()
        row.update(
            {
                "government_formed": None,
                "coalition_size": 0,
                "confidence_votes_passed": 0,
                "confidence_votes_failed": 0,
                "bills_vetoed": sys_stats["bills_vetoed"],
                "gridlock_events": sys_stats["gridlock_events"],
                "divided_government": sep_stats["divided_government"],
                "veto_rate": sep_stats["veto_rate"],
                "discipline_strength": model.config.discipline_strength,
            }
        )

    return row


def run_multiseed_comparison(
    scenarios: Optional[Iterable[ComparisonScenario]] = None,
    institutions: Sequence[str] = INSTITUTION_NAMES,
    n_seeds: int = 200,
    base_seed: int = 0,
    n_jobs: int = -1,
    verbose: int = 0,
) -> pd.DataFrame:
    """
    Run N_seeds independent replications for each (scenario, institution) pair.

    Returns a long-form DataFrame with one row per (scenario, institution, seed).
    """
    scenario_list = list(scenarios) if scenarios is not None else list(DEFAULT_SCENARIOS)
    institution_list = list(institutions)

    jobs = [
        (scenario, institution, base_seed + i)
        for scenario in scenario_list
        for institution in institution_list
        for i in range(n_seeds)
    ]

    results = Parallel(n_jobs=n_jobs, backend="loky", verbose=verbose)(
        delayed(_simulate_one)(scenario, institution, seed)
        for scenario, institution, seed in jobs
    )

    return pd.DataFrame(results)


def _parse_scenarios(names: Sequence[str]) -> List[ComparisonScenario]:
    if not names or "all" in names:
        return list(DEFAULT_SCENARIOS)
    missing = [n for n in names if n not in SCENARIOS_BY_NAME]
    if missing:
        raise SystemExit(f"Unknown scenario(s): {missing}. Available: {list(SCENARIOS_BY_NAME)}")
    return [SCENARIOS_BY_NAME[n] for n in names]


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-seed institutional comparison")
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["all"],
        help="Scenario names, or 'all' (default).",
    )
    parser.add_argument("--seeds", type=int, default=200, help="Seeds per (scenario, institution).")
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--jobs", type=int, default=-1, help="joblib n_jobs (-1 = all cores).")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/phase_a/"),
        help="Output directory for CSVs.",
    )
    parser.add_argument("--verbose", type=int, default=5)
    parser.add_argument("--no-plots", action="store_true", help="Skip PNG rendering.")
    args = parser.parse_args(argv)

    scenarios = _parse_scenarios(args.scenarios)
    args.output.mkdir(parents=True, exist_ok=True)

    print(
        f"Running {len(scenarios)} scenarios × {len(INSTITUTION_NAMES)} institutions × {args.seeds} seeds "
        f"= {len(scenarios) * len(INSTITUTION_NAMES) * args.seeds} simulations on {args.jobs} jobs",
        flush=True,
    )

    df = run_multiseed_comparison(
        scenarios=scenarios,
        n_seeds=args.seeds,
        base_seed=args.base_seed,
        n_jobs=args.jobs,
        verbose=args.verbose,
    )

    long_path = args.output / "results_long.csv"
    df.to_csv(long_path, index=False)
    print(f"Wrote {len(df)} rows to {long_path}")

    summary_df = summarize(df)
    summary_path = args.output / "summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"Wrote {len(summary_df)} rows to {summary_path}")

    hyp_df = pairwise_tests(df)
    hyp_path = args.output / "hypothesis_tests.csv"
    hyp_df.to_csv(hyp_path, index=False)
    print(f"Wrote {len(hyp_df)} rows to {hyp_path}")

    if not args.no_plots:
        paths = render_all(df, summary_df, args.output / "figures")
        for p in paths:
            print(f"Wrote figure {p}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
