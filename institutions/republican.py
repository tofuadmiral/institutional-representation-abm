from __future__ import annotations

from typing import Optional, List, Dict, Any

from institutions.base import BaseInstitutionModel
from agents.legislator import LegislatorAgent
from agents.party import PartyAgent
from agents.committee import CommitteeAgent, CommitteeJurisdiction
from bills.bill import Bill
from config import RepublicanConfig


class RepublicanModel(BaseInstitutionModel):
    """
    Republican/Presidential system with separation of powers and committee-based governance.

    Key Features:
    - Separation of powers (Executive vs Legislative)
    - Committee-based agenda setting (committees control floor time)
    - Individual legislator autonomy (weaker party discipline)
    - Fixed terms (no confidence votes)
    - Gridlock potential (executive vs legislative opposition)
    - Committee gatekeeping powers
    """

    def __init__(
        self,
        num_legislators: int = 10,
        num_constituencies: int = 5,
        num_parties: int = 2,
        config: Optional[RepublicanConfig] = None,
        seed: Optional[int] = None,
    ) -> None:
        self.config: RepublicanConfig = config or RepublicanConfig()

        super().__init__(
            num_legislators=num_legislators,
            num_constituencies=num_constituencies,
            num_parties=num_parties,
            legislator_config=self.config.legislator,
            seed=seed,
        )

        # Executive branch state
        self.executive_party: Optional[int] = None
        self.president: Optional[LegislatorAgent] = None
        self.executive_ideology = (0.0, 0.0)

        # Legislative state
        self.legislative_session: int = 1
        self.bills_passed: int = 0
        self.bills_vetoed: int = 0
        self.gridlock_events: int = 0

        # Committee system
        self.committees: List[CommitteeAgent] = []
        self.bills_in_committee: Dict[int, int] = {}
        self.committee_agenda: List[int] = []

        # Initialize system
        self._initialize_committees()
        self._elect_executive()

    def _initialize_committees(self) -> None:
        """Create committees with specialized jurisdictions - central to republican system."""
        jurisdictions = [
            CommitteeJurisdiction(
                name="House Ways and Means",
                policy_area="economic",
                ideology_center=(0.3, 0.0),
                ideology_radius=0.9,
            ),
            CommitteeJurisdiction(
                name="House Judiciary",
                policy_area="justice",
                ideology_center=(0.1, -0.4),
                ideology_radius=0.8,
            ),
            CommitteeJurisdiction(
                name="House Foreign Affairs",
                policy_area="foreign",
                ideology_center=(0.0, -0.2),
                ideology_radius=0.7,
            ),
            CommitteeJurisdiction(
                name="House Energy and Commerce",
                policy_area="environment",
                ideology_center=(-0.2, 0.1),
                ideology_radius=0.8,
            ),
            CommitteeJurisdiction(
                name="House Education and Labor",
                policy_area="social",
                ideology_center=(-0.4, 0.5),
                ideology_radius=0.9,
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

        self._assign_committee_members()

    def _assign_committee_members(self) -> None:
        """Assign legislators to committees with party proportionality."""
        legislators = []
        parties = []

        for agent in self.schedule.agents:
            if isinstance(agent, LegislatorAgent):
                legislators.append(agent)
            elif isinstance(agent, PartyAgent):
                parties.append(agent)

        for committee in self.committees:
            committee.assign_members(legislators, parties)

    def _elect_executive(self) -> None:
        """Elect executive (president) from available parties."""
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
            if self.random.random() < self.config.largest_party_presidency_prob:
                self.executive_party = max(party_seats.keys(), key=lambda k: party_seats[k])
            else:
                other_parties = [k for k in party_seats.keys()]
                self.executive_party = self.random.choice(other_parties)

            if self.executive_party in party_legislators:
                executive_legislators = party_legislators[self.executive_party]
                if executive_legislators:
                    self.president = self.random.choice(executive_legislators)
                    self.executive_ideology = self.president.ideology

    def _get_weak_disciplined_vote(self, legislator: LegislatorAgent, bill: Bill) -> bool:
        """
        Get legislator vote with weak party discipline (republican characteristic).

        Republicans have much weaker party discipline than parliamentary systems.
        """
        if self.config.discipline_strength == 0:
            return legislator.decide_vote(bill)

        if self.random.random() < self.config.discipline_strength:
            if legislator.party_id is not None:
                party_legislators = [
                    a for a in self.schedule.agents
                    if isinstance(a, LegislatorAgent) and a.party_id == legislator.party_id
                ]

                if party_legislators:
                    avg_ideology = [
                        sum(l.ideology[0] for l in party_legislators) / len(party_legislators),
                        sum(l.ideology[1] for l in party_legislators) / len(party_legislators),
                    ]

                    dist = sum((a - b) ** 2 for a, b in zip(avg_ideology, bill.ideology)) ** 0.5
                    return dist < self.legislator_config.vote_support_threshold

        return legislator.decide_vote(bill)

    def _executive_veto_check(self, bill: Bill) -> bool:
        """Check if executive vetoes the bill."""
        if self.president is None:
            return False

        executive_distance = sum((a - b) ** 2 for a, b in zip(self.executive_ideology, bill.ideology)) ** 0.5

        veto_probability = min(
            self.config.max_veto_probability,
            executive_distance / self.config.veto_distance_scale,
        )

        veto_probability = max(veto_probability, self.config.executive_opposition_rate)

        return self.random.random() < veto_probability

    def pass_legislation(self, bill: Bill) -> bool:
        """
        Pass legislation through republican process.

        Process:
        1. Committee consideration (can kill, amend, or schedule)
        2. Floor vote (if committee approves)
        3. Executive veto check
        4. Override attempt (if vetoed)
        """
        committee_result = self._route_to_committee(bill)

        if committee_result["action"] == "kill":
            return False
        elif committee_result["action"] == "amend":
            bill = committee_result["bill"]

        votes_for = 0
        votes_against = 0

        for agent in self.schedule.agents:
            if isinstance(agent, LegislatorAgent):
                vote = self._get_weak_disciplined_vote(agent, bill)
                if vote:
                    votes_for += 1
                else:
                    votes_against += 1

        legislative_passed = votes_for > votes_against
        if not legislative_passed:
            return False

        if self._executive_veto_check(bill):
            self.bills_vetoed += 1

            total_legislators = votes_for + votes_against
            override_threshold = int(total_legislators * self.config.override_threshold_fraction) + 1

            if votes_for >= override_threshold:
                self.bills_passed += 1
                return True
            else:
                self.gridlock_events += 1
                return False
        else:
            self.bills_passed += 1
            return True

    def _route_to_committee(self, bill: Bill) -> Dict[str, Any]:
        """Route bill to appropriate committee (stronger gatekeeping than parliamentary)."""
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

    def get_system_stats(self) -> Dict[str, Any]:
        """Return republican system statistics."""
        return {
            'system_type': 'republican',
            'executive_party': self.executive_party,
            'president_id': self.president.unique_id if self.president else None,
            'legislative_session': self.legislative_session,
            'bills_passed': self.bills_passed,
            'bills_vetoed': self.bills_vetoed,
            'gridlock_events': self.gridlock_events,
            'discipline_strength': self.config.discipline_strength,
        }

    def get_separation_of_powers_stats(self) -> Dict[str, Any]:
        """Analyze separation of powers dynamics."""
        party_seats: Dict[int, int] = {}
        for agent in self.schedule.agents:
            if isinstance(agent, LegislatorAgent) and agent.party_id is not None:
                party_seats[agent.party_id] = party_seats.get(agent.party_id, 0) + 1

        total_legislators = sum(party_seats.values())
        legislative_majority_party = max(party_seats.keys(), key=lambda k: party_seats[k]) if party_seats else None

        divided_government = (self.executive_party != legislative_majority_party)

        return {
            'divided_government': divided_government,
            'executive_party': self.executive_party,
            'legislative_majority_party': legislative_majority_party,
            'legislative_party_seats': party_seats,
            'total_legislators': total_legislators,
            'veto_rate': (self.bills_vetoed / max(1, self.bills_passed + self.bills_vetoed)),
            'gridlock_rate': (self.gridlock_events / max(1, self.bills_passed + self.bills_vetoed + self.gridlock_events)),
        }

    def get_committee_stats(self) -> Dict[str, Any]:
        """Return committee system statistics (same as parliamentary but used differently)."""
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
        Advance the republican model by one step.

        Different from parliamentary - no government stability checks.
        Focus on committee work and legislative-executive tensions.
        """
        if self.random.random() < self.config.legislative_activity_rate:
            test_bill = Bill(
                bill_id=self.schedule.time,
                ideology=self._default_ideology(0, 1),
                salience=0.5,
            )
            self.pass_legislation(test_bill)

        self.schedule.step()
        self.datacollector.collect(self)
