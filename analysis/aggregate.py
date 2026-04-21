from __future__ import annotations

from typing import Iterable, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats


METRICS_TO_TEST: Tuple[str, ...] = (
    "passage_rate",
    "bills_vetoed",
    "gridlock_events",
    "committee_kill_rate",
    "committee_amendment_rate",
    "avg_representation_distance",
)


def bootstrap_ci(
    values: np.ndarray,
    confidence: float = 0.95,
    n_resamples: int = 9999,
    random_state: Optional[int] = 0,
) -> Tuple[float, float]:
    """
    Percentile bootstrap CI for the mean of `values`.

    Returns (low, high). For zero-variance inputs the CI collapses to (mean, mean):
    that is a legitimate finding (e.g. fragmented-parliamentary passage = 0 every seed),
    not a bug.
    """
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return float("nan"), float("nan")
    if np.all(values == values[0]):
        return float(values[0]), float(values[0])
    result = stats.bootstrap(
        (values,),
        np.mean,
        confidence_level=confidence,
        n_resamples=n_resamples,
        method="percentile",
        random_state=random_state,
    )
    return float(result.confidence_interval.low), float(result.confidence_interval.high)


def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return float("nan")
    pooled_var = ((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2)
    if pooled_var == 0:
        if a.mean() == b.mean():
            return 0.0
        return float("inf") if a.mean() > b.mean() else float("-inf")
    return (a.mean() - b.mean()) / pooled_var ** 0.5


def summarize(
    df_long: pd.DataFrame,
    metrics: Iterable[str] = METRICS_TO_TEST,
) -> pd.DataFrame:
    """
    Collapse a long-form (scenario, institution, seed) dataframe into a summary
    with bootstrap 95% CIs per (scenario, institution, metric).
    """
    rows = []
    metric_list = list(metrics)
    for (scenario, institution), df_group in df_long.groupby(["scenario", "institution"], sort=False):
        n = len(df_group)
        for metric in metric_list:
            if metric not in df_group.columns:
                continue
            values = df_group[metric].to_numpy(dtype=float)
            low, high = bootstrap_ci(values)
            rows.append(
                {
                    "scenario": scenario,
                    "institution": institution,
                    "metric": metric,
                    "n": n,
                    "mean": float(values.mean()),
                    "std": float(values.std(ddof=1)) if n > 1 else 0.0,
                    "ci_low": low,
                    "ci_high": high,
                }
            )
    return pd.DataFrame(rows)


def pairwise_tests(
    df_long: pd.DataFrame,
    metrics: Iterable[str] = METRICS_TO_TEST,
    institution_a: str = "parliamentary",
    institution_b: str = "republican",
) -> pd.DataFrame:
    """
    For each (scenario, metric), compare `institution_a` against `institution_b` with
    Welch's t, Mann-Whitney U, and Cohen's d.

    NaNs in p-values indicate zero-variance inputs (e.g. every seed produced the
    same value). That is recorded faithfully rather than fudged.
    """
    rows = []
    metric_list = list(metrics)
    for scenario, df_scenario in df_long.groupby("scenario", sort=False):
        group_a = df_scenario[df_scenario["institution"] == institution_a]
        group_b = df_scenario[df_scenario["institution"] == institution_b]
        for metric in metric_list:
            if metric not in df_scenario.columns:
                continue
            values_a = group_a[metric].to_numpy(dtype=float)
            values_b = group_b[metric].to_numpy(dtype=float)

            welch_t = float("nan")
            welch_p = float("nan")
            mwu_stat = float("nan")
            mwu_p = float("nan")

            if len(values_a) >= 2 and len(values_b) >= 2:
                var_a = float(np.var(values_a, ddof=1))
                var_b = float(np.var(values_b, ddof=1))
                if var_a > 0 or var_b > 0:
                    welch = stats.ttest_ind(values_a, values_b, equal_var=False)
                    welch_t = float(welch.statistic)
                    welch_p = float(welch.pvalue)
                    mwu = stats.mannwhitneyu(values_a, values_b, alternative="two-sided")
                    mwu_stat = float(mwu.statistic)
                    mwu_p = float(mwu.pvalue)

            rows.append(
                {
                    "scenario": scenario,
                    "metric": metric,
                    "institution_a": institution_a,
                    "institution_b": institution_b,
                    "n_a": len(values_a),
                    "n_b": len(values_b),
                    "mean_a": float(values_a.mean()) if len(values_a) else float("nan"),
                    "mean_b": float(values_b.mean()) if len(values_b) else float("nan"),
                    "mean_diff": (
                        float(values_a.mean() - values_b.mean())
                        if len(values_a) and len(values_b)
                        else float("nan")
                    ),
                    "welch_t": welch_t,
                    "welch_p": welch_p,
                    "mwu_stat": mwu_stat,
                    "mwu_p": mwu_p,
                    "cohens_d": _cohens_d(values_a, values_b),
                }
            )
    return pd.DataFrame(rows)
