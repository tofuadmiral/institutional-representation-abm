"""Exact descriptive benchmarks for the finite project menu.

These diagnostics were added after the first discovery run. They are not new
preregistered primary outcomes. The welfare optimum is a benchmark, not a claim
that utilitarian aggregation is the uniquely legitimate institutional objective.
"""

from __future__ import annotations

from itertools import product


def feasible_portfolios():
    return tuple(tuple(p for p in pair if p is not None)
                 for pair in product((None, "A0", "A1"), (None, "B0", "B1")))


def utility_vector(utilities, projects):
    return {str(actor): sum(row[project] for project in projects) for actor, row in utilities.items()}


def representation_metrics(utilities, selected_projects, passed_projects, signers):
    if set(passed_projects) - set(selected_projects):
        raise ValueError("passed project outside selected agenda")
    if tuple(selected_projects) not in feasible_portfolios() and tuple(reversed(selected_projects)) not in feasible_portfolios():
        raise ValueError("invalid selected agenda")
    all_vectors = [utility_vector(utilities, projects) for projects in feasible_portfolios()]
    actual = utility_vector(utilities, passed_projects)
    full = utility_vector(utilities, selected_projects)
    regrets = {}
    for actor in actual:
        lo, hi = min(v[actor] for v in all_vectors), max(v[actor] for v in all_vectors)
        regrets[actor] = (hi - actual[actor]) / (hi - lo) if hi > lo else 0.0
    myopic_passed = tuple(p for p in selected_projects if sum(row[p] > 0 for row in utilities.values()) >= 4)
    myopic = utility_vector(utilities, myopic_passed)
    best_total = max(sum(v.values()) for v in all_vectors)
    return dict(realized=actual, normalized_individual_regret=regrets,
                mean_normalized_regret=sum(regrets.values()) / len(regrets),
                actual_total=sum(actual.values()), utilitarian_menu_ceiling=best_total,
                utility_shortfall_from_menu_ceiling=best_total - sum(actual.values()),
                myopic_selected_agenda_projects=myopic_passed,
                myopic_selected_agenda_utility=myopic,
                actual_minus_myopic_total=sum(actual.values()) - sum(myopic.values()),
                loss_principals=[i for i, value in actual.items() if value < 0],
                negative_package_signers=[str(i) for i in signers if full[str(i)] < 0],
                signed_delivery_shortfall={str(i): full[str(i)] - actual[str(i)] for i in signers})
