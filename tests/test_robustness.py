from __future__ import annotations

import pandas as pd
import pytest

from experiments.discipline_robustness import (
    INSTITUTIONS,
    MAJORITY_DEPENDENCE_ORDER,
    _config_with_discipline,
    check_monotone_ordering,
    compute_rescue_deltas,
    run_discipline_grid,
)
from experiments.scenarios import BASELINE, FRAGMENTED


def test_config_builder_sets_discipline_for_every_institution():
    for inst in INSTITUTIONS:
        cfg = _config_with_discipline(inst, 0.42)
        assert cfg.discipline_strength == 0.42


def test_majority_dependence_order_is_well_defined():
    assert set(MAJORITY_DEPENDENCE_ORDER) == set(INSTITUTIONS)
    assert MAJORITY_DEPENDENCE_ORDER[0] == "parliamentary"
    assert MAJORITY_DEPENDENCE_ORDER[-1] == "republican"


def test_discipline_grid_produces_rows_for_every_cell():
    D_values = [0.0, 0.5]
    df = run_discipline_grid(
        discipline_values=D_values,
        scenarios=[BASELINE],
        n_seeds=3,
        n_jobs=1,
    )
    # 4 institutions × 1 scenario × 2 D values × 3 seeds = 24
    assert len(df) == 24
    assert set(df["discipline_strength"].unique()) == set(D_values)
    assert set(df["institution"].unique()) == set(INSTITUTIONS)


def test_rescue_deltas_require_zero_in_grid():
    df_no_zero = run_discipline_grid(
        discipline_values=[0.3, 0.8],
        scenarios=[BASELINE],
        n_seeds=2,
        n_jobs=1,
    )
    with pytest.raises(ValueError, match="discipline_strength=0.0"):
        compute_rescue_deltas(df_no_zero)


def test_rescue_at_zero_is_zero():
    df = run_discipline_grid(
        discipline_values=[0.0, 0.5],
        scenarios=[BASELINE],
        n_seeds=3,
        n_jobs=1,
    )
    deltas = compute_rescue_deltas(df)
    zero_rows = deltas[deltas["discipline_strength"] == 0.0]
    assert (zero_rows["rescue_vs_zero"] == 0.0).all()


def test_fragmented_rescue_ordering_is_monotone_over_discipline_grid():
    """Regression: the Phase C headline finding must survive varying the common
    discipline level. If this test breaks, the paper's lead claim is in trouble."""
    df = run_discipline_grid(
        discipline_values=[0.0, 0.2, 0.5, 0.8],
        scenarios=[FRAGMENTED],
        n_seeds=50,
        n_jobs=-1,
    )
    deltas = compute_rescue_deltas(df)
    orders = check_monotone_ordering(deltas, "fragmented", MAJORITY_DEPENDENCE_ORDER)
    assert orders["matches_expected_order"].all(), (
        f"Monotone ordering violated at D values: "
        f"{orders[~orders['matches_expected_order']]['discipline_strength'].tolist()}"
    )
