"""Draw the paper's enacted outcomes from the released offers and binding votes."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from reproduce import gpt_outcomes, qwen_games


def outcome_counts(agreements, harmful, total):
    return agreements - harmful, harmful, total - agreements


def panels():
    rules = gpt_outcomes()
    conflict = [r for r in rules if r["family"] == "conflict"]
    first = []
    for rule in ("majority", "unanimity"):
        branches = [r for r in conflict if r["rule"] == rule]
        agreements = sum(int(r["agreement"]) for r in branches)
        harmful = sum(int(r["harmful_exclusion"]) for r in branches)
        first.append((rule.capitalize(), outcome_counts(agreements, harmful, len(branches))))

    second = []
    for study, labels in (
        ("counts-and-reminder", ("Payoffs alone", "Payoffs + reminder + counts")),
        ("matched-reminder", ("Matched reminder", "Matched reminder + counts")),
    ):
        games = qwen_games(study)
        for arm, label in zip(("ordinary", "counts"), labels):
            branches = [r for r in games if r["arm"] == arm]
            enacted = [r for r in branches if r["implemented"] != r["fallback"]]
            harmful = sum(r["claimant_harmed_if_passed"] for r in enacted)
            second.append((label, outcome_counts(len(enacted), harmful, len(branches))))
    return first, second


def main():
    colors = ("#27665B", "#A64629", "#DFE5E7")
    plt.rcParams["pdf.fonttype"] = 42
    fig, axes = plt.subplots(2, 1, figsize=(6.45, 3.15), gridspec_kw={"height_ratios": [2, 4.35]})
    for ax, rows, positions, title in zip(
        axes, panels(), ([1, 0], [3.3, 2.3, 1, 0]),
        ("A   Voting rule in conflict games (GPT-4.1)", "B   Proposer display under unanimity (Qwen)"),
    ):
        ax.set_title(title, loc="left", fontsize=10, weight="bold", pad=4)
        for (_, counts), y in zip(rows, positions):
            left = 0
            for value, color in zip(counts, colors):
                width = 100 * value / sum(counts)
                if value:
                    ax.barh(y, width, height=.65, left=left, color=color)
                    small = width < 4
                    ax.text(
                        left + width + 1 if small else left + width/2, y,
                        str(value), ha="left" if small else "center", va="center",
                        fontsize=8, color="#243437" if small or color == colors[2] else "white",
                        zorder=4,
                    )
                left += width
        ax.set_xlim(0, 100)
        ax.set_ylim(-.55, max(positions) + .55)
        ax.set_yticks(positions, [label for label, _ in rows], fontsize=8)
        ax.tick_params(axis="y", length=0)
        ax.set_xticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

    labels = ("Mutual gain enacted", "Harmful agreement", "Fallback")
    fig.legend(
        handles=[Patch(color=c, label=l) for c, l in zip(colors, labels)],
        ncol=3, loc="lower center", frameon=False, fontsize=8,
    )
    fig.subplots_adjust(left=.32, right=.99, top=.90, bottom=.14, hspace=.64)
    fig.savefig(
        Path(__file__).with_name("bargaining-outcomes.pdf"),
        bbox_inches="tight", pad_inches=.04, metadata={"CreationDate": None, "ModDate": None},
    )


if __name__ == "__main__":
    main()
