"""Institution-dependent representation quality.

The existing `_representation_metrics` measures constituency-to-legislator
alignment, which is identical across institutions because all four use the
same `BaseInstitutionModel._create_legislators` deterministic assignment.
That's a limitation of the existing metric, not a finding about institutions.

This module computes a different, institution-dependent metric: the average
ideological distance between *passed bills* and the median (or mean)
constituency ideology. The intuition: constituencies want policy close to
their median; institutions mediate which bills get through; the average gap
between passed bills and the constituent median tells us how well each
institution represents the electorate in policy output.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from agents.constituency import ConstituencyAgent
from bills.bill import Bill
from config import (
    ParliamentaryConfig,
    RepublicanConfig,
    premier_presidential_config,
    president_parliamentary_config,
)
from experiments.scenarios import (
    BASELINE, ComparisonScenario, DEFAULT_SCENARIOS, SCENARIOS_BY_NAME,
)
from institutions.parliamentary import ParliamentaryModel
from institutions.republican import RepublicanModel
from institutions.semi_presidential import SemiPresidentialModel

INSTITUTIONS = (
    "parliamentary", "republican", "premier_presidential", "president_parliamentary",
)


def _build(institution: str, scenario: ComparisonScenario, seed: int):
    if institution == "parliamentary":
        return ParliamentaryModel(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=ParliamentaryConfig(), seed=seed,
        )
    if institution == "republican":
        return RepublicanModel(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=RepublicanConfig(), seed=seed,
        )
    if institution == "premier_presidential":
        return SemiPresidentialModel(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=premier_presidential_config(), seed=seed,
        )
    if institution == "president_parliamentary":
        return SemiPresidentialModel(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=president_parliamentary_config(), seed=seed,
        )
    raise ValueError(f"Unknown institution: {institution}")


def _constituency_median_ideology(model) -> Tuple[float, float]:
    ideologies = [
        a.ideology for a in model.schedule.agents if isinstance(a, ConstituencyAgent)
    ]
    if not ideologies:
        return (0.0, 0.0)
    arr = np.array(ideologies)
    return (float(np.median(arr[:, 0])), float(np.median(arr[:, 1])))


def _simulate_with_tracking(
    scenario: ComparisonScenario,
    institution: str,
    seed: int,
) -> Dict[str, Any]:
    model = _build(institution, scenario, seed)
    median = _constituency_median_ideology(model)

    low, high = scenario.bill_ideology_range
    passed_distances: List[float] = []
    proposed_distances: List[float] = []
    n_passed = 0
    for i in range(scenario.num_bills):
        ideology = (model.random.uniform(low, high), model.random.uniform(low, high))
        salience = model.random.uniform(0.3, 1.0)
        bill = Bill(bill_id=i, ideology=ideology, salience=salience)
        distance = (
            (ideology[0] - median[0]) ** 2 + (ideology[1] - median[1]) ** 2
        ) ** 0.5
        proposed_distances.append(distance)
        if model.pass_legislation(bill):
            passed_distances.append(distance)
            n_passed += 1

    return {
        "scenario": scenario.name,
        "institution": institution,
        "seed": seed,
        "bills_processed": scenario.num_bills,
        "bills_passed": n_passed,
        "passage_rate": n_passed / max(scenario.num_bills, 1),
        "mean_proposed_distance": float(np.mean(proposed_distances)) if proposed_distances else 0.0,
        "mean_passed_distance": (
            float(np.mean(passed_distances)) if passed_distances else float("nan")
        ),
        "policy_representation_gap": (
            # What was passed minus what was offered. Positive = passed bills are
            # FURTHER from median than random draws (anti-representative filter);
            # negative = passed bills are CLOSER (pro-representative filter).
            (float(np.mean(passed_distances)) - float(np.mean(proposed_distances)))
            if passed_distances else float("nan")
        ),
    }


def run_representation_analysis(
    scenarios: Optional[Iterable[ComparisonScenario]] = None,
    institutions: Sequence[str] = INSTITUTIONS,
    n_seeds: int = 100,
    base_seed: int = 0,
    n_jobs: int = -1,
) -> pd.DataFrame:
    scenario_list = list(scenarios) if scenarios is not None else list(DEFAULT_SCENARIOS)
    jobs = [
        (scenario, inst, base_seed + i)
        for scenario in scenario_list
        for inst in institutions
        for i in range(n_seeds)
    ]
    results = Parallel(n_jobs=n_jobs, backend="loky", verbose=0)(
        delayed(_simulate_with_tracking)(scenario, inst, seed)
        for scenario, inst, seed in jobs
    )
    return pd.DataFrame(results)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Institution-dependent representation analysis"
    )
    parser.add_argument("--scenarios", nargs="+", default=["all"])
    parser.add_argument("--seeds", type=int, default=200)
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--jobs", type=int, default=-1)
    parser.add_argument("--output", type=Path, default=Path("results/phase_g/"))
    args = parser.parse_args(argv)

    args.output.mkdir(parents=True, exist_ok=True)
    if "all" in args.scenarios:
        scenarios = list(DEFAULT_SCENARIOS)
    else:
        scenarios = [SCENARIOS_BY_NAME[n] for n in args.scenarios]

    df = run_representation_analysis(
        scenarios=scenarios, n_seeds=args.seeds,
        base_seed=args.base_seed, n_jobs=args.jobs,
    )
    path = args.output / "representation_long.csv"
    df.to_csv(path, index=False)
    print(f"Wrote {len(df)} rows to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
