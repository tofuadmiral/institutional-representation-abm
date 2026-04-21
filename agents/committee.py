from __future__ import annotations

from typing import List, Optional, Dict, Any, Sequence
from random import Random
from dataclasses import dataclass

from bills.bill import Bill
from config import CommitteeConfig


@dataclass
class CommitteeJurisdiction:
    """Defines the policy area and ideological range a committee covers."""
    name: str
    policy_area: str
    ideology_center: Sequence[float]
    ideology_radius: float

    def covers_bill(self, bill: Bill) -> bool:
        """Check if this committee has jurisdiction over a bill."""
        distance = sum((a - b) ** 2 for a, b in zip(bill.ideology, self.ideology_center)) ** 0.5
        return distance <= self.ideology_radius


class CommitteeAgent:
    """
    Legislative committee with jurisdiction over specific policy areas.

    Features:
    - Specialized policy jurisdiction
    - Party-proportional membership
    - Committee chair (agenda control)
    - Amendment powers
    - Gatekeeping function (can kill bills)
    """

    def __init__(
        self,
        committee_id: int,
        jurisdiction: CommitteeJurisdiction,
        rng: Random,
        size: int = 5,
        gatekeeping_power: float = 0.3,
        config: Optional[CommitteeConfig] = None,
    ):
        self.committee_id = committee_id
        self.jurisdiction = jurisdiction
        self.rng = rng
        self.size = size
        self.gatekeeping_power = gatekeeping_power
        self.config = config or CommitteeConfig()

        # Committee composition
        self.members: List[int] = []
        self.chair: Optional[int] = None
        self.party_composition: Dict[int, int] = {}

        # Committee activity tracking
        self.bills_considered = 0
        self.bills_approved = 0
        self.bills_killed = 0
        self.amendments_made = 0

    def assign_members(self, available_legislators: List[Any], parties: List[Any]) -> None:
        """Assign legislators to committee with party-proportional representation."""
        if len(available_legislators) < self.size:
            self.size = len(available_legislators)

        party_sizes: Dict[int, int] = {}
        for legislator in available_legislators:
            party_id = legislator.party_id
            if party_id is not None:
                party_sizes[party_id] = party_sizes.get(party_id, 0) + 1

        total_legislators = len(available_legislators)

        self.members = []
        self.party_composition = {}

        for party_id, party_size in party_sizes.items():
            proportional_seats = max(1, round((party_size / total_legislators) * self.size))
            party_legislators = [l for l in available_legislators if l.party_id == party_id]

            selected = self.rng.sample(
                party_legislators,
                min(proportional_seats, len(party_legislators)),
            )

            for legislator in selected:
                if len(self.members) < self.size:
                    self.members.append(legislator.unique_id)
                    self.party_composition[party_id] = self.party_composition.get(party_id, 0) + 1

        if self.members:
            largest_party = max(self.party_composition.keys(),
                                key=lambda p: self.party_composition[p])

            for legislator in available_legislators:
                if (legislator.unique_id in self.members and
                        legislator.party_id == largest_party):
                    self.chair = legislator.unique_id
                    break

    def consider_bill(self, bill: Bill, legislators: Dict[int, Any]) -> Dict[str, Any]:
        """
        Committee consideration of a bill.

        Returns:
            - action: "approve", "kill", "amend"
            - amended_bill: Bill object if amended
            - vote_breakdown: How committee members voted
        """
        if not self.jurisdiction.covers_bill(bill):
            return {"action": "refer", "message": "Outside committee jurisdiction"}

        self.bills_considered += 1

        member_votes: Dict[int, bool] = {}
        support_count = 0

        for member_id in self.members:
            legislator = legislators[member_id]

            distance = sum((a - b) ** 2 for a, b in zip(bill.ideology, legislator.ideology)) ** 0.5
            support_prob = max(self.config.min_support_probability, 1.0 - distance)

            supports = self.rng.random() < support_prob
            member_votes[member_id] = supports
            if supports:
                support_count += 1

        support_rate = support_count / len(self.members)

        if support_rate > self.config.strong_support_threshold:
            self.bills_approved += 1
            return {
                "action": "approve",
                "bill": bill,
                "vote_breakdown": member_votes,
                "support_rate": support_rate,
            }
        elif support_rate > self.config.moderate_support_threshold:
            amended_bill = self._amend_bill(bill, legislators)
            self.amendments_made += 1
            return {
                "action": "amend",
                "bill": amended_bill,
                "original_bill": bill,
                "vote_breakdown": member_votes,
                "support_rate": support_rate,
            }
        else:
            if self.rng.random() < self.gatekeeping_power:
                self.bills_killed += 1
                return {
                    "action": "kill",
                    "bill": bill,
                    "vote_breakdown": member_votes,
                    "support_rate": support_rate,
                }
            else:
                self.bills_approved += 1
                return {
                    "action": "approve",
                    "bill": bill,
                    "vote_breakdown": member_votes,
                    "support_rate": support_rate,
                }

    def _amend_bill(self, bill: Bill, legislators: Dict[int, Any]) -> Bill:
        """Amend a bill to better reflect committee preferences."""
        if not self.members:
            return bill

        total_ideology = [0.0, 0.0]
        for member_id in self.members:
            legislator = legislators[member_id]
            for i in range(len(total_ideology)):
                total_ideology[i] += legislator.ideology[i]

        avg_ideology = [x / len(self.members) for x in total_ideology]

        amendment_strength = self.config.amendment_strength
        amended_ideology = []

        for i in range(len(bill.ideology)):
            current = bill.ideology[i]
            target = avg_ideology[i]
            amended = current + amendment_strength * (target - current)
            amended_ideology.append(amended)

        amended_bill = Bill(
            bill_id=bill.bill_id,
            ideology=tuple(amended_ideology),
            salience=bill.salience,
            votes=bill.votes.copy(),
        )

        return amended_bill

    def get_stats(self) -> Dict[str, Any]:
        """Get committee performance statistics."""
        total_bills = self.bills_considered
        if total_bills == 0:
            return {
                "committee_id": self.committee_id,
                "jurisdiction": self.jurisdiction.name,
                "policy_area": self.jurisdiction.policy_area,
                "chair": self.chair,
                "size": len(self.members),
                "party_composition": self.party_composition,
                "bills_considered": 0,
                "bills_approved": 0,
                "bills_killed": 0,
                "amendments_made": 0,
                "approval_rate": 0.0,
                "kill_rate": 0.0,
                "amendment_rate": 0.0,
            }

        return {
            "committee_id": self.committee_id,
            "jurisdiction": self.jurisdiction.name,
            "policy_area": self.jurisdiction.policy_area,
            "chair": self.chair,
            "size": len(self.members),
            "party_composition": self.party_composition,
            "bills_considered": total_bills,
            "bills_approved": self.bills_approved,
            "bills_killed": self.bills_killed,
            "amendments_made": self.amendments_made,
            "approval_rate": self.bills_approved / total_bills,
            "kill_rate": self.bills_killed / total_bills,
            "amendment_rate": self.amendments_made / total_bills,
        }
