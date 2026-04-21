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
    """Per-scenario mean passage rate with 95% CI, for every institution present."""
    scenarios = list(df_long["scenario"].unique())
    institutions = sorted(df_long["institution"].unique())
    n_inst = len(institutions)
    markers = ["o", "s", "^", "D", "v", "P"]
    colors = [f"C{i}" for i in range(n_inst)]
    spread = 0.3
    offsets = np.linspace(-spread, spread, n_inst) if n_inst > 1 else np.array([0.0])

    fig, ax = plt.subplots(figsize=(9, 1.2 + 0.85 * len(scenarios)))
    y_positions = np.arange(len(scenarios)) * 2.0

    for i, scenario in enumerate(scenarios):
        df_s = df_long[df_long["scenario"] == scenario]
        for j, inst in enumerate(institutions):
            values = df_s[df_s["institution"] == inst]["passage_rate"].to_numpy()
            if len(values) == 0:
                continue
            low, high = bootstrap_ci(values)
            ax.errorbar(
                values.mean(),
                y_positions[i] + offsets[j],
                xerr=[[values.mean() - low], [high - values.mean()]],
                fmt=markers[j % len(markers)],
                color=colors[j],
                capsize=3,
                label=inst if i == 0 else None,
            )

    ax.set_yticks(y_positions)
    ax.set_yticklabels(scenarios)
    ax.set_xlim(-0.02, 1.02)
    ax.set_xlabel("Passage rate (mean, 95% bootstrap CI)")
    ax.set_title("Legislative passage rate by scenario and institution")
    ax.legend(loc="lower right", fontsize=8)

    fig.tight_layout()
    if output_path is not None:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    return fig


SHORT_INSTITUTION_LABEL = {
    "parliamentary": "Parl",
    "republican": "Rep",
    "premier_presidential": "PremPres",
    "president_parliamentary": "PresParl",
}


def violin_plot_distributions(
    df_long: pd.DataFrame,
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """Violin plot of per-seed passage rate, faceted by scenario."""
    scenarios = list(df_long["scenario"].unique())
    institutions = sorted(df_long["institution"].unique())
    n_inst = len(institutions)
    fig, axes = plt.subplots(
        1, len(scenarios), figsize=(1.4 * n_inst * len(scenarios), 4.5), sharey=True
    )
    if len(scenarios) == 1:
        axes = [axes]

    for ax, scenario in zip(axes, scenarios):
        data = []
        for inst in institutions:
            values = df_long[
                (df_long["scenario"] == scenario) & (df_long["institution"] == inst)
            ]["passage_rate"].to_numpy()
            data.append(values)

        parts = ax.violinplot(data, showmeans=True, showmedians=True, widths=0.8)
        for idx, body in enumerate(parts["bodies"]):
            body.set_facecolor(f"C{idx}")
            body.set_alpha(0.7)

        ax.set_xticks(np.arange(1, n_inst + 1))
        ax.set_xticklabels(
            [SHORT_INSTITUTION_LABEL.get(i, i) for i in institutions],
            rotation=30, ha="right", fontsize=8,
        )
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
