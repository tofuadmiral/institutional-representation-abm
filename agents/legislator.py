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

    def decide_vote(self, bill) -> bool:
        """
        Returns True if the legislator supports the bill, False otherwise.
        Simple stub based on Euclidean distance to bill ideology.
        """
        dist = ((self.ideology[0] - bill.ideology[0])**2 +
                (self.ideology[1] - bill.ideology[1])**2)**0.5
        return dist < 1.0

    def evaluate_constituency_alignment(self) -> float:
        """
        Returns the ideological distance to the legislator's constituency.
        Requires the model to have `self.model.constituencies` dict.
        """
        constituency = self.model.constituencies[self.constituency_id]
        dist = ((self.ideology[0] - constituency.ideology[0])**2 +
                (self.ideology[1] - constituency.ideology[1])**2)**0.5
        return dist

    def record_vote(self, bill, vote) -> None:
        """
        Records the legislator's vote for a bill.
        Requires the model to have `self.model.votes` dict.
        """
        if not hasattr(bill, 'votes'):
            bill.votes = {}
        bill.votes[self.unique_id] = vote

    def __repr__(self):
        return f"Legislator(id={self.unique_id}, ideology={self.ideology}, constituency={self.constituency_id}, party={self.party_id})"


