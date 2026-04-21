from __future__ import annotations

import pandas as pd

from experiments.scenarios import BASELINE
from experiments.sensitivity import (
    INSTITUTION_PROBLEMS,
    _apply_params,
    analyze_morris,
    analyze_sobol,
    run_morris,
    run_sobol,
)


def test_apply_params_produces_valid_config_and_scenario():
    problem = INSTITUTION_PROBLEMS["parliamentary"]
    sample = [0.5, 0.55, 0.3, 0.7, 3.4, 6.6]
    config, scenario = _apply_params("parliamentary", BASELINE, sample)
    assert config.discipline_strength == 0.5
    assert config.confidence_threshold == 0.55
    assert config.committee_gatekeeping_power == 0.3
    assert config.opposition_discipline_multiplier == 0.7
    # Integer params round to nearest
    assert scenario.num_parties == 3
    assert scenario.num_constituencies == 7


def test_run_morris_smoke_parliamentary():
    df = run_morris(
        "parliamentary",
        BASELINE,
        n_trajectories=4,
        seeds_per_sample=1,
        n_jobs=1,
    )
    # Morris design = (D+1) * n_trajectories = 7 * 4 = 28
    assert len(df) == 28
    assert (df["passage_rate"] >= 0).all()
    assert (df["passage_rate"] <= 1).all()
    # No duplicate sample_idx
    assert df["sample_idx"].nunique() == len(df)


def test_morris_analysis_returns_one_row_per_parameter():
    df = run_morris(
        "republican",
        BASELINE,
        n_trajectories=4,
        seeds_per_sample=1,
        n_jobs=1,
    )
    res = analyze_morris(df, "republican")
    assert len(res) == 6
    assert set(res["parameter"]) == set(INSTITUTION_PROBLEMS["republican"]["names"])
    assert {"mu", "mu_star", "sigma", "mu_star_conf"}.issubset(res.columns)


def test_run_sobol_smoke_and_analysis():
    df = run_sobol(
        "republican",
        BASELINE,
        n_samples=8,
        seeds_per_sample=1,
        n_jobs=1,
    )
    # Sobol without second order: N * (D + 2) = 8 * 8 = 64
    assert len(df) == 64
    res = analyze_sobol(df, "republican")
    assert len(res) == 6
    assert {"S1", "S1_conf", "ST", "ST_conf"}.issubset(res.columns)


def test_sensitivity_is_deterministic():
    a = run_morris(
        "parliamentary",
        BASELINE,
        n_trajectories=4,
        seeds_per_sample=1,
        n_jobs=1,
    )
    b = run_morris(
        "parliamentary",
        BASELINE,
        n_trajectories=4,
        seeds_per_sample=1,
        n_jobs=1,
    )
    pd.testing.assert_frame_equal(a, b)
