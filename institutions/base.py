from __future__ import annotations

from typing import Optional, Tuple

from mesa import Model
from mesa.time import RandomActivation

from agents.constituency import ConstituencyAgent
from agents.legislator import LegislatorAgent
from agents.party import PartyAgent
from config import LegislatorConfig
from metrics.collectors import build_default_datacollector


class BaseInstitutionModel(Model):
    """
    Base Mesa model for comparing institutional rules of representation.

    This class wires together the scheduler, core agent types, and data
    collection in a way that is shared across institutional variants.
    """

    def __init__(
        self,
        num_legislators: int = 10,
        num_constituencies: int = 5,
        num_parties: int = 2,
        legislator_config: Optional[LegislatorConfig] = None,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__(seed=seed)

        # Expose population sizes as explicit state for downstream analysis.
        self.num_legislators: int = num_legislators
        self.num_constituencies: int = num_constituencies
        self.num_parties: int = num_parties

        # Legislator-level config is read by LegislatorAgent.decide_vote.
        self.legislator_config: LegislatorConfig = legislator_config or LegislatorConfig()

        # Core Mesa components.
        self.schedule: RandomActivation = RandomActivation(self)
        self.datacollector = build_default_datacollector()

        # Agent creation is deliberately simple and reproducible.
        self._create_constituencies()
        self._create_parties()
        self._create_legislators()

    def _default_ideology(self, index: int, total: int) -> Tuple[float, float]:
        """
        Simple deterministic ideology assignment on a 2D line.

        This keeps agents biased but comparable across institutional variants.
        """
        position = -1.0 + 2.0 * (index / max(1, total - 1)) if total > 1 else 0.0
        return position, position

    def _create_constituencies(self) -> None:
        for i in range(self.num_constituencies):
            ideology = self._default_ideology(i, self.num_constituencies)
            constituency = ConstituencyAgent(
                unique_id=self.next_id(),
                model=self,
                ideology=ideology,
                population=1000,
            )
            self.schedule.add(constituency)

    def _create_parties(self) -> None:
        for i in range(self.num_parties):
            ideology = self._default_ideology(i, self.num_parties)
            party = PartyAgent(
                unique_id=self.next_id(),
                model=self,
                ideology=ideology,
                name=f"Party_{i}",
            )
            self.schedule.add(party)

    def _create_legislators(self) -> None:
        for i in range(self.num_legislators):
            ideology = self._default_ideology(i, self.num_legislators)
            constituency_id = i % self.num_constituencies
            party_id = i % self.num_parties if self.num_parties > 0 else None
            legislator = LegislatorAgent(
                unique_id=self.next_id(),
                model=self,
                ideology=ideology,
                constituency_id=constituency_id,
                party_id=party_id,
            )
            self.schedule.add(legislator)

    @property 
    def legislators(self):
        """Get all legislator agents."""
        return [agent for agent in self.schedule.agents if hasattr(agent, 'ideology') and hasattr(agent, 'party_id')]
    
    @property
    def constituencies(self):
        """Get all constituency agents mapped by ID."""
        constituency_dict = {}
        for agent in self.schedule.agents:
            if hasattr(agent, 'population'):  # ConstituencyAgent has population
                constituency_dict[agent.unique_id] = agent
        return constituency_dict
    
    @property
    def parties(self):
        """Get all party agents mapped by ID."""
        party_dict = {}
        for agent in self.schedule.agents:
            if hasattr(agent, 'name') and not hasattr(agent, 'population'):  # PartyAgent has name but not population
                party_dict[agent.unique_id] = agent
        return party_dict

    def step(self) -> None:
        """
        Advance the model by one step.

        Institutional subclasses may extend this method but should preserve
        the basic ordering of data collection and agent activation.
        """
        self.datacollector.collect(self)
        self.schedule.step()


