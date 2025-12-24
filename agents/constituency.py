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

    def evaluate_bill(self, bill) -> float:
        """
        Returns a utility score for the bill based on the constituency's ideological proximity.
        Higher scores indicate stronger alignment (1 = perfect match, 0 = worst match).
        """
        dist = ((self.ideology[0] - bill.ideology[0])**2 +
                (self.ideology[1] - bill.ideology[1])**2)**0.5
        score = max(0.0, 1.0 - dist)  # Clamp to [0,1]
        return score

    def __repr__(self):
        return f"Constituency(id={self.unique_id}, ideology={self.ideology}, population={self.population})"


