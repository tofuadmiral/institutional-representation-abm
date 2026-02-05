from __future__ import annotations

from typing import Optional, List, Dict, Any
import random

from institutions.base import BaseInstitutionModel
from agents.legislator import LegislatorAgent
from agents.party import PartyAgent
from bills.bill import Bill


class ParliamentaryModel(BaseInstitutionModel):
    """
    Parliamentary system with government formation, confidence votes, and party discipline.

    Key Features:
    - Government formation based on parliamentary majority
    - Confidence votes that can trigger government collapse
    - Strong party discipline in voting
    - Coalition building mechanics
    - Prime Minister selection from largest party
    """

    def __init__(
        self,
        num_legislators: int = 10,
        num_constituencies: int = 5,
        num_parties: int = 2,
        confidence_threshold: float = 0.5,
        discipline_strength: float = 0.8,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__(
            num_legislators=num_legislators,
            num_constituencies=num_constituencies,
            num_parties=num_parties,
            seed=seed,
        )
        
        # Parliamentary-specific parameters
        self.confidence_threshold = confidence_threshold  # Fraction needed for confidence
        self.discipline_strength = discipline_strength    # Party discipline strength (0-1)
        
        # Government state
        self.government_party = None
        self.prime_minister = None
        self.government_coalition = []
        self.government_formed = False
        self.confidence_votes_passed = 0
        self.confidence_votes_failed = 0
        
        # Form initial government
        self._form_government()

    def _form_government(self) -> None:
        """
        Form government based on party seat distribution.
        
        In parliamentary systems, the party (or coalition) that can command
        a majority in parliament forms the government.
        """
        # Count legislators per party
        party_seats = {}
        party_legislators = {}
        
        for agent in self.schedule.agents:
            if isinstance(agent, LegislatorAgent):
                party_id = agent.party_id
                if party_id is not None:
                    party_seats[party_id] = party_seats.get(party_id, 0) + 1
                    if party_id not in party_legislators:
                        party_legislators[party_id] = []
                    party_legislators[party_id].append(agent)
        
        # Find largest party
        if party_seats:
            largest_party = max(party_seats.keys(), key=lambda k: party_seats[k])
            largest_party_seats = party_seats[largest_party]
            
            # Check if largest party has majority
            total_seats = sum(party_seats.values())
            majority_threshold = int(total_seats * self.confidence_threshold) + 1
            
            if largest_party_seats >= majority_threshold:
                # Single party government
                self.government_party = largest_party
                self.government_coalition = [largest_party]
            else:
                # Need coalition - simplified: largest party + next largest
                other_parties = [(k, v) for k, v in party_seats.items() if k != largest_party]
                if other_parties:
                    second_largest = max(other_parties, key=lambda x: x[1])[0]
                    coalition_seats = largest_party_seats + party_seats[second_largest]
                    
                    if coalition_seats >= majority_threshold:
                        self.government_party = largest_party  # Lead party
                        self.government_coalition = [largest_party, second_largest]
            
            # Select Prime Minister from government party
            if self.government_party is not None and self.government_party in party_legislators:
                government_mps = party_legislators[self.government_party]
                if government_mps:
                    self.prime_minister = self.random.choice(government_mps)
                
            self.government_formed = True

    def _conduct_confidence_vote(self, bill: Bill) -> bool:
        """
        Conduct a confidence vote on a bill.
        
        In parliamentary systems, certain key votes are matters of confidence.
        If the government loses, it may fall.
        """
        votes_for = 0
        votes_against = 0
        
        for agent in self.schedule.agents:
            if isinstance(agent, LegislatorAgent):
                vote = self._get_disciplined_vote(agent, bill)
                if vote:
                    votes_for += 1
                else:
                    votes_against += 1
        
        # Government survives if it gets enough support
        total_votes = votes_for + votes_against
        confidence_passed = votes_for / total_votes >= self.confidence_threshold
        
        if confidence_passed:
            self.confidence_votes_passed += 1
        else:
            self.confidence_votes_failed += 1
            # Government falls - trigger new government formation
            self._government_falls()
            
        return confidence_passed

    def _get_disciplined_vote(self, legislator: LegislatorAgent, bill: Bill) -> bool:
        """
        Get legislator's vote with party discipline applied.
        
        Parliamentary systems feature strong party discipline where MPs
        typically vote with their party line rather than personal preference.
        """
        # Base vote based on personal ideology
        personal_vote = legislator.decide_vote(bill)
        
        # Apply party discipline if legislator is in government coalition
        if (legislator.party_id in self.government_coalition and 
            self.random.random() < self.discipline_strength):
            # Government party members vote with government
            return True
        elif (legislator.party_id not in self.government_coalition and 
              self.random.random() < self.discipline_strength * 0.7):  # Opposition discipline weaker
            # Opposition votes against government bills
            return False
        else:
            # Vote based on personal ideology
            return personal_vote

    def _government_falls(self) -> None:
        """
        Handle government collapse after failed confidence vote.
        
        When government loses confidence, new government formation occurs.
        """
        self.government_formed = False
        self.government_party = None
        self.prime_minister = None
        self.government_coalition = []
        
        # Attempt to form new government
        self._form_government()

    def pass_legislation(self, bill: Bill) -> bool:
        """
        Pass legislation through parliamentary process.
        
        Government bills are typically confidence matters in parliamentary systems.
        """
        if not self.government_formed:
            return False
            
        # Treat major bills as confidence votes
        is_confidence_matter = self.random.random() < 0.3  # 30% of bills are confidence matters
        
        if is_confidence_matter:
            return self._conduct_confidence_vote(bill)
        else:
            # Regular vote with party discipline
            votes_for = 0
            votes_against = 0
            
            for agent in self.schedule.agents:
                if isinstance(agent, LegislatorAgent):
                    vote = self._get_disciplined_vote(agent, bill)
                    if vote:
                        votes_for += 1
                    else:
                        votes_against += 1
            
            return votes_for > votes_against

    def get_government_stats(self) -> Dict[str, Any]:
        """Return current government statistics for analysis."""
        return {
            'government_formed': self.government_formed,
            'government_party': self.government_party,
            'coalition_size': len(self.government_coalition),
            'confidence_votes_passed': self.confidence_votes_passed,
            'confidence_votes_failed': self.confidence_votes_failed,
            'prime_minister_id': self.prime_minister.unique_id if self.prime_minister else None
        }

    def step(self) -> None:
        """
        Advance the parliamentary model by one step.
        
        Includes government stability checks and potential legislation.
        """
        # Occasionally test government stability with a random bill
        if self.government_formed and self.random.random() < 0.2:  # 20% chance
            test_bill = Bill(
                bill_id=self.schedule.time,
                ideology=self._default_ideology(0, 1),
                salience=0.5
            )
            self.pass_legislation(test_bill)
        
        # Call parent step for data collection and agent activation
        super().step()


