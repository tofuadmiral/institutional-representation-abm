"""Plots for Phase F robustness checks."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "font.size": 10,
})

INSTITUTION_COLORS = {
    "parliamentary": "C0",
    "premier_presidential": "C2",
    "president_parliamentary": "C4",
    "republican": "C1",
}

INSTITUTION_LABELS = {
    "parliamentary": "Parliamentary",
    "premier_presidential": "Premier-Presidential",
    "president_parliamentary": "President-Parliamentary",
    "republican": "Republican",
}


def discipline_rescue_curves(
    rescue_df: pd.DataFrame,
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """One line per institution, x = common discipline level, y = rescue from zeroing discipline.

    Under fragmentation, the monotone ordering parl > premier > president-parl > rep
    should hold across the D grid if the Phase C claim is structural.
    """
    scenarios = sorted(rescue_df["scenario"].unique())
    fig, axes = plt.subplots(1, len(scenarios), figsize=(6.0 * len(scenarios), 4.5), squeeze=False)

    for ax, scenario in zip(axes[0], scenarios):
        sub = rescue_df[rescue_df["scenario"] == scenario]
        sub = sub[sub["discipline_strength"] > 0]  # D=0 has rescue=0 by definition
        for inst, g in sub.groupby("institution"):
            g = g.sort_values("discipline_strength")
            ax.plot(
                g["discipline_strength"], g["rescue_vs_zero"],
                marker="o", color=INSTITUTION_COLORS.get(inst, "grey"),
                label=INSTITUTION_LABELS.get(inst, inst),
            )
        ax.axhline(0, color="grey", linewidth=0.6)
        ax.set_xlabel("Common discipline level D (applied to all institutions)")
        ax.set_ylabel(r"Rescue $\Delta$ = passage(D=0) − passage(D)")
        ax.set_title(f"Scenario: {scenario}")
        ax.legend(loc="best", fontsize=8)

    fig.suptitle(
        "Discipline-default robustness: rescue magnitude across a common D grid",
    )
    fig.tight_layout()
    if output_path is not None:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    return fig


def render_phase_f_plots(
    rescue_df: pd.DataFrame,
    output_dir: Path,
) -> Tuple[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    curves_path = output_dir / "discipline_rescue_curves.png"
    discipline_rescue_curves(rescue_df, curves_path)
    plt.close("all")
    return (curves_path,)
