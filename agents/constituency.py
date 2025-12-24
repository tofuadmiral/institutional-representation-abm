from __future__ import annotations

from typing import Tuple

from mesa import Agent, Model


class ConstituencyAgent(Agent):
    """
    Agent representing a geographic or social constituency.

    Constituencies provide stable preferences that legislators are meant to
    represent, enabling comparisons of institutional mediation of representation.
    """

    def __init__(
        self,
        unique_id: int,
        model: Model,
        ideology: Tuple[float, float],
        population: int,
    ) -> None:
        super().__init__(unique_id, model)
        self.ideology: Tuple[float, float] = ideology
        self.population: int = population

    def step(self) -> None:
        """
        Placeholder behavior for a single simulation step.

        Later extensions may allow constituencies to update preferences or
        evaluate their representatives; for now they are static preference holders.
        """
        # Deliberate no-op: constituencies remain static in the baseline model.
        return


