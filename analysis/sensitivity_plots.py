"""Plots for Phase B: Morris mu*-sigma, Sobol indices, ablation deltas."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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


def morris_scatter(
    morris_df: pd.DataFrame,
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """Mu*-vs-sigma scatter: parameters high on both axes are the most influential
    and the most nonlinear/interacting."""
    institutions = sorted(morris_df["institution"].unique())
    fig, axes = plt.subplots(
        1, len(institutions), figsize=(5.0 * len(institutions), 4.5), squeeze=False,
    )

    for ax, inst in zip(axes[0], institutions):
        sub = morris_df[morris_df["institution"] == inst]
        ax.scatter(sub["mu_star"], sub["sigma"], s=80, c="C0", alpha=0.7)
        for _, row in sub.iterrows():
            ax.annotate(
                row["parameter"],
                xy=(row["mu_star"], row["sigma"]),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=8,
            )
        ax.set_xlabel(r"$\mu^*$  (mean absolute effect)")
        ax.set_ylabel(r"$\sigma$  (variability / interactions)")
        ax.set_title(f"Morris — {inst}")
        mu_min = min(0.0, sub["mu_star"].min())
        ax.set_xlim(left=mu_min - 0.02)
        ax.set_ylim(bottom=-0.02)

    fig.suptitle("Morris elementary-effects screening on passage rate")
    fig.tight_layout()
    if output_path is not None:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    return fig


def sobol_bars(
    sobol_df: pd.DataFrame,
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """First-order (S1) and total-order (ST) Sobol indices side by side per institution."""
    institutions = sorted(sobol_df["institution"].unique())
    fig, axes = plt.subplots(
        1, len(institutions), figsize=(6.0 * len(institutions), 4.5), squeeze=False,
    )

    for ax, inst in zip(axes[0], institutions):
        sub = sobol_df[sobol_df["institution"] == inst].reset_index(drop=True)
        y = np.arange(len(sub))
        width = 0.4
        ax.barh(
            y - width / 2, sub["ST"], height=width,
            xerr=sub["ST_conf"], color="C1", alpha=0.8, label="ST (total)", capsize=2,
        )
        ax.barh(
            y + width / 2, sub["S1"], height=width,
            xerr=sub["S1_conf"], color="C0", alpha=0.8, label="S1 (first-order)", capsize=2,
        )
        ax.axvline(0.0, color="grey", linewidth=0.6)
        ax.set_yticks(y)
        ax.set_yticklabels(sub["parameter"], fontsize=9)
        ax.invert_yaxis()
        ax.set_xlabel("Sobol index on passage_rate")
        ax.set_title(f"Sobol — {inst}")
        ax.legend(loc="lower right", fontsize=8)

    fig.suptitle("Sobol variance decomposition of passage rate")
    fig.tight_layout()
    if output_path is not None:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    return fig


def ablation_forest(
    deltas_df: pd.DataFrame,
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """Forest plot of Δ passage_rate when each mechanism is ablated."""
    non_baseline = deltas_df[deltas_df["ablation"] != "baseline"].copy()
    non_baseline = non_baseline.sort_values(["scenario", "institution", "ablation"])

    labels: List[str] = [
        f"{row['scenario']} · {row['institution']} · {row['ablation']}"
        for _, row in non_baseline.iterrows()
    ]
    deltas = non_baseline["delta_vs_baseline"].to_numpy()
    stds = non_baseline["std"].to_numpy()
    counts = non_baseline["count"].to_numpy()
    stderr = stds / np.sqrt(np.maximum(counts, 1))

    fig, ax = plt.subplots(figsize=(7.0, 0.35 * len(labels) + 1.5))
    y = np.arange(len(labels))
    colors = ["C0" if "parliamentary" in lbl else "C1" for lbl in labels]
    ax.errorbar(
        deltas, y, xerr=1.96 * stderr,
        fmt="o", capsize=3, ecolor="black",
        markerfacecolor="white", markeredgecolor="black",
    )
    for yi, d, c in zip(y, deltas, colors):
        ax.plot(d, yi, "o", color=c, markersize=7)

    ax.axvline(0, color="grey", linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel(r"$\Delta$ passage rate  (ablated − full model)")
    ax.set_title("Mechanism ablations: contribution of each mechanism to passage rate")
    fig.tight_layout()
    if output_path is not None:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    return fig


def render_all_phase_b(
    morris_df: pd.DataFrame,
    sobol_df: pd.DataFrame,
    deltas_df: pd.DataFrame,
    output_dir: Path,
) -> Tuple[Path, Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    morris_path = output_dir / "morris_scatter.png"
    sobol_path = output_dir / "sobol_bars.png"
    ablation_path = output_dir / "ablation_forest.png"
    morris_scatter(morris_df, morris_path)
    sobol_bars(sobol_df, sobol_path)
    ablation_forest(deltas_df, ablation_path)
    plt.close("all")
    return morris_path, sobol_path, ablation_path
