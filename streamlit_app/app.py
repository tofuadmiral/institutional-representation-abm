"""Streamlit UI for the institutional representation ABM.

Launch:

    streamlit run streamlit_app/app.py

Three tabs, all backed by the N-seed harness:

  Scenario Comparison: run every selected scenario against every selected
    institution using the sidebar-tuned configs; show violin + summary +
    pairwise hypothesis tests.

  Parameter Sweep: pick one parameter, sweep it across a range, plot passage
    rate (with 95% bootstrap CI) as a curve per institution.

  Ablations: run the mechanism-ablation harness and display the Δ forest plot.

The sidebar exposes every tunable config field. Running anything is cached via
@st.cache_data keyed on the full parameter set, so dragging a slider that
isn't in the current computation path doesn't re-execute.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable when run from streamlit.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import dataclasses  # noqa: E402
from typing import Any, Dict, List, Sequence  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from analysis.aggregate import all_pairwise_tests, bootstrap_ci, summarize  # noqa: E402
from analysis.plots import violin_plot_distributions  # noqa: E402
from analysis.sensitivity_plots import ablation_forest  # noqa: E402
from experiments.ablation import run_ablation  # noqa: E402
from experiments.parameter_sweep import (  # noqa: E402
    SWEEPABLE_PARAMETERS,
    SWEEPABLE_SCENARIO_PARAMETERS,
)
from experiments.scenarios import SCENARIOS_BY_NAME  # noqa: E402
from streamlit_app.configs import INSTITUTIONS, build_configs_from_sidebar  # noqa: E402
from streamlit_app.runners import run_custom_multiseed, run_custom_sweep  # noqa: E402


st.set_page_config(page_title="Institutional ABM", layout="wide")
st.title("Institutional Representation ABM")
st.caption(
    "Compare parliamentary, republican, and two semi-presidential variants on "
    "passage rate, veto rate, and representation quality."
)

# ------------------------------------------------------------------ sidebar

with st.sidebar:
    st.header("Simulation controls")
    n_seeds = st.slider("Seeds per (scenario × institution)", 10, 200, 50, step=10)
    base_seed = st.number_input("Base seed", value=0, step=1)
    selected_institutions = st.multiselect(
        "Institutions", list(INSTITUTIONS), default=list(INSTITUTIONS),
    )
    st.divider()
    st.header("Institution configs")
    custom_configs = build_configs_from_sidebar()


def _filter_configs(configs: Dict[str, Any], institutions: Sequence[str]) -> Dict[str, Any]:
    return {k: v for k, v in configs.items() if k in institutions}


@st.cache_data(show_spinner="Running N-seed simulations...")
def _cached_multiseed(
    scenario_names: tuple,
    institution_names: tuple,
    n_seeds: int,
    base_seed: int,
    config_hashes: tuple,
    configs: Dict[str, Any],
) -> pd.DataFrame:
    scenarios = [SCENARIOS_BY_NAME[n] for n in scenario_names]
    return run_custom_multiseed(
        scenarios=scenarios,
        configs={k: configs[k] for k in institution_names},
        n_seeds=n_seeds,
        base_seed=base_seed,
        n_jobs=-1,
    )


@st.cache_data(show_spinner="Running parameter sweep...")
def _cached_sweep(
    institution: str,
    param_name: str,
    values: tuple,
    scenario_name: str,
    n_seeds: int,
    base_seed: int,
    _config,
) -> pd.DataFrame:
    scenario = SCENARIOS_BY_NAME[scenario_name]
    return run_custom_sweep(
        institution=institution,
        param_name=param_name,
        values=list(values),
        base_config=_config,
        scenario=scenario,
        n_seeds=n_seeds,
        base_seed=base_seed,
        n_jobs=-1,
    )


@st.cache_data(show_spinner="Running ablation runs...")
def _cached_ablation(
    scenario_names: tuple,
    institution_names: tuple,
    n_seeds: int,
    base_seed: int,
) -> pd.DataFrame:
    scenarios = [SCENARIOS_BY_NAME[n] for n in scenario_names]
    return run_ablation(
        scenarios=scenarios,
        institutions=institution_names,
        n_seeds=n_seeds,
        base_seed=base_seed,
        n_jobs=-1,
    )


def _config_signature(configs: Dict[str, Any]) -> tuple:
    """Hashable signature of a configs dict for cache keying."""
    out = []
    for inst, cfg in sorted(configs.items()):
        # dataclass asdict flattens nested configs too, which is what we want here.
        flat = dataclasses.asdict(cfg)
        out.append((inst, tuple(sorted((k, repr(v)) for k, v in flat.items()))))
    return tuple(out)


# --------------------------------------------------------------------- tabs

tab1, tab2, tab3 = st.tabs(
    ["Scenario Comparison", "Parameter Sweep", "Mechanism Ablations"]
)

# -------- Scenario Comparison

with tab1:
    st.subheader("Compare institutions across scenarios")
    st.caption(
        "Pick scenarios and institutions; each (scenario × institution) cell is run with "
        "N seeds using the sidebar-tuned configs."
    )
    scenario_names = st.multiselect(
        "Scenarios",
        list(SCENARIOS_BY_NAME.keys()),
        default=list(SCENARIOS_BY_NAME.keys()),
        key="compare_scenarios",
    )
    run_compare = st.button("Run comparison", key="run_compare", type="primary")

    if run_compare and scenario_names and selected_institutions:
        configs = _filter_configs(custom_configs, selected_institutions)
        df = _cached_multiseed(
            tuple(scenario_names),
            tuple(selected_institutions),
            int(n_seeds),
            int(base_seed),
            _config_signature(configs),
            configs,
        )
        st.success(f"Collected {len(df)} runs.")
        summary = summarize(df, metrics=("passage_rate",))
        st.dataframe(
            summary[["scenario", "institution", "n", "mean", "ci_low", "ci_high"]],
            use_container_width=True,
        )
        st.pyplot(violin_plot_distributions(df))
        if len(selected_institutions) >= 2:
            hyp = all_pairwise_tests(df, metrics=("passage_rate",))
            st.subheader("Pairwise comparisons (passage rate)")
            st.dataframe(
                hyp[[
                    "scenario", "institution_a", "institution_b",
                    "mean_a", "mean_b", "mean_diff", "welch_p", "cohens_d",
                ]],
                use_container_width=True,
            )

# -------- Parameter Sweep

with tab2:
    st.subheader("Sweep one parameter across a range")
    st.caption(
        "Pick a parameter, set a min/max/steps range, and see how passage rate responds. "
        "Uses the sidebar config as the anchor for all other fields."
    )
    sweep_cols = st.columns(2)
    with sweep_cols[0]:
        sweep_inst = st.selectbox("Institution", selected_institutions or list(INSTITUTIONS))
        sweep_scenario = st.selectbox("Scenario", list(SCENARIOS_BY_NAME.keys()))
    with sweep_cols[1]:
        candidates = list(SWEEPABLE_PARAMETERS.get(sweep_inst, ())) + list(SWEEPABLE_SCENARIO_PARAMETERS)
        sweep_param = st.selectbox("Parameter", candidates)

    sweep_range_cols = st.columns(3)
    lo = sweep_range_cols[0].number_input("Min", value=0.0)
    hi = sweep_range_cols[1].number_input("Max", value=1.0)
    steps = sweep_range_cols[2].number_input("Steps", value=11, step=1, min_value=2, max_value=40)

    run_sweep = st.button("Run sweep", key="run_sweep", type="primary")
    if run_sweep:
        values = tuple(np.linspace(lo, hi, int(steps)).tolist())
        if sweep_param in SWEEPABLE_SCENARIO_PARAMETERS:
            base_cfg = custom_configs[sweep_inst]
            from experiments.parameter_sweep import run_parameter_sweep
            sweep_df = run_parameter_sweep(
                sweep_inst,
                sweep_param,
                values,
                scenario=SCENARIOS_BY_NAME[sweep_scenario],
                n_seeds=int(n_seeds),
                base_seed=int(base_seed),
                base_config=base_cfg,
                n_jobs=-1,
                verbose=0,
            )
        else:
            sweep_df = _cached_sweep(
                sweep_inst,
                sweep_param,
                values,
                sweep_scenario,
                int(n_seeds),
                int(base_seed),
                custom_configs[sweep_inst],
            )

        curve_rows = []
        for v, sub in sweep_df.groupby(sweep_param, sort=True):
            vals = sub["passage_rate"].to_numpy()
            low, high = bootstrap_ci(vals)
            curve_rows.append({
                sweep_param: v,
                "mean": float(vals.mean()),
                "ci_low": low,
                "ci_high": high,
                "n": len(vals),
            })
        curve = pd.DataFrame(curve_rows)
        st.line_chart(curve.set_index(sweep_param)[["mean", "ci_low", "ci_high"]])
        st.dataframe(curve, use_container_width=True)

# -------- Mechanism Ablations

with tab3:
    st.subheader("Ablation: disable mechanisms one at a time")
    st.caption(
        "Each ablation runs with the institution's default config (not the sidebar values), "
        "since the toggles themselves are the object of study."
    )
    ablation_scenarios = st.multiselect(
        "Scenarios", list(SCENARIOS_BY_NAME.keys()),
        default=["baseline", "fragmented"], key="ablation_scenarios",
    )
    run_ablations = st.button("Run ablations", key="run_ablations", type="primary")
    if run_ablations and ablation_scenarios and selected_institutions:
        df = _cached_ablation(
            tuple(ablation_scenarios),
            tuple(selected_institutions),
            int(n_seeds),
            int(base_seed),
        )
        from experiments.ablation import ablation_deltas
        deltas = ablation_deltas(df)
        st.dataframe(
            deltas[["scenario", "institution", "ablation", "mean", "delta_vs_baseline"]],
            use_container_width=True,
        )
        st.pyplot(ablation_forest(deltas))
