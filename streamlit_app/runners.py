"""Thin wrappers around the experiment runners that accept custom configs.

The existing `run_multiseed_comparison` hardcodes default configs per
institution. The Streamlit app needs to pass user-tuned configs, so we wrap
`_simulate_with_config` from the parameter_sweep module.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Sequence

import pandas as pd
from joblib import Parallel, delayed

from experiments.ablation import _simulate_ablation
from experiments.parameter_sweep import _simulate_with_config
from experiments.scenarios import ComparisonScenario

INSTITUTIONS_WITH_VETO = {"republican", "premier_presidential", "president_parliamentary"}


def run_custom_multiseed(
    scenarios: Sequence[ComparisonScenario],
    configs: Dict[str, Any],
    n_seeds: int = 50,
    base_seed: int = 0,
    n_jobs: int = -1,
) -> pd.DataFrame:
    """Run the standard N-institution x N-scenario x N-seed cross-product using
    user-supplied configs."""
    jobs: List = []
    for scenario in scenarios:
        for inst, config in configs.items():
            for i in range(n_seeds):
                jobs.append((inst, scenario, config, base_seed + i))

    results = Parallel(n_jobs=n_jobs, backend="loky", verbose=0)(
        delayed(_simulate_with_config)(inst, scenario, config, seed)
        for inst, scenario, config, seed in jobs
    )
    return pd.DataFrame(results)


def run_custom_sweep(
    institution: str,
    param_name: str,
    values: Sequence[float],
    base_config: Any,
    scenario: ComparisonScenario,
    n_seeds: int = 30,
    base_seed: int = 0,
    n_jobs: int = -1,
) -> pd.DataFrame:
    """Sweep a single parameter using a user-tuned base config as the anchor point."""
    jobs: List = []
    for val in values:
        overridden = dataclasses.replace(base_config, **{param_name: val})
        for i in range(n_seeds):
            jobs.append((institution, scenario, overridden, base_seed + i, val))

    def _task(inst, sc, cfg, seed, val):
        row = _simulate_with_config(inst, sc, cfg, seed)
        row[param_name] = val
        return row

    results = Parallel(n_jobs=n_jobs, backend="loky", verbose=0)(
        delayed(_task)(*j) for j in jobs
    )
    return pd.DataFrame(results)
