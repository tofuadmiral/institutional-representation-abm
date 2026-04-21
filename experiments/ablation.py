"""Mechanism ablations: turn off committees / discipline / veto one at a time.

Ablations are applied by monkey-patching the instantiated model, not by adding
flags to the institution classes. This keeps the production code free of
research-only branches. Each ablation is localised to a single model instance;
nothing is mutated at the class level.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd
from joblib import Parallel, delayed

from bills.bill import Bill
from config import ParliamentaryConfig, RepublicanConfig
from experiments.multiseed_comparison import (
    INSTITUTION_NAMES,
    _generate_bills,
    _representation_metrics,
)
from experiments.scenarios import (
    BASELINE,
    FRAGMENTED,
    ComparisonScenario,
    SCENARIOS_BY_NAME,
)
from institutions.parliamentary import ParliamentaryModel
from institutions.republican import RepublicanModel

ABLATION_NAMES = ("baseline", "no_committees", "no_discipline", "no_veto")


def _build_ablated_model(
    institution: str,
    scenario: ComparisonScenario,
    seed: int,
    ablation: str,
):
    if institution == "parliamentary":
        base_config = ParliamentaryConfig()
        if ablation == "no_discipline":
            base_config = dataclasses.replace(base_config, discipline_strength=0.0)
        model = ParliamentaryModel(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=base_config,
            seed=seed,
        )
    elif institution == "republican":
        base_config = RepublicanConfig()
        if ablation == "no_discipline":
            base_config = dataclasses.replace(base_config, discipline_strength=0.0)
        model = RepublicanModel(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=base_config,
            seed=seed,
        )
    else:
        raise ValueError(f"Unknown institution: {institution}")

    if ablation == "no_committees":
        # Skip committee routing: every bill goes straight to the floor.
        def _approve(bill: Bill) -> Dict[str, Any]:
            return {"action": "approve", "bill": bill}

        model._route_to_committee = _approve  # type: ignore[method-assign]
    elif ablation == "no_veto" and institution == "republican":
        model._executive_veto_check = lambda bill: False  # type: ignore[method-assign]

    return model


def _simulate_ablation(
    scenario: ComparisonScenario,
    institution: str,
    ablation: str,
    seed: int,
) -> Dict[str, Any]:
    model = _build_ablated_model(institution, scenario, seed, ablation)
    bills = _generate_bills(model, scenario)

    bills_passed = sum(1 for b in bills if model.pass_legislation(b))
    committee_stats = model.get_committee_stats()
    rep_metrics = _representation_metrics(model)

    row: Dict[str, Any] = {
        "scenario": scenario.name,
        "institution": institution,
        "ablation": ablation,
        "seed": seed,
        "bills_processed": len(bills),
        "bills_passed": bills_passed,
        "passage_rate": bills_passed / max(len(bills), 1),
        "committee_kill_rate": committee_stats.get("avg_kill_rate", 0.0),
        "committee_amendment_rate": committee_stats.get("avg_amendment_rate", 0.0),
        **rep_metrics,
    }
    if institution == "republican":
        sys_stats = model.get_system_stats()
        row["bills_vetoed"] = sys_stats["bills_vetoed"]
        row["gridlock_events"] = sys_stats["gridlock_events"]
    return row


def _is_applicable(institution: str, ablation: str) -> bool:
    if ablation == "no_veto" and institution == "parliamentary":
        return False
    return True


def run_ablation(
    scenarios: Optional[Iterable[ComparisonScenario]] = None,
    institutions: Sequence[str] = INSTITUTION_NAMES,
    ablations: Sequence[str] = ABLATION_NAMES,
    n_seeds: int = 100,
    base_seed: int = 0,
    n_jobs: int = -1,
    verbose: int = 0,
) -> pd.DataFrame:
    scenario_list = list(scenarios) if scenarios is not None else [BASELINE, FRAGMENTED]
    jobs = [
        (scenario, inst, ablation, base_seed + i)
        for scenario in scenario_list
        for inst in institutions
        for ablation in ablations
        if _is_applicable(inst, ablation)
        for i in range(n_seeds)
    ]

    results = Parallel(n_jobs=n_jobs, backend="loky", verbose=verbose)(
        delayed(_simulate_ablation)(*job) for job in jobs
    )
    return pd.DataFrame(results)


def ablation_deltas(df: pd.DataFrame) -> pd.DataFrame:
    """Summarise (scenario, institution, ablation) cells and compute Δ vs baseline."""
    grouped = (
        df.groupby(["scenario", "institution", "ablation"])["passage_rate"]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    baselines = (
        grouped[grouped["ablation"] == "baseline"]
        .set_index(["scenario", "institution"])["mean"]
        .to_dict()
    )

    def _delta(row: pd.Series) -> float:
        if row["ablation"] == "baseline":
            return 0.0
        return float(row["mean"] - baselines.get((row["scenario"], row["institution"]), float("nan")))

    grouped["delta_vs_baseline"] = grouped.apply(_delta, axis=1)
    return grouped


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Mechanism ablation runner.")
    parser.add_argument("--scenarios", nargs="+", default=["baseline", "fragmented"])
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--jobs", type=int, default=-1)
    parser.add_argument("--output", type=Path, default=Path("results/phase_b/"))
    parser.add_argument("--verbose", type=int, default=5)
    args = parser.parse_args(argv)

    args.output.mkdir(parents=True, exist_ok=True)
    scenarios = [SCENARIOS_BY_NAME[name] for name in args.scenarios]

    df = run_ablation(
        scenarios=scenarios,
        n_seeds=args.seeds,
        base_seed=args.base_seed,
        n_jobs=args.jobs,
        verbose=args.verbose,
    )
    long_path = args.output / "ablation_long.csv"
    df.to_csv(long_path, index=False)
    print(f"Wrote {len(df)} rows to {long_path}")

    deltas = ablation_deltas(df)
    deltas_path = args.output / "ablation_deltas.csv"
    deltas.to_csv(deltas_path, index=False)
    print(f"Wrote {len(deltas)} rows to {deltas_path}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
