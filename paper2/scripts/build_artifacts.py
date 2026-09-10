"""Build Paper 2 figures and LaTeX tables from the frozen CSV snapshot."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
TABLES = ROOT / "tables"

MODEL_LABELS = {
    "mlx-community/Qwen3-8B-4bit": "Qwen3-8B",
    "mlx-community/Mistral-Small-24B-Instruct-2501-4bit": "Mistral-Small-24B",
}
STATE_LABELS = {
    "oracle_correct": "Correct",
    "aggregate_pressure_violation": "Violation",
    "compliant_suboptimal": "Compliant, suboptimal",
}
INSTITUTION_LABELS = {
    "no_review": "No review",
    "broad_override": "Broad override",
    "certificate_gate": "Evidence gate",
}


def pct(value: float, digits: int = 1) -> str:
    return f"{100 * value:.{digits}f}"


def tex_escape(value: object) -> str:
    return str(value).replace("_", r"\_").replace("%", r"\%")


def read(name: str, filename: str) -> pd.DataFrame:
    return pd.read_csv(DATA / name / filename)


def state_effects() -> pd.DataFrame:
    spatial = pd.concat(
        [
            read(
                "multi_eligible_certificate_gate_qwen3_8b_n96",
                "certificate_gate_effects.csv",
            ).assign(model="mlx-community/Qwen3-8B-4bit"),
            read(
                "multi_eligible_certificate_gate_mistral_24b_n96",
                "certificate_gate_effects.csv",
            ).assign(
                model="mlx-community/Mistral-Small-24B-Instruct-2501-4bit"
            ),
        ],
        ignore_index=True,
    ).assign(domain="Spatial policy")
    portfolio = pd.concat(
        [
            read(
                "portfolio_certificate_gate_qwen3_8b_n96",
                "portfolio_gate_effects.csv",
            ).assign(model="mlx-community/Qwen3-8B-4bit"),
            read(
                "portfolio_certificate_gate_mistral_24b_n96",
                "portfolio_gate_effects.csv",
            ).assign(
                model="mlx-community/Mistral-Small-24B-Instruct-2501-4bit"
            ),
        ],
        ignore_index=True,
    ).assign(domain="Portfolio approval")
    combined = pd.concat([spatial, portfolio], ignore_index=True)
    combined = combined[
        (combined["metric"] == "protected_oracle_match")
        & (combined["scope"] != "all")
    ].copy().rename(columns={"scope": "proposal_state"})
    combined["model_label"] = combined["model"].map(MODEL_LABELS)
    combined["state_label"] = combined["proposal_state"].map(STATE_LABELS)
    return combined


def build_state_effect_figure() -> None:
    data = state_effects()
    domains = ["Spatial policy", "Portfolio approval"]
    models = ["Qwen3-8B", "Mistral-Small-24B"]
    states = ["Correct", "Violation", "Compliant, suboptimal"]
    colors = ["#2c7fb8", "#7fcdbb", "#f03b20"]
    fig, axes = plt.subplots(2, 2, figsize=(10.2, 6.7), sharey=True)
    for row, domain in enumerate(domains):
        for col, model in enumerate(models):
            ax = axes[row, col]
            scoped = data[
                (data["domain"] == domain) & (data["model_label"] == model)
            ]
            values = [
                float(scoped.loc[scoped["state_label"] == state, "effect"].iloc[0])
                for state in states
            ]
            bars = ax.bar(np.arange(3), np.multiply(values, 100), color=colors)
            ax.axhline(0, color="#333333", linewidth=0.8)
            ax.set_title(f"{domain} — {model}", fontsize=10)
            ax.set_xticks(np.arange(3), ["Correct", "Violation", "Compliant\nsuboptimal"])
            ax.grid(axis="y", color="#dddddd", linewidth=0.6)
            ax.set_axisbelow(True)
            for bar, value in zip(bars, values, strict=True):
                offset = 3.0 if value >= 0 else -3.5
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    100 * value + offset,
                    f"{100 * value:+.1f}",
                    ha="center",
                    va="center",
                    fontsize=8,
                )
    axes[0, 0].set_ylabel("Evidence gate − broad override (pp)")
    axes[1, 0].set_ylabel("Evidence gate − broad override (pp)")
    fig.suptitle("Exact-optimality effect depends on the proposal state", y=0.995)
    fig.tight_layout()
    for suffix in ("pdf", "png"):
        fig.savefig(FIGURES / f"state_conditional_effects.{suffix}", dpi=220)
    plt.close(fig)


def build_natural_figure() -> None:
    rows = []
    for directory in (
        "natural_proposer_qwen3_8b_n96",
        "natural_proposer_mistral_24b_n96",
    ):
        outcomes = read(directory, "natural_outcomes.csv")
        for (model, institution), group in outcomes.groupby(["model", "institution"]):
            rows.append(
                {
                    "model": MODEL_LABELS[model],
                    "institution": INSTITUTION_LABELS.get(institution, institution),
                    "exact": group["protected_oracle_match"].mean(),
                    "compliant": group["constraint_followed"].mean(),
                }
            )
    data = pd.DataFrame(rows)
    order = ["No review", "Broad override", "Evidence gate"]
    colors = {"No review": "#969696", "Broad override": "#f03b20", "Evidence gate": "#2c7fb8"}
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.7), sharey=True)
    for ax, model in zip(axes, ["Qwen3-8B", "Mistral-Small-24B"], strict=True):
        scoped = data[data["model"] == model].set_index("institution").loc[order]
        x = np.arange(2)
        width = 0.23
        for index, institution in enumerate(order):
            values = 100 * scoped.loc[institution, ["exact", "compliant"]].to_numpy(dtype=float)
            ax.bar(x + (index - 1) * width, values, width, label=institution, color=colors[institution])
        ax.set_xticks(x, ["Exact optimum", "Binding compliance"])
        ax.set_title(model)
        ax.set_ylim(0, 105)
        ax.grid(axis="y", color="#dddddd", linewidth=0.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Rate (%)")
    axes[1].legend(frameon=False, loc="lower right")
    fig.suptitle("Outcomes with naturally generated spatial proposals", y=0.99)
    fig.tight_layout()
    for suffix in ("pdf", "png"):
        fig.savefig(FIGURES / f"natural_proposal_outcomes.{suffix}", dpi=220)
    plt.close(fig)


def build_frontier_figure() -> None:
    conditional = state_effects()
    rows = []
    for (domain, model), scoped in conditional.groupby(["domain", "model_label"]):
        effects = scoped.set_index("state_label")["effect"].to_dict()
        for correct_pct in range(101):
            for violation_pct in range(101 - correct_pct):
                suboptimal_pct = 100 - correct_pct - violation_pct
                rows.append(
                    {
                        "domain": domain,
                        "model_label": model,
                        "correct_prevalence": correct_pct / 100,
                        "violation_prevalence": violation_pct / 100,
                        "expected_gate_minus_broad": (
                            correct_pct * effects["Correct"]
                            + violation_pct * effects["Violation"]
                            + suboptimal_pct * effects["Compliant, suboptimal"]
                        )
                        / 100,
                    }
                )
    data = pd.DataFrame(rows)
    fig, axes = plt.subplots(2, 2, figsize=(9.8, 7.6), sharex=True, sharey=True)
    levels = np.linspace(-0.9, 0.9, 19)
    last = None
    for row, domain in enumerate(["Spatial policy", "Portfolio approval"]):
        for col, model in enumerate(["Qwen3-8B", "Mistral-Small-24B"]):
            ax = axes[row, col]
            scoped = data[(data["domain"] == domain) & (data["model_label"] == model)]
            x = scoped["correct_prevalence"].to_numpy()
            y = scoped["violation_prevalence"].to_numpy()
            z = scoped["expected_gate_minus_broad"].to_numpy()
            last = ax.tricontourf(x, y, z, levels=levels, cmap="RdBu", extend="both")
            ax.tricontour(x, y, z, levels=[0], colors="black", linewidths=1.2)
            ax.plot([0, 1], [1, 0], color="#555555", linewidth=0.7)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_title(f"{domain} — {model}", fontsize=10)
            if col == 0:
                ax.set_ylabel("Violation prevalence")
            if row == 1:
                ax.set_xlabel("Correct-proposal prevalence")
    if last is not None:
        colorbar_axis = fig.add_axes([0.88, 0.18, 0.025, 0.64])
        colorbar = fig.colorbar(last, cax=colorbar_axis)
        colorbar.set_label("Expected exact-rate effect (gate − broad)")
    fig.suptitle("The preferred jurisdiction depends on upstream proposal states", y=0.98)
    fig.subplots_adjust(left=0.09, right=0.83, bottom=0.09, top=0.92, wspace=0.16, hspace=0.22)
    for suffix in ("pdf", "png"):
        fig.savefig(FIGURES / f"prevalence_frontiers.{suffix}", dpi=220)
    plt.close(fig)


def build_main_results_table() -> None:
    data = state_effects()
    rows = []
    for domain in ("Spatial policy", "Portfolio approval"):
        for model in ("Qwen3-8B", "Mistral-Small-24B"):
            scoped = data[(data["domain"] == domain) & (data["model_label"] == model)]
            values = {
                row.state_label: row.effect for row in scoped.itertuples(index=False)
            }
            rows.append(
                (
                    domain,
                    model,
                    pct(values["Correct"]),
                    pct(values["Violation"]),
                    pct(values["Compliant, suboptimal"]),
                )
            )
    lines = [
        r"\begin{tabular}{llrrr}",
        r"\toprule",
        r"Domain & Model & Correct & Violation & Compliant suboptimal \\",
        r"\midrule",
    ]
    for domain, model, correct, violation, suboptimal in rows:
        lines.append(
            f"{tex_escape(domain)} & {tex_escape(model)} & {correct} & {violation} & {suboptimal} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    (TABLES / "state_effects.tex").write_text("\n".join(lines) + "\n")


def build_natural_table() -> None:
    states = read(
        "paper_validations_cross_model", "natural_state_frequencies.csv"
    )
    states = states[(states["scenario"] == "all") & (states["scope"] != "pooled_models")]
    effects = read("paper_validations_cross_model", "natural_gate_effects.csv")
    effects = effects[effects["scope"] == "all"]
    rows = []
    for model_id, model_label in MODEL_LABELS.items():
        scoped_states = states[states["scope"] == model_id].set_index("proposal_state")
        scoped_effects = effects[effects["model"] == model_id].set_index("metric")
        rows.append(
            (
                model_label,
                int(scoped_states.loc["oracle_correct", "count"]),
                int(scoped_states.loc["protected_violation", "count"]),
                int(scoped_states.loc["compliant_suboptimal", "count"]),
                pct(scoped_effects.loc["protected_oracle_match", "effect"]),
                pct(scoped_effects.loc["constraint_followed", "effect"]),
            )
        )
    lines = [
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Model & Correct & Violation & Suboptimal & Exact $\Delta$ & Compliance $\Delta$ \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            f"{tex_escape(row[0])} & {row[1]} & {row[2]} & {row[3]} & {row[4]} & {row[5]} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    (TABLES / "natural_results.tex").write_text("\n".join(lines) + "\n")


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    build_state_effect_figure()
    build_natural_figure()
    build_frontier_figure()
    build_main_results_table()
    build_natural_table()
    print(f"Wrote figures to {FIGURES} and tables to {TABLES}")


if __name__ == "__main__":
    main()
