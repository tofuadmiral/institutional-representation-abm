"""Run a 1-D sweep over a single parameter while holding everything else fixed.

Used by the Streamlit sweep tab. The signature is deliberately narrow: one
institution, one parameter, a list of values. Aggregation with bootstrap CIs
is the caller's job (via `analysis.aggregate.summarize`).
"""
from __future__ import annotations

import dataclasses
from typing import Any, Iterable, Optional, Sequence

import pandas as pd
from joblib import Parallel, delayed

from config import (
    ParliamentaryConfig,
    RepublicanConfig,
    premier_presidential_config,
    president_parliamentary_config,
)
from experiments.multiseed_comparison import _simulate_one
from experiments.scenarios import BASELINE, ComparisonScenario


SWEEPABLE_PARAMETERS = {
    "parliamentary": (
        "discipline_strength",
        "confidence_threshold",
        "committee_gatekeeping_power",
        "opposition_discipline_multiplier",
        "confidence_matter_rate",
        "legislative_activity_rate",
    ),
    "republican": (
        "discipline_strength",
        "executive_opposition_rate",
        "max_veto_probability",
        "committee_gatekeeping_power",
        "largest_party_presidency_prob",
        "override_threshold_fraction",
        "legislative_activity_rate",
    ),
    "premier_presidential": (
        "discipline_strength",
        "confidence_threshold",
        "committee_gatekeeping_power",
        "executive_opposition_rate",
        "max_veto_probability",
        "opposition_discipline_multiplier",
    ),
    "president_parliamentary": (
        "discipline_strength",
        "confidence_threshold",
        "committee_gatekeeping_power",
        "executive_opposition_rate",
        "max_veto_probability",
        "presidential_dismissal_rate",
    ),
}

SWEEPABLE_SCENARIO_PARAMETERS = ("num_parties", "num_constituencies", "num_bills")


def _default_config(institution: str):
    if institution == "parliamentary":
        return ParliamentaryConfig()
    if institution == "republican":
        return RepublicanConfig()
    if institution == "premier_presidential":
        return premier_presidential_config()
    if institution == "president_parliamentary":
        return president_parliamentary_config()
    raise ValueError(f"Unknown institution: {institution}")


def _apply_override(
    institution: str,
    scenario: ComparisonScenario,
    param_name: str,
    value: Any,
    base_config: Optional[Any] = None,
):
    """Return (config, scenario) with the single parameter replaced."""
    base_config = base_config or _default_config(institution)
    if param_name in SWEEPABLE_SCENARIO_PARAMETERS:
        coerced = int(round(value)) if param_name in {"num_parties", "num_constituencies", "num_bills"} else value
        modified_scenario = dataclasses.replace(scenario, **{param_name: coerced})
        return base_config, modified_scenario
    modified_config = dataclasses.replace(base_config, **{param_name: value})
    return modified_config, scenario


def _simulate_with_config(
    institution: str,
    scenario: ComparisonScenario,
    config,
    seed: int,
):
    """Invoke _simulate_one after swapping in a custom config.

    `_simulate_one` hardcodes a default config per institution, so we replicate
    the body here with the supplied `config`.
    """
    from bills.bill import Bill
    from institutions.parliamentary import ParliamentaryModel
    from institutions.republican import RepublicanModel
    from institutions.semi_presidential import SemiPresidentialModel

    if institution == "parliamentary":
        model = ParliamentaryModel(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=config, seed=seed,
        )
    elif institution == "republican":
        model = RepublicanModel(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=config, seed=seed,
        )
    elif institution in ("premier_presidential", "president_parliamentary"):
        model = SemiPresidentialModel(
            num_legislators=scenario.num_legislators,
            num_constituencies=scenario.num_constituencies,
            num_parties=scenario.num_parties,
            config=config, seed=seed,
        )
    else:
        raise ValueError(f"Unknown institution: {institution}")

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

    return {
        "institution": institution,
        "scenario": scenario.name,
        "seed": seed,
        "bills_passed": bills_passed,
        "passage_rate": bills_passed / max(scenario.num_bills, 1),
    }


def run_parameter_sweep(
    institution: str,
    param_name: str,
    values: Sequence[float],
    scenario: ComparisonScenario = BASELINE,
    n_seeds: int = 30,
    base_seed: int = 0,
    base_config: Optional[Any] = None,
    n_jobs: int = -1,
    verbose: int = 0,
) -> pd.DataFrame:
    """Sweep `param_name` across `values`, running `n_seeds` replications per point.

    Returns a long-form frame with one row per (value, seed).
    """
    jobs = []
    for val in values:
        config, modified_scenario = _apply_override(
            institution, scenario, param_name, val, base_config=base_config,
        )
        for i in range(n_seeds):
            jobs.append((institution, modified_scenario, config, base_seed + i, val))

    def _task(inst, sc, cfg, seed, val):
        row = _simulate_with_config(inst, sc, cfg, seed)
        row[param_name] = val
        return row

    results = Parallel(n_jobs=n_jobs, backend="loky", verbose=verbose)(
        delayed(_task)(*j) for j in jobs
    )
    return pd.DataFrame(results)


def sweep_all_institutions(
    param_name: str,
    values: Sequence[float],
    institutions: Iterable[str] = (
        "parliamentary", "republican", "premier_presidential", "president_parliamentary",
    ),
    scenario: ComparisonScenario = BASELINE,
    n_seeds: int = 30,
    base_seed: int = 0,
    n_jobs: int = -1,
    verbose: int = 0,
) -> pd.DataFrame:
    """Sweep the same parameter across every institution that supports it (or all if scenario-level)."""
    frames = []
    for inst in institutions:
        if param_name in SWEEPABLE_SCENARIO_PARAMETERS or param_name in SWEEPABLE_PARAMETERS.get(inst, ()):
            df = run_parameter_sweep(
                inst, param_name, values, scenario=scenario,
                n_seeds=n_seeds, base_seed=base_seed, n_jobs=n_jobs, verbose=verbose,
            )
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
