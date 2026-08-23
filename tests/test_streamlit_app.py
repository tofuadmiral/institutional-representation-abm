from __future__ import annotations

import importlib

import pandas as pd
import pytest

from experiments.parameter_sweep import (
    SWEEPABLE_PARAMETERS,
    SWEEPABLE_SCENARIO_PARAMETERS,
    run_parameter_sweep,
    sweep_all_institutions,
)
from experiments.scenarios import BASELINE

from config import ParliamentaryConfig, premier_presidential_config


def test_streamlit_modules_import_cleanly():
    """Importing the app must not crash outside a Streamlit session."""
    importlib.import_module("streamlit_app.configs")
    importlib.import_module("streamlit_app.runners")
    importlib.import_module("streamlit_app.app")


def test_slider_specs_cover_every_institution():
    from streamlit_app.configs import INSTITUTIONS, SLIDER_SPECS
    assert set(SLIDER_SPECS.keys()) == set(INSTITUTIONS)
    for inst, specs in SLIDER_SPECS.items():
        for name, spec in specs.items():
            lo, hi, step, default = spec
            assert lo < hi, f"{inst}.{name}: lo must be < hi"
            assert lo <= default <= hi, f"{inst}.{name}: default out of range"


def test_select_specs_reference_valid_config_fields():
    import dataclasses

    from streamlit_app.configs import INSTITUTIONS, SELECT_SPECS
    cfgs = {
        "parliamentary": ParliamentaryConfig(),
        "premier_presidential": premier_presidential_config(),
    }
    assert set(SELECT_SPECS.keys()) <= set(INSTITUTIONS)
    for inst, specs in SELECT_SPECS.items():
        fields = {f.name for f in dataclasses.fields(cfgs[inst])}
        for name, (options, default) in specs.items():
            assert name in fields, f"{inst}.{name} not a config field"
            assert default in options


def test_parameter_sweep_returns_expected_shape():
    values = [0.0, 0.25, 0.5, 0.75, 1.0]
    df = run_parameter_sweep(
        "parliamentary", "discipline_strength", values,
        n_seeds=3, n_jobs=1,
    )
    assert len(df) == len(values) * 3
    assert set(df["discipline_strength"].unique()) == set(values)
    assert (df["passage_rate"] >= 0).all()
    assert (df["passage_rate"] <= 1).all()


def test_parameter_sweep_is_monotone_for_discipline_parliamentary():
    """Sanity: parliamentary passage should grow with discipline under a baseline scenario."""
    values = [0.0, 0.4, 0.8]
    df = run_parameter_sweep(
        "parliamentary", "discipline_strength", values,
        n_seeds=20, n_jobs=1,
    )
    means = df.groupby("discipline_strength")["passage_rate"].mean()
    assert means[0.0] < means[0.4]
    assert means[0.4] < means[0.8]


def test_sweep_all_institutions_includes_every_institution():
    df = sweep_all_institutions("discipline_strength", [0.0, 1.0], n_seeds=2, n_jobs=1)
    assert set(df["institution"].unique()) == {
        "parliamentary", "republican", "premier_presidential", "president_parliamentary",
    }


def test_sweep_all_institutions_scenario_parameter():
    df = sweep_all_institutions("num_parties", [2, 5], n_seeds=2, n_jobs=1)
    # num_parties is a scenario-level knob so all 4 institutions participate
    assert set(df["institution"].unique()) == {
        "parliamentary", "republican", "premier_presidential", "president_parliamentary",
    }
    assert set(df["num_parties"].unique()) == {2, 5}


def test_sweepable_parameters_are_subset_of_config_fields():
    import dataclasses
    from config import (
        ParliamentaryConfig, RepublicanConfig,
        premier_presidential_config, president_parliamentary_config,
    )
    cfgs = {
        "parliamentary": ParliamentaryConfig(),
        "republican": RepublicanConfig(),
        "premier_presidential": premier_presidential_config(),
        "president_parliamentary": president_parliamentary_config(),
    }
    for inst, params in SWEEPABLE_PARAMETERS.items():
        fields = {f.name for f in dataclasses.fields(cfgs[inst])}
        for param in params:
            assert param in fields, f"{param} not in {inst} config fields"


def test_custom_multiseed_honours_passed_configs():
    from streamlit_app.runners import run_custom_multiseed
    import dataclasses
    from config import ParliamentaryConfig, RepublicanConfig, premier_presidential_config, president_parliamentary_config
    configs = {
        "parliamentary": dataclasses.replace(ParliamentaryConfig(), discipline_strength=0.0),
        "republican": RepublicanConfig(),
        "premier_presidential": premier_presidential_config(),
        "president_parliamentary": president_parliamentary_config(),
    }
    df = run_custom_multiseed(
        [BASELINE], configs=configs, n_seeds=5, n_jobs=1,
    )
    assert len(df) == 5 * 4
    assert set(df["institution"].unique()) == set(configs.keys())
