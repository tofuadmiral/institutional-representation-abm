from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ComparisonScenario:
    """Defines a scenario for institutional comparison."""
    name: str
    description: str
    num_legislators: int
    num_constituencies: int
    num_parties: int
    num_bills: int
    bill_ideology_range: Tuple[float, float]


BASELINE = ComparisonScenario(
    name="baseline",
    description="Standard balanced scenario",
    num_legislators=20,
    num_constituencies=6,
    num_parties=3,
    num_bills=25,
    bill_ideology_range=(-1.0, 1.0),
)

FRAGMENTED = ComparisonScenario(
    name="fragmented",
    description="Many parties, coalition politics",
    num_legislators=24,
    num_constituencies=8,
    num_parties=5,
    num_bills=30,
    bill_ideology_range=(-1.0, 1.0),
)

POLARIZED = ComparisonScenario(
    name="polarized",
    description="Extreme bills, testing system limits",
    num_legislators=16,
    num_constituencies=4,
    num_parties=2,
    num_bills=20,
    bill_ideology_range=(-1.5, 1.5),
)

SMALL_SYSTEM = ComparisonScenario(
    name="small_system",
    description="Minimal viable system",
    num_legislators=10,
    num_constituencies=3,
    num_parties=2,
    num_bills=15,
    bill_ideology_range=(-0.8, 0.8),
)


DEFAULT_SCENARIOS = (BASELINE, FRAGMENTED, POLARIZED, SMALL_SYSTEM)


SCENARIOS_BY_NAME = {s.name: s for s in DEFAULT_SCENARIOS}
