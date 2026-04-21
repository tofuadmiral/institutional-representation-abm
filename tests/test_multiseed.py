from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.aggregate import _cohens_d, bootstrap_ci, pairwise_tests, summarize
from experiments.multiseed_comparison import run_multiseed_comparison
from experiments.scenarios import BASELINE


def test_bootstrap_ci_zero_variance_is_collapsed():
    low, high = bootstrap_ci(np.zeros(30))
    assert low == 0.0
    assert high == 0.0


def test_bootstrap_ci_contains_mean():
    rng = np.random.default_rng(0)
    values = rng.normal(loc=5.0, scale=1.0, size=200)
    low, high = bootstrap_ci(values)
    assert low < values.mean() < high
    assert high - low < 0.5  # should be tight for n=200


def test_cohens_d_for_known_distributions():
    a = np.array([1.0, 1.0, 1.0, 1.0])
    b = np.array([2.0, 2.0, 2.0, 2.0])
    # pooled variance is 0, a.mean() < b.mean(), so -inf
    d = _cohens_d(a, b)
    assert d == float("-inf")

    c = np.array([0.0, 1.0, 2.0, 3.0])
    d_val = _cohens_d(c, c)
    assert d_val == 0.0


def test_run_multiseed_comparison_smoke():
    df = run_multiseed_comparison(
        scenarios=[BASELINE],
        n_seeds=3,
        n_jobs=1,
    )
    assert len(df) == 3 * 2  # 3 seeds × 2 institutions
    assert set(df["institution"].unique()) == {"parliamentary", "republican"}
    assert set(df["seed"].unique()) == {0, 1, 2}
    assert (df["passage_rate"] >= 0).all()
    assert (df["passage_rate"] <= 1).all()


def test_run_multiseed_is_deterministic():
    df_a = run_multiseed_comparison(scenarios=[BASELINE], n_seeds=5, n_jobs=1)
    df_b = run_multiseed_comparison(scenarios=[BASELINE], n_seeds=5, n_jobs=1)
    pd.testing.assert_frame_equal(df_a, df_b)


def test_summarize_has_one_row_per_cell():
    df = run_multiseed_comparison(scenarios=[BASELINE], n_seeds=5, n_jobs=1)
    summary = summarize(df)
    # 2 institutions × len(METRICS_TO_TEST) metrics, but only metrics present in df
    assert len(summary) > 0
    tol = 1e-9
    for _, row in summary.iterrows():
        assert row["n"] == 5
        assert row["ci_low"] - tol <= row["mean"] <= row["ci_high"] + tol


def test_pairwise_tests_baseline_has_significant_passage_difference():
    df = run_multiseed_comparison(scenarios=[BASELINE], n_seeds=30, n_jobs=1)
    hyp = pairwise_tests(df)
    passage = hyp[(hyp["scenario"] == "baseline") & (hyp["metric"] == "passage_rate")]
    assert len(passage) == 1
    row = passage.iloc[0]
    # Parliamentary should beat republican at baseline with a large effect size
    assert row["mean_diff"] > 0.1
    assert abs(row["cohens_d"]) > 1.0
    assert row["welch_p"] < 0.01
