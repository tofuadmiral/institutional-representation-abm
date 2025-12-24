from __future__ import annotations

from typing import Optional, Tuple

from mesa import Agent, Model


class LegislatorAgent(Agent):
    """
    Agent representing an individual legislator.

    This class intentionally keeps behavior minimal while exposing the core
    state used in institutional comparisons (ideology, party, and constituency).
    """

    def __init__(
        self,
        unique_id: int,
        model: Model,
        ideology: Tuple[float, float],
        constituency_id: int,
        party_id: Optional[int] = None,
    ) -> None:
        super().__init__(unique_id, model)
        self.ideology: Tuple[float, float] = ideology
        self.constituency_id: int = constituency_id
        self.party_id: Optional[int] = party_id

    def step(self) -> None:
        """
        Placeholder behavior for a single simulation step.

        Institutional logic (e.g., agenda setting, voting rules) will later
        determine how legislators act; for now they simply exist in the system.
        """
        # Deliberate no-op: behavior will be defined by institutional rules.
        return


