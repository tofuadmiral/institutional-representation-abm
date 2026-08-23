from __future__ import annotations

from typing import Optional, List, Dict, Any

from institutions.base import BaseInstitutionModel
from agents.legislator import LegislatorAgent
from agents.party import PartyAgent
from agents.committee import CommitteeAgent, CommitteeJurisdiction
from bills.bill import Bill
from config import HUNG_PERSONAL_VOTE, ParliamentaryConfig


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
        config: Optional[ParliamentaryConfig] = None,
        seed: Optional[int] = None,
    ) -> None:
        self.config: ParliamentaryConfig = config or ParliamentaryConfig()

        super().__init__(
            num_legislators=num_legislators,
            num_constituencies=num_constituencies,
            num_parties=num_parties,
            legislator_config=self.config.legislator,
            seed=seed,
        )

        # Government state
        self.government_party: Optional[int] = None
        self.prime_minister: Optional[LegislatorAgent] = None
        self.government_coalition: List[int] = []
        self.government_formed: bool = False
        self.confidence_votes_passed: int = 0
        self.confidence_votes_failed: int = 0

        # Committee system
        self.committees: List[CommitteeAgent] = []
        self.bills_in_committee: Dict[int, int] = {}

        # Initialize committees and form government
        self._initialize_committees()
        self._form_government()

    def _initialize_committees(self) -> None:
        """Create committees with specialized jurisdictions."""
        jurisdictions = [
            CommitteeJurisdiction(
                name="Finance Committee",
                policy_area="economic",
                ideology_center=(0.5, 0.0),
                ideology_radius=0.8,
            ),
            CommitteeJurisdiction(
                name="Social Affairs Committee",
                policy_area="social",
                ideology_center=(-0.3, 0.7),
                ideology_radius=0.9,
            ),
            CommitteeJurisdiction(
                name="Foreign Affairs Committee",
                policy_area="foreign",
                ideology_center=(0.0, -0.4),
                ideology_radius=0.7,
            ),
            CommitteeJurisdiction(
                name="Environment Committee",
                policy_area="environment",
                ideology_center=(-0.6, 0.3),
                ideology_radius=0.6,
            ),
            CommitteeJurisdiction(
                name="Justice Committee",
                policy_area="justice",
                ideology_center=(0.0, -0.6),
                ideology_radius=0.8,
            ),
        ]

        actual_committees = min(self.config.num_committees, len(jurisdictions))

        for i in range(actual_committees):
            committee = CommitteeAgent(
                committee_id=i,
                jurisdiction=jurisdictions[i],
                rng=self.random,
                size=self.config.committee_size,
                gatekeeping_power=self.config.committee_gatekeeping_power,
                config=self.config.committee,
            )
            self.committees.append(committee)

    def _assign_committee_members(self) -> None:
        """Assign legislators to committees after government formation."""
        legislators = []
        parties = []

        for agent in self.schedule.agents:
            if isinstance(agent, LegislatorAgent):
                legislators.append(agent)
            elif isinstance(agent, PartyAgent):
                parties.append(agent)

        for committee in self.committees:
            committee.assign_members(legislators, parties)

    def _form_government(self) -> None:
        """
        Form government based on party seat distribution.

        In parliamentary systems, the party (or coalition) that can command
        a majority in parliament forms the government.
        """
        party_seats: Dict[int, int] = {}
        party_legislators: Dict[int, List[LegislatorAgent]] = {}

        for agent in self.schedule.agents:
            if isinstance(agent, LegislatorAgent):
                party_id = agent.party_id
                if party_id is not None:
                    party_seats[party_id] = party_seats.get(party_id, 0) + 1
                    if party_id not in party_legislators:
                        party_legislators[party_id] = []
                    party_legislators[party_id].append(agent)

        if party_seats:
            largest_party = max(party_seats.keys(), key=lambda k: party_seats[k])
            largest_party_seats = party_seats[largest_party]

            total_seats = sum(party_seats.values())
            majority_threshold = int(total_seats * self.config.confidence_threshold) + 1

            if largest_party_seats >= majority_threshold:
                self.government_party = largest_party
                self.government_coalition = [largest_party]
            else:
                other_parties = [(k, v) for k, v in party_seats.items() if k != largest_party]
                if other_parties:
                    second_largest = max(other_parties, key=lambda x: x[1])[0]
                    coalition_seats = largest_party_seats + party_seats[second_largest]

                    if coalition_seats >= majority_threshold:
                        self.government_party = largest_party
                        self.government_coalition = [largest_party, second_largest]

            if self.government_party is not None and self.government_party in party_legislators:
                government_mps = party_legislators[self.government_party]
                if government_mps:
                    self.prime_minister = self.random.choice(government_mps)

            self.government_formed = True

        self._assign_committee_members()

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

        total_votes = votes_for + votes_against
        confidence_passed = votes_for / total_votes >= self.config.confidence_threshold

        if confidence_passed:
            self.confidence_votes_passed += 1
        else:
            self.confidence_votes_failed += 1
            self._government_falls()

        return confidence_passed

    def _get_disciplined_vote(self, legislator: LegislatorAgent, bill: Bill) -> bool:
        """
        Get legislator's vote with party discipline applied.

        Parliamentary systems feature strong party discipline where MPs
        typically vote with their party line rather than personal preference.

        Hung-parliament behaviour (empty coalition): under `personal_vote` the
        whip is simply absent, so every MP reverts to their own preference.
        Under `cohesive_obstruction` the opposition-whip branch below applies
        to every MP — a polarised, anti-system reading of hung parliaments in
        which cohesive obstruction blocks all bills.
        """
        personal_vote = legislator.decide_vote(bill)

        if (not self.government_coalition and
                self.config.hung_parliament_behavior == HUNG_PERSONAL_VOTE):
            return personal_vote

        if (legislator.party_id in self.government_coalition and
                self.random.random() < self.config.discipline_strength):
            return True
        elif (legislator.party_id not in self.government_coalition and
              self.random.random() < self.config.discipline_strength * self.config.opposition_discipline_multiplier):
            return False
        else:
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

        self._form_government()

    def pass_legislation(self, bill: Bill) -> bool:
        """
        Pass legislation through parliamentary process with committee stage.

        Bills go through:
        1. Committee consideration (can amend or kill)
        2. Floor vote with party discipline
        3. Confidence votes for government bills
        """
        if not self.government_formed:
            return False

        committee_result = self._route_to_committee(bill)

        if committee_result["action"] == "kill":
            return False
        elif committee_result["action"] == "amend":
            bill = committee_result["bill"]

        is_confidence_matter = self.random.random() < self.config.confidence_matter_rate

        if is_confidence_matter:
            return self._conduct_confidence_vote(bill)
        else:
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

    def _route_to_committee(self, bill: Bill) -> Dict[str, Any]:
        """Route bill to appropriate committee for consideration."""
        relevant_committee = None
        for committee in self.committees:
            if committee.jurisdiction.covers_bill(bill):
                relevant_committee = committee
                break

        if relevant_committee is None:
            return {"action": "approve", "bill": bill}

        self.bills_in_committee[bill.bill_id] = relevant_committee.committee_id

        legislators: Dict[int, LegislatorAgent] = {}
        for agent in self.schedule.agents:
            if isinstance(agent, LegislatorAgent):
                legislators[agent.unique_id] = agent

        return relevant_committee.consider_bill(bill, legislators)

    def get_government_stats(self) -> Dict[str, Any]:
        """Return current government statistics for analysis."""
        return {
            'government_formed': self.government_formed,
            'government_party': self.government_party,
            'coalition_size': len(self.government_coalition),
            'confidence_votes_passed': self.confidence_votes_passed,
            'confidence_votes_failed': self.confidence_votes_failed,
            'prime_minister_id': self.prime_minister.unique_id if self.prime_minister else None,
        }

    def get_committee_stats(self) -> Dict[str, Any]:
        """Return committee system statistics for analysis."""
        if not self.committees:
            return {
                'num_committees': 0,
                'avg_committee_size': 0,
                'total_bills_considered': 0,
                'total_bills_killed': 0,
                'total_amendments': 0,
                'committee_details': [],
            }

        total_bills_considered = sum(c.bills_considered for c in self.committees)
        total_bills_killed = sum(c.bills_killed for c in self.committees)
        total_amendments = sum(c.amendments_made for c in self.committees)
        avg_size = sum(len(c.members) for c in self.committees) / len(self.committees)

        return {
            'num_committees': len(self.committees),
            'avg_committee_size': avg_size,
            'total_bills_considered': total_bills_considered,
            'total_bills_killed': total_bills_killed,
            'total_amendments': total_amendments,
            'avg_kill_rate': (total_bills_killed / total_bills_considered) if total_bills_considered > 0 else 0,
            'avg_amendment_rate': (total_amendments / total_bills_considered) if total_bills_considered > 0 else 0,
            'committee_details': [c.get_stats() for c in self.committees],
        }

    def step(self) -> None:
        """
        Advance the parliamentary model by one step.

        Includes government stability checks and potential legislation.
        """
        if self.government_formed and self.random.random() < self.config.legislative_activity_rate:
            test_bill = Bill(
                bill_id=self.schedule.time,
                ideology=self._default_ideology(0, 1),
                salience=0.5,
            )
            self.pass_legislation(test_bill)

        super().step()
