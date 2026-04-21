from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.aggregate import METRICS_TO_TEST, bootstrap_ci


plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "font.size": 10,
    }
)


def forest_plot_passage_delta(
    df_long: pd.DataFrame,
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """Per-scenario mean passage rate with 95% CI, for each institution."""
    scenarios = list(df_long["scenario"].unique())
    fig, ax = plt.subplots(figsize=(8, 1.0 + 0.9 * len(scenarios)))

    y_positions = np.arange(len(scenarios)) * 2.0

    for i, scenario in enumerate(scenarios):
        df_s = df_long[df_long["scenario"] == scenario]
        parl = df_s[df_s["institution"] == "parliamentary"]["passage_rate"].to_numpy()
        rep = df_s[df_s["institution"] == "republican"]["passage_rate"].to_numpy()

        parl_low, parl_high = bootstrap_ci(parl)
        rep_low, rep_high = bootstrap_ci(rep)

        ax.errorbar(
            parl.mean(),
            y_positions[i] + 0.3,
            xerr=[[parl.mean() - parl_low], [parl_high - parl.mean()]],
            fmt="o",
            color="C0",
            capsize=3,
            label="Parliamentary" if i == 0 else None,
        )
        ax.errorbar(
            rep.mean(),
            y_positions[i] - 0.3,
            xerr=[[rep.mean() - rep_low], [rep_high - rep.mean()]],
            fmt="s",
            color="C1",
            capsize=3,
            label="Republican" if i == 0 else None,
        )

    ax.set_yticks(y_positions)
    ax.set_yticklabels(scenarios)
    ax.set_xlim(-0.02, 1.02)
    ax.set_xlabel("Passage rate (mean, 95% bootstrap CI)")
    ax.set_title("Legislative passage rate by scenario and institution")
    ax.legend(loc="lower right")

    fig.tight_layout()
    if output_path is not None:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    return fig


def violin_plot_distributions(
    df_long: pd.DataFrame,
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """Violin plot of per-seed passage rate, faceted by scenario."""
    scenarios = list(df_long["scenario"].unique())
    fig, axes = plt.subplots(
        1, len(scenarios), figsize=(3.0 * len(scenarios), 4.0), sharey=True
    )
    if len(scenarios) == 1:
        axes = [axes]

    for ax, scenario in zip(axes, scenarios):
        parl = df_long[
            (df_long["scenario"] == scenario) & (df_long["institution"] == "parliamentary")
        ]["passage_rate"].to_numpy()
        rep = df_long[
            (df_long["scenario"] == scenario) & (df_long["institution"] == "republican")
        ]["passage_rate"].to_numpy()

        parts = ax.violinplot([parl, rep], showmeans=True, showmedians=True, widths=0.8)
        for idx, body in enumerate(parts["bodies"]):
            body.set_facecolor(["C0", "C1"][idx])
            body.set_alpha(0.7)

        ax.set_xticks([1, 2])
        ax.set_xticklabels(["Parl", "Rep"])
        ax.set_title(scenario)
        ax.set_ylim(-0.05, 1.05)

    axes[0].set_ylabel("Passage rate per seed")
    fig.suptitle("Distribution of passage rates across seeds")
    fig.tight_layout()
    if output_path is not None:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    return fig


def heatmap_metrics_by_scenario(
    summary_df: pd.DataFrame,
    metrics: Iterable[str] = METRICS_TO_TEST,
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """Heatmap of metric means by (scenario, institution)."""
    metric_list = list(metrics)
    subset = summary_df[summary_df["metric"].isin(metric_list)]
    pivot = subset.pivot(
        index="metric", columns=["scenario", "institution"], values="mean"
    )

    fig, ax = plt.subplots(
        figsize=(2.5 + 1.1 * len(pivot.columns), 1.0 + 0.5 * len(pivot.index))
    )
    values = pivot.values.astype(float)
    im = ax.imshow(values, aspect="auto", cmap="viridis")

    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(
        [f"{scen}\n{inst}" for scen, inst in pivot.columns],
        rotation=0,
        fontsize=8,
    )
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)

    midpoint = np.nanmean(values)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            val = values[i, j]
            if np.isnan(val):
                continue
            ax.text(
                j,
                i,
                f"{val:.2f}",
                ha="center",
                va="center",
                color="white" if val < midpoint else "black",
                fontsize=8,
            )

    fig.colorbar(im, ax=ax, label="mean")
    ax.set_title("Mean metric values by (scenario, institution)")
    fig.tight_layout()
    if output_path is not None:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    return fig


def render_all(
    df_long: pd.DataFrame,
    summary_df: pd.DataFrame,
    output_dir: Path,
) -> Tuple[Path, Path, Path]:
    """Render the three figures and return their paths."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    forest_path = output_dir / "forest_passage.png"
    violin_path = output_dir / "violin_passage.png"
    heatmap_path = output_dir / "heatmap_metrics.png"

    forest_plot_passage_delta(df_long, output_path=forest_path)
    violin_plot_distributions(df_long, output_path=violin_path)
    heatmap_metrics_by_scenario(summary_df, output_path=heatmap_path)

    plt.close("all")
    return forest_path, violin_path, heatmap_path
