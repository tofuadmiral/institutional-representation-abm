"""Robustness check: party-clustered legislator ideologies.

The default initialisation spreads legislators evenly along the ideological
diagonal with round-robin party assignment, which makes every party maximally
heterogeneous internally. That choice plausibly inflates the *magnitude* of the
``no_discipline`` ablation effect: the whip has more work to do when party
members span the whole spectrum. This experiment re-initialises legislator
ideologies as (own-party position + Gaussian noise) and re-runs the discipline
ablation, to test whether the fragmented rescue ordering

    parliamentary > premier_presidential > president_parliamentary > republican

is an artefact of the spread initialisation or a structural property.

Following the ablation convention, the clustered initialisation is applied by
patching instantiated models rather than adding research-only flags to the
institution classes. Re-assigning ideologies after construction is consistent
because nothing at initialisation consumes legislator ideologies: government
formation and executive election read party seat counts, and committee
assignment is party-proportional.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

import pandas as pd
from joblib import Parallel, delayed

from experiments.ablation import _build_ablated_model
from experiments.multiseed_comparison import (
    INSTITUTION_NAMES,
    _generate_bills,
    _representation_metrics,
)
from experiments.scenarios import (
    FRAGMENTED,
    POLARIZED,
    ComparisonScenario,
    SCENARIOS_BY_NAME,
)

CLUSTER_SPREAD_DEFAULT = 0.15
ABLATIONS = ("baseline", "no_discipline")


def apply_clustered_ideologies(model, seed: int, spread: float = CLUSTER_SPREAD_DEFAULT) -> None:
    """Re-assign legislator ideologies to (party position + Gaussian noise).

    Uses a dedicated RNG so the model's own RNG stream (and therefore all
    downstream bill/vote draws) is identical to the un-clustered run with the
    same seed. Constituency and party positions are left untouched.
    """
    rng = random.Random(f"clustered-{seed}")
    for legislator in sorted(model.legislators, key=lambda a: a.unique_id):
        if legislator.party_id is None:
            continue
        px, py = model._default_ideology(legislator.party_id, model.num_parties)
        x = max(-1.0, min(1.0, px + rng.gauss(0.0, spread)))
        y = max(-1.0, min(1.0, py + rng.gauss(0.0, spread)))
        legislator.ideology = (x, y)


def _simulate(
    scenario: ComparisonScenario,
    institution: str,
    ablation: str,
    seed: int,
    spread: float,
) -> Dict[str, Any]:
    model = _build_ablated_model(institution, scenario, seed, ablation)
    apply_clustered_ideologies(model, seed, spread)
    bills = _generate_bills(model, scenario)

    bills_passed = sum(1 for b in bills if model.pass_legislation(b))
    rep_metrics = _representation_metrics(model)
    return {
        "scenario": scenario.name,
        "institution": institution,
        "ablation": ablation,
        "seed": seed,
        "cluster_spread": spread,
        "bills_processed": len(bills),
        "bills_passed": bills_passed,
        "passage_rate": bills_passed / max(len(bills), 1),
        **rep_metrics,
    }


def run_clustered_ablation(
    scenarios: Optional[Iterable[ComparisonScenario]] = None,
    institutions: Sequence[str] = INSTITUTION_NAMES,
    n_seeds: int = 100,
    base_seed: int = 0,
    spread: float = CLUSTER_SPREAD_DEFAULT,
    n_jobs: int = -1,
    verbose: int = 0,
) -> pd.DataFrame:
    scenario_list = list(scenarios) if scenarios is not None else [FRAGMENTED, POLARIZED]
    jobs = [
        (scenario, inst, ablation, base_seed + i, spread)
        for scenario in scenario_list
        for inst in institutions
        for ablation in ABLATIONS
        for i in range(n_seeds)
    ]
    results = Parallel(n_jobs=n_jobs, backend="loky", verbose=verbose)(
        delayed(_simulate)(*job) for job in jobs
    )
    return pd.DataFrame(results)


def rescue_deltas(df: pd.DataFrame) -> pd.DataFrame:
    """Per (scenario, institution): mean passage under both arms and the
    no_discipline delta (positive = removing discipline rescues passage)."""
    grouped = (
        df.groupby(["scenario", "institution", "ablation"])["passage_rate"]
        .mean()
        .unstack("ablation")
        .reset_index()
    )
    grouped["no_discipline_delta"] = grouped["no_discipline"] - grouped["baseline"]
    return grouped


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Clustered-initialisation robustness runner.")
    parser.add_argument("--scenarios", nargs="+", default=["fragmented", "polarized"])
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--spread", type=float, default=CLUSTER_SPREAD_DEFAULT)
    parser.add_argument("--jobs", type=int, default=-1)
    parser.add_argument("--output", type=Path, default=Path("results/clustered_init/"))
    parser.add_argument("--verbose", type=int, default=5)
    args = parser.parse_args(argv)

    args.output.mkdir(parents=True, exist_ok=True)
    scenarios = [SCENARIOS_BY_NAME[name] for name in args.scenarios]

    df = run_clustered_ablation(
        scenarios=scenarios,
        n_seeds=args.seeds,
        base_seed=args.base_seed,
        spread=args.spread,
        n_jobs=args.jobs,
        verbose=args.verbose,
    )
    long_path = args.output / "clustered_ablation_long.csv"
    df.to_csv(long_path, index=False)
    print(f"Wrote {len(df)} rows to {long_path}")

    deltas = rescue_deltas(df)
    deltas_path = args.output / "clustered_rescue_deltas.csv"
    deltas.to_csv(deltas_path, index=False)
    print(f"Wrote {len(deltas)} rows to {deltas_path}")
    print(deltas.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
