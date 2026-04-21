from __future__ import annotations

import pandas as pd

from experiments.ablation import (
    ABLATION_NAMES,
    _build_ablated_model,
    _is_applicable,
    _simulate_ablation,
    ablation_deltas,
    run_ablation,
)
from experiments.scenarios import BASELINE, FRAGMENTED


def test_no_veto_not_applicable_to_parliamentary():
    assert _is_applicable("parliamentary", "no_veto") is False
    assert _is_applicable("republican", "no_veto") is True
    for ablation in ABLATION_NAMES:
        if ablation != "no_veto":
            assert _is_applicable("parliamentary", ablation) is True
            assert _is_applicable("republican", ablation) is True


def test_no_discipline_sets_discipline_to_zero():
    parl = _build_ablated_model("parliamentary", BASELINE, seed=0, ablation="no_discipline")
    rep = _build_ablated_model("republican", BASELINE, seed=0, ablation="no_discipline")
    assert parl.config.discipline_strength == 0.0
    assert rep.config.discipline_strength == 0.0


def test_no_committees_skips_committee_routing():
    """With committee routing bypassed, bills_in_committee must stay empty."""
    model = _build_ablated_model("parliamentary", BASELINE, seed=0, ablation="no_committees")
    from bills.bill import Bill
    for i in range(5):
        bill = Bill(bill_id=i, ideology=(0.0, 0.0), salience=0.5)
        model.pass_legislation(bill)
    assert len(model.bills_in_committee) == 0


def test_no_veto_never_vetoes():
    model = _build_ablated_model("republican", FRAGMENTED, seed=0, ablation="no_veto")
    from bills.bill import Bill
    for i in range(10):
        bill = Bill(bill_id=i, ideology=(0.9, 0.9), salience=0.8)
        model.pass_legislation(bill)
    assert model.bills_vetoed == 0


def test_ablation_run_produces_all_cells():
    df = run_ablation(scenarios=[BASELINE], n_seeds=2, n_jobs=1)
    # parliamentary: 3 ablations × 2 seeds = 6; republican: 4 × 2 = 8; total 14
    assert len(df) == 14
    expected = {
        ("parliamentary", "baseline"), ("parliamentary", "no_committees"),
        ("parliamentary", "no_discipline"),
        ("republican", "baseline"), ("republican", "no_committees"),
        ("republican", "no_discipline"), ("republican", "no_veto"),
    }
    got = set(df.groupby(["institution", "ablation"]).groups.keys())
    assert got == expected


def test_ablation_deltas_baseline_row_is_zero():
    df = run_ablation(scenarios=[BASELINE], n_seeds=5, n_jobs=1)
    deltas = ablation_deltas(df)
    baseline_rows = deltas[deltas["ablation"] == "baseline"]
    assert (baseline_rows["delta_vs_baseline"] == 0.0).all()


def test_ablation_is_deterministic_under_seed():
    a = _simulate_ablation(BASELINE, "parliamentary", "no_committees", seed=42)
    b = _simulate_ablation(BASELINE, "parliamentary", "no_committees", seed=42)
    assert a == b
