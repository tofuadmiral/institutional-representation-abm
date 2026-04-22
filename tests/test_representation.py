from __future__ import annotations

import pandas as pd

from experiments.representation import (
    INSTITUTIONS,
    _constituency_median_ideology,
    _simulate_with_tracking,
    run_representation_analysis,
)
from experiments.scenarios import BASELINE, POLARIZED


def test_constituency_median_is_well_defined():
    from institutions.parliamentary import ParliamentaryModel
    m = ParliamentaryModel(num_legislators=20, num_constituencies=6, num_parties=3, seed=0)
    median = _constituency_median_ideology(m)
    assert -1.0 <= median[0] <= 1.0
    assert -1.0 <= median[1] <= 1.0


def test_simulate_with_tracking_returns_expected_fields():
    row = _simulate_with_tracking(BASELINE, "parliamentary", seed=0)
    for k in ("scenario", "institution", "seed", "bills_passed", "passage_rate",
              "mean_proposed_distance", "mean_passed_distance",
              "policy_representation_gap"):
        assert k in row
    assert row["bills_passed"] >= 0
    assert row["bills_passed"] <= row["bills_processed"]


def test_representation_analysis_covers_every_institution():
    df = run_representation_analysis(
        scenarios=[BASELINE], n_seeds=3, n_jobs=1,
    )
    assert len(df) == len(INSTITUTIONS) * 3
    assert set(df["institution"].unique()) == set(INSTITUTIONS)


def test_republican_filters_extreme_bills_under_polarization():
    """Sanity: under polarized bills, republican should filter toward the median
    more than parliamentary (the Phase G second finding).

    We test with a small N and a modest margin to avoid flakiness.
    """
    df = run_representation_analysis(
        scenarios=[POLARIZED], n_seeds=50, n_jobs=-1,
    )
    parl_gap = df[(df["institution"] == "parliamentary")]["policy_representation_gap"].mean()
    rep_gap = df[(df["institution"] == "republican")]["policy_representation_gap"].mean()
    # Republican should filter (more negative gap) than parliamentary.
    assert rep_gap < parl_gap - 0.2, (
        f"Expected republican polarized gap << parliamentary; got rep={rep_gap}, parl={parl_gap}"
    )
