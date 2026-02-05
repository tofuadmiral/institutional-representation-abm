from __future__ import annotations

from typing import List, Optional, Dict, Any, Sequence
import random
from dataclasses import dataclass

from bills.bill import Bill


@dataclass
class CommitteeJurisdiction:
    """Defines the policy area and ideological range a committee covers."""
    name: str
    policy_area: str
    ideology_center: Sequence[float]  # Center of jurisdiction in ideological space
    ideology_radius: float           # How far from center the committee covers
    
    def covers_bill(self, bill: Bill) -> bool:
        """Check if this committee has jurisdiction over a bill."""
        # Calculate distance from committee's ideological center
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
        size: int = 5,
        gatekeeping_power: float = 0.3  # Probability of killing bills they dislike
    ):
        self.committee_id = committee_id
        self.jurisdiction = jurisdiction
        self.size = size
        self.gatekeeping_power = gatekeeping_power
        
        # Committee composition
        self.members: List[int] = []  # legislator IDs
        self.chair: Optional[int] = None  # legislator ID of chair
        self.party_composition: Dict[int, int] = {}  # party_id -> count
        
        # Committee activity tracking
        self.bills_considered = 0
        self.bills_approved = 0
        self.bills_killed = 0
        self.amendments_made = 0

    def assign_members(self, available_legislators: List[Any], parties: List[Any]) -> None:
        """Assign legislators to committee with party-proportional representation."""
        if len(available_legislators) < self.size:
            self.size = len(available_legislators)
            
        # Calculate party strengths in legislature
        party_sizes = {}
        for legislator in available_legislators:
            party_id = legislator.party_id
            if party_id is not None:
                party_sizes[party_id] = party_sizes.get(party_id, 0) + 1
            
        total_legislators = len(available_legislators)
        
        # Assign members proportionally by party
        self.members = []
        self.party_composition = {}
        
        for party_id, party_size in party_sizes.items():
            # Calculate proportional seats (with minimum 1 if party exists)
            proportional_seats = max(1, round((party_size / total_legislators) * self.size))
            
            # Get legislators from this party
            party_legislators = [l for l in available_legislators if l.party_id == party_id]
            
            # Randomly select committee members from party
            selected = random.sample(
                party_legislators, 
                min(proportional_seats, len(party_legislators))
            )
            
            for legislator in selected:
                if len(self.members) < self.size:
                    self.members.append(legislator.unique_id)
                    self.party_composition[party_id] = self.party_composition.get(party_id, 0) + 1
                    
        # Select chair from largest party on committee
        if self.members:
            largest_party = max(self.party_composition.keys(), 
                              key=lambda p: self.party_composition[p])
            
            # Find a member from largest party to be chair
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
        
        # Get committee member opinions
        member_votes = {}
        support_count = 0
        
        for member_id in self.members:
            legislator = legislators[member_id]
            
            # Calculate support based on ideological distance
            distance = sum((a - b) ** 2 for a, b in zip(bill.ideology, legislator.ideology)) ** 0.5
            support_prob = max(0.1, 1.0 - distance)  # Min 10% chance of support
            
            supports = random.random() < support_prob
            member_votes[member_id] = supports
            if supports:
                support_count += 1
                
        support_rate = support_count / len(self.members)
        
        # Decision logic
        if support_rate > 0.6:
            # Strong support - approve as is
            self.bills_approved += 1
            return {
                "action": "approve",
                "bill": bill,
                "vote_breakdown": member_votes,
                "support_rate": support_rate
            }
        elif support_rate > 0.4:
            # Moderate support - try to amend
            amended_bill = self._amend_bill(bill, legislators)
            self.amendments_made += 1
            return {
                "action": "amend", 
                "bill": amended_bill,
                "original_bill": bill,
                "vote_breakdown": member_votes,
                "support_rate": support_rate
            }
        else:
            # Low support - might kill it
            if random.random() < self.gatekeeping_power:
                self.bills_killed += 1
                return {
                    "action": "kill",
                    "bill": bill,
                    "vote_breakdown": member_votes,
                    "support_rate": support_rate
                }
            else:
                # Let it pass anyway (sometimes committees don't kill bills they dislike)
                self.bills_approved += 1
                return {
                    "action": "approve",
                    "bill": bill,
                    "vote_breakdown": member_votes,
                    "support_rate": support_rate
                }

    def _amend_bill(self, bill: Bill, legislators: Dict[int, Any]) -> Bill:
        """Amend a bill to better reflect committee preferences."""
        if not self.members:
            return bill
            
        # Calculate average committee ideology
        total_ideology = [0.0, 0.0]  # Assuming 2D ideology space
        for member_id in self.members:
            legislator = legislators[member_id]
            for i in range(len(total_ideology)):
                total_ideology[i] += legislator.ideology[i]
                
        avg_ideology = [x / len(self.members) for x in total_ideology]
        
        # Move bill ideology toward committee average (partial amendment)
        amendment_strength = 0.3  # How much the bill moves toward committee
        amended_ideology = []
        
        for i in range(len(bill.ideology)):
            current = bill.ideology[i]
            target = avg_ideology[i]
            amended = current + amendment_strength * (target - current)
            amended_ideology.append(amended)
        
        # Create new bill with amended ideology
        amended_bill = Bill(
            bill_id=bill.bill_id,
            ideology=tuple(amended_ideology),
            salience=bill.salience,
            votes=bill.votes.copy()
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
                "amendment_rate": 0.0
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
            "amendment_rate": self.amendments_made / total_bills
        }