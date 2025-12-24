from __future__ import annotations

from typing import Tuple

from mesa import Agent, Model


class PartyAgent(Agent):
    """
    Agent representing a political party organization.

    Parties aggregate legislators and policy positions but, in this baseline
    implementation, do not yet enforce discipline or coordinate behavior.
    """

    def __init__(
        self,
        unique_id: int,
        model: Model,
        ideology: Tuple[float, float],
        name: str,
    ) -> None:
        super().__init__(unique_id, model)
        self.ideology: Tuple[float, float] = ideology
        self.name: str = name

    def step(self) -> None:
        """
        Placeholder behavior for a single simulation step.

        Future institutional comparisons can introduce party-level strategies
        without changing the basic agent interface.
        """
        # Deliberate no-op: party behavior is not modeled in the baseline.
        return


