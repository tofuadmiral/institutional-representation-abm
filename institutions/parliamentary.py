from __future__ import annotations

from typing import Optional

from institutions.base import BaseInstitutionModel


class ParliamentaryModel(BaseInstitutionModel):
    """
    Placeholder model for a parliamentary system.

    This subclass shares agents and metrics with other institutional variants
    but will later encode parliament-specific agenda and government formation
    rules without changing the underlying population.
    """

    def __init__(
        self,
        num_legislators: int = 10,
        num_constituencies: int = 5,
        num_parties: int = 2,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__(
            num_legislators=num_legislators,
            num_constituencies=num_constituencies,
            num_parties=num_parties,
            seed=seed,
        )

    def step(self) -> None:
        """
        Advance the parliamentary model by one step.

        Institutional details (e.g., confidence votes, cabinet structure) will
        later be inserted here while keeping the base stepping logic intact.
        """
        super().step()


