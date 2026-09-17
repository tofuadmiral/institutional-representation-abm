"""Seven-principal synthetic profiles for Paper 3's design-space checks."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

from paper3.institution import Mandate, Policy


class PreferenceRegime(str, Enum):
    FEASIBLE_COMPROMISE = "feasible_compromise"
    POLARIZED_BLOCS = "polarized_blocs"
    FRAGMENTED = "fragmented"
    PROTECTED_MINORITY = "protected_minority"


POLICIES = (
    Policy("status_quo", (0.0, 0.0)),
    Policy("broad_compromise", (0.0, 0.35)),
    Policy("left_package", (-0.8, 0.2)),
    Policy("right_package", (0.8, 0.2)),
    Policy("left_hard", (-1.0, -0.45)),
    Policy("right_hard", (1.0, -0.45)),
    Policy("minority_protection", (-0.55, 0.8)),
)


@dataclass(frozen=True)
class CoalitionScenario:
    scenario_id: str
    regime: PreferenceRegime
    mandates: tuple[Mandate, ...]
    policies: tuple[Policy, ...] = POLICIES
    status_quo_id: str = "status_quo"


def generate_scenario(*, seed: int, regime: PreferenceRegime) -> CoalitionScenario:
    """Generate matched seven-principal profiles with predeclared hard mandates."""
    rng = random.Random(seed)
    centers: list[tuple[float, float]]
    groups: list[str]
    limits: list[float]
    trade_budgets: list[float]
    weights: list[float]
    if regime is PreferenceRegime.FEASIBLE_COMPROMISE:
        centers = [(0.0, 0.35)] * 7
        groups, limits, weights, trade_budgets = ["broad"] * 7, [0.62] * 7, [1.0] * 7, [0.2] * 7
    elif regime is PreferenceRegime.POLARIZED_BLOCS:
        centers = [(-0.9, 0.1)] * 4 + [(0.9, 0.1)] * 3
        groups, limits, weights, trade_budgets = ["left"] * 4 + ["right"] * 3, [1.05] * 7, [1.0] * 7, [1.0] * 7
    elif regime is PreferenceRegime.FRAGMENTED:
        centers = [(-0.8, 0.2)] * 2 + [(0.0, 0.35)] * 3 + [(0.8, 0.2)] * 2
        groups, limits, weights, trade_budgets = ["left"] * 2 + ["center"] * 3 + ["right"] * 2, [0.95] * 7, [1.0] * 7, [0.85] * 7
    else:
        centers = [(-0.55, 0.8)] * 2 + [(0.25, 0.1)] * 5
        groups, limits, weights, trade_budgets = ["protected"] * 2 + ["majority"] * 5, [0.4] * 2 + [0.85] * 5, [2.0] * 2 + [1.0] * 5, [0.15] * 2 + [0.5] * 5
    order = list(range(7))
    rng.shuffle(order)
    mandates = []
    for representative_id, source in enumerate(order):
        x, y = centers[source]
        mandates.append(
            Mandate(
                principal_id=representative_id,
                ideal_point=(x + rng.uniform(-0.045, 0.045), y + rng.uniform(-0.045, 0.045)),
                hard_loss_limit=limits[source],
                weight=weights[source],
                group=groups[source],
                trade_loss_budget=trade_budgets[source],
            )
        )
    return CoalitionScenario(
        scenario_id=f"paper3-{regime.value}-{seed}", regime=regime, mandates=tuple(mandates)
    )
