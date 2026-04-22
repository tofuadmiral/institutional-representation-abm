"""Plots for the institutional-representation tradeoff (Phase G)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "font.size": 10,
})

INSTITUTION_ORDER = (
    "parliamentary", "premier_presidential", "president_parliamentary", "republican",
)
INSTITUTION_COLORS = {
    "parliamentary": "C0",
    "premier_presidential": "C2",
    "president_parliamentary": "C4",
    "republican": "C1",
}


def tradeoff_scatter(
    df: pd.DataFrame,
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """Passage rate vs. policy_representation_gap, one point per
    (institution, scenario) with per-seed cloud."""
    fig, axes = plt.subplots(
        1, 4, figsize=(16, 4.5), sharey=True,
    )
    scenarios = ["baseline", "fragmented", "polarized", "small_system"]

    for ax, scenario in zip(axes, scenarios):
        sub = df[df["scenario"] == scenario]
        for inst in INSTITUTION_ORDER:
            s = sub[sub["institution"] == inst]
            if len(s) == 0:
                continue
            ax.scatter(
                s["passage_rate"], s["policy_representation_gap"],
                color=INSTITUTION_COLORS.get(inst, "grey"),
                alpha=0.15, s=10,
            )
            ax.scatter(
                s["passage_rate"].mean(), s["policy_representation_gap"].mean(),
                color=INSTITUTION_COLORS.get(inst, "grey"),
                s=120, edgecolor="black", linewidth=1.2,
                label=inst.replace("_", " "),
            )
        ax.axhline(0, color="grey", linewidth=0.5, linestyle="--")
        ax.set_xlim(-0.05, 1.05)
        ax.set_xlabel("Passage rate")
        ax.set_title(scenario)

    axes[0].set_ylabel(r"Policy representation gap" "\n"
                       r"$\bar d_{\mathrm{passed}} - \bar d_{\mathrm{proposed}}$")
    axes[-1].legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    fig.suptitle(
        "Passage rate vs. representation quality — the institutional tradeoff",
    )
    fig.tight_layout()
    if output_path is not None:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    return fig
