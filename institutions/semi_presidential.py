"""Semi-presidential institutional model.

Combines a directly-elected president (republican-style) with a cabinet
responsible to parliament (parliamentary-style). The two real-world variants
differ on who forms the government and whether the president can unilaterally
dismiss the PM. Both are reachable through the same class by flipping config
toggles:

    premier_presidential   : government_formation="majority_driven",
                             president_can_dismiss_pm=False
    president_parliamentary: government_formation="president_driven",
                             president_can_dismiss_pm=True

The class deliberately duplicates some helpers from ParliamentaryModel and
RepublicanModel instead of inheriting from both -- semi-presidential has
enough subtle interactions (cohabitation, divided government, dismissal) that
a dedicated class reads better than a diamond-inherited mixin.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.committee import CommitteeAgent, CommitteeJurisdiction
from agents.legislator import LegislatorAgent
from agents.party import PartyAgent
from bills.bill import Bill
from config import (
    GOV_FORMATION_MAJORITY_DRIVEN,
    GOV_FORMATION_PRESIDENT_DRIVEN,
    HUNG_PERSONAL_VOTE,
    SemiPresidentialConfig,
)
from institutions.base import BaseInstitutionModel


class SemiPresidentialModel(BaseInstitutionModel):
    """Semi-presidential system: president + cabinet responsible to parliament."""

    def __init__(
        self,
        num_legislators: int = 10,
        num_constituencies: int = 5,
        num_parties: int = 2,
        config: Optional[SemiPresidentialConfig] = None,
        seed: Optional[int] = None,
    ) -> None:
        self.config: SemiPresidentialConfig = config or SemiPresidentialConfig()

        super().__init__(
            num_legislators=num_legislators,
            num_constituencies=num_constituencies,
            num_parties=num_parties,
            legislator_config=self.config.legislator,
            seed=seed,
        )

        # Presidential state
        self.executive_party: Optional[int] = None
        self.president: Optional[LegislatorAgent] = None
        self.executive_ideology = (0.0, 0.0)

        # Parliamentary government state
        self.government_party: Optional[int] = None
        self.prime_minister: Optional[LegislatorAgent] = None
        self.government_coalition: List[int] = []
        self.government_formed: bool = False
        self.confidence_votes_passed: int = 0
        self.confidence_votes_failed: int = 0
        self.presidential_dismissals: int = 0

        # Legislative counters (republican-style)
        self.bills_passed_counter: int = 0
        self.bills_vetoed: int = 0
        self.gridlock_events: int = 0

        # Committees
        self.committees: List[CommitteeAgent] = []
        self.bills_in_committee: Dict[int, int] = {}

        self._initialize_committees()
        self._elect_president()
        self._form_government()

    # ------------------------------------------------------------------ setup

    def _initialize_committees(self) -> None:
        """Hybrid committee set — similar to parliamentary."""
        jurisdictions = [
            CommitteeJurisdiction(
                name="Finance Committee", policy_area="economic",
                ideology_center=(0.4, 0.0), ideology_radius=0.8,
            ),
            CommitteeJurisdiction(
                name="Social Affairs Committee", policy_area="social",
                ideology_center=(-0.3, 0.6), ideology_radius=0.9,
            ),
            CommitteeJurisdiction(
                name="Foreign Affairs Committee", policy_area="foreign",
                ideology_center=(0.0, -0.3), ideology_radius=0.7,
            ),
            CommitteeJurisdiction(
                name="Environment Committee", policy_area="environment",
                ideology_center=(-0.5, 0.3), ideology_radius=0.6,
            ),
            CommitteeJurisdiction(
                name="Justice Committee", policy_area="justice",
                ideology_center=(0.1, -0.5), ideology_radius=0.8,
            ),
        ]
        actual = min(self.config.num_committees, len(jurisdictions))
        for i in range(actual):
            self.committees.append(
                CommitteeAgent(
                    committee_id=i,
                    jurisdiction=jurisdictions[i],
                    rng=self.random,
                    size=self.config.committee_size,
                    gatekeeping_power=self.config.committee_gatekeeping_power,
                    config=self.config.committee,
                )
            )

    def _assign_committee_members(self) -> None:
        legislators = [a for a in self.schedule.agents if isinstance(a, LegislatorAgent)]
        parties = [a for a in self.schedule.agents if isinstance(a, PartyAgent)]
        for committee in self.committees:
            committee.assign_members(legislators, parties)

    def _elect_president(self) -> None:
        """Direct election — largest party usually wins, occasionally an outsider."""
        party_seats, party_legislators = self._tally_parties()
        if not party_seats:
            return

        if self.random.random() < self.config.largest_party_presidency_prob:
            self.executive_party = max(party_seats, key=lambda k: party_seats[k])
        else:
            self.executive_party = self.random.choice(list(party_seats.keys()))

        candidates = party_legislators.get(self.executive_party, [])
        if candidates:
            self.president = self.random.choice(candidates)
            self.executive_ideology = self.president.ideology

    def _tally_parties(self):
        party_seats: Dict[int, int] = {}
        party_legislators: Dict[int, List[LegislatorAgent]] = {}
        for agent in self.schedule.agents:
            if isinstance(agent, LegislatorAgent) and agent.party_id is not None:
                pid = agent.party_id
                party_seats[pid] = party_seats.get(pid, 0) + 1
                party_legislators.setdefault(pid, []).append(agent)
        return party_seats, party_legislators

    # ----------------------------------------------------- government formation

    def _form_government(self) -> None:
        if self.config.government_formation == GOV_FORMATION_PRESIDENT_DRIVEN:
            self._form_president_driven_government()
        else:
            self._form_majority_driven_government()
        self._assign_committee_members()

    def _form_majority_driven_government(self) -> None:
        """Parliamentary-style: largest party (or two-party coalition) forms government."""
        party_seats, party_legislators = self._tally_parties()
        if not party_seats:
            return

        largest = max(party_seats, key=lambda k: party_seats[k])
        largest_seats = party_seats[largest]
        total = sum(party_seats.values())
        majority = int(total * self.config.confidence_threshold) + 1

        if largest_seats >= majority:
            self.government_party = largest
            self.government_coalition = [largest]
        else:
            others = [(k, v) for k, v in party_seats.items() if k != largest]
            if others:
                second = max(others, key=lambda x: x[1])[0]
                if largest_seats + party_seats[second] >= majority:
                    self.government_party = largest
                    self.government_coalition = [largest, second]

        if self.government_party is not None:
            pool = party_legislators.get(self.government_party, [])
            if pool:
                self.prime_minister = self.random.choice(pool)
        self.government_formed = True

    def _form_president_driven_government(self) -> None:
        """President-driven: president appoints PM, preferably from own party.

        If the president's party has a majority (alone or with a second party),
        government forms as a normal majority coalition led by the presidential
        party. Otherwise the president appoints a minority cabinet from their
        own party — fragile but possible, common in president-parliamentary
        systems where the president can dismiss and replace the PM.
        """
        party_seats, party_legislators = self._tally_parties()
        if not party_seats:
            return

        total = sum(party_seats.values())
        majority = int(total * self.config.confidence_threshold) + 1

        if self.executive_party is None or self.executive_party not in party_seats:
            # Fall back to majority-driven if no president was elected
            self._form_majority_driven_government()
            return

        pres_seats = party_seats[self.executive_party]
        self.government_party = self.executive_party
        self.government_coalition = [self.executive_party]

        if pres_seats < majority:
            # Try to pull in a second party aligned with the president
            others = sorted(
                ((k, v) for k, v in party_seats.items() if k != self.executive_party),
                key=lambda x: x[1], reverse=True,
            )
            for pid, _ in others:
                if pres_seats + party_seats[pid] >= majority:
                    self.government_coalition = [self.executive_party, pid]
                    break
            # If still no coalition majority, the government is a minority cabinet.

        pool = party_legislators.get(self.executive_party, [])
        if pool:
            self.prime_minister = self.random.choice(pool)
        self.government_formed = True

    def _government_falls(self) -> None:
        self.government_formed = False
        self.government_party = None
        self.prime_minister = None
        self.government_coalition = []
        self._form_government()

    # ------------------------------------------------------------ voting logic

    def _get_disciplined_vote(self, legislator: LegislatorAgent, bill: Bill) -> bool:
        """Discipline midway between parliamentary and republican.

        Shares the hung-parliament toggle with ParliamentaryModel: under
        `personal_vote`, an empty coalition means no whip is in play and every
        MP reverts to their own preference; under `cohesive_obstruction` the
        opposition-whip branch applies to everyone.
        """
        personal_vote = legislator.decide_vote(bill)

        if (not self.government_coalition and
                self.config.hung_parliament_behavior == HUNG_PERSONAL_VOTE):
            return personal_vote

        if (
            legislator.party_id in self.government_coalition
            and self.random.random() < self.config.discipline_strength
        ):
            return True
        if (
            legislator.party_id not in self.government_coalition
            and self.random.random()
            < self.config.discipline_strength * self.config.opposition_discipline_multiplier
        ):
            return False
        return personal_vote

    def _conduct_confidence_vote(self, bill: Bill) -> bool:
        votes_for = 0
        votes_against = 0
        for agent in self.schedule.agents:
            if isinstance(agent, LegislatorAgent):
                if self._get_disciplined_vote(agent, bill):
                    votes_for += 1
                else:
                    votes_against += 1
        total = votes_for + votes_against
        passed = total > 0 and votes_for / total >= self.config.confidence_threshold
        if passed:
            self.confidence_votes_passed += 1
        else:
            self.confidence_votes_failed += 1
            self._government_falls()
        return passed

    def _executive_veto_check(self, bill: Bill) -> bool:
        """President vetoes bills far from their ideology."""
        if self.president is None:
            return False
        distance = sum(
            (a - b) ** 2 for a, b in zip(self.executive_ideology, bill.ideology)
        ) ** 0.5
        veto_prob = min(
            self.config.max_veto_probability,
            distance / self.config.veto_distance_scale,
        )
        veto_prob = max(veto_prob, self.config.executive_opposition_rate)
        return self.random.random() < veto_prob

    # ------------------------------------------------------------ legislation

    def _maybe_dismiss_pm(self) -> None:
        """Presidential dismissal check. Fires if the president can dismiss and
        the president-PM ideological distance exceeds 0.5."""
        if not (
            self.config.president_can_dismiss_pm
            and self.government_formed
            and self.president is not None
            and self.prime_minister is not None
        ):
            return
        distance = sum(
            (a - b) ** 2
            for a, b in zip(self.executive_ideology, self.prime_minister.ideology)
        ) ** 0.5
        if distance > 0.5 and self.random.random() < self.config.presidential_dismissal_rate:
            self.presidential_dismissals += 1
            self._government_falls()

    def pass_legislation(self, bill: Bill) -> bool:
        # Dismissal runs per legislative opportunity; in batch mode this is the
        # only entry point that triggers it (step() bypassed by CLI runners).
        self._maybe_dismiss_pm()

        if not self.government_formed:
            return False

        committee_result = self._route_to_committee(bill)
        if committee_result["action"] == "kill":
            return False
        if committee_result["action"] == "amend":
            bill = committee_result["bill"]

        is_confidence_matter = self.random.random() < self.config.confidence_matter_rate
        if is_confidence_matter:
            legislative_passed = self._conduct_confidence_vote(bill)
        else:
            votes_for = 0
            votes_against = 0
            for agent in self.schedule.agents:
                if isinstance(agent, LegislatorAgent):
                    if self._get_disciplined_vote(agent, bill):
                        votes_for += 1
                    else:
                        votes_against += 1
            legislative_passed = votes_for > votes_against

        if not legislative_passed:
            return False

        # Presidential veto stage (semi-presidential systems retain this).
        if self._executive_veto_check(bill):
            self.bills_vetoed += 1
            # Count votes again to set override threshold if this wasn't a confidence vote.
            if is_confidence_matter:
                # Confidence already passed -- treat it as a strong majority
                self.bills_passed_counter += 1
                return True
            total_legislators = sum(
                1 for a in self.schedule.agents if isinstance(a, LegislatorAgent)
            )
            override_threshold = int(
                total_legislators * self.config.override_threshold_fraction
            ) + 1
            # Approximate override check using last tally
            if 'votes_for' in locals() and votes_for >= override_threshold:
                self.bills_passed_counter += 1
                return True
            self.gridlock_events += 1
            return False

        self.bills_passed_counter += 1
        return True

    def _route_to_committee(self, bill: Bill) -> Dict[str, Any]:
        relevant = None
        for c in self.committees:
            if c.jurisdiction.covers_bill(bill):
                relevant = c
                break
        if relevant is None:
            return {"action": "approve", "bill": bill}

        self.bills_in_committee[bill.bill_id] = relevant.committee_id
        legislators: Dict[int, LegislatorAgent] = {
            a.unique_id: a for a in self.schedule.agents if isinstance(a, LegislatorAgent)
        }
        return relevant.consider_bill(bill, legislators)

    # -------------------------------------------------------------- step loop

    def step(self) -> None:
        # Dismissal is owned by pass_legislation (fires per bill). Steps that
        # don't produce a bill skip the dismissal opportunity; this keeps the
        # per-bill semantics consistent between batch CLI runs and interactive
        # step-driven runs.
        if (
            self.government_formed
            and self.random.random() < self.config.legislative_activity_rate
        ):
            test_bill = Bill(
                bill_id=self.schedule.time,
                ideology=self._default_ideology(0, 1),
                salience=0.5,
            )
            self.pass_legislation(test_bill)

        super().step()

    # --------------------------------------------------------- stats accessors

    def get_government_stats(self) -> Dict[str, Any]:
        return {
            "variant": self.config.variant,
            "government_formation": self.config.government_formation,
            "government_formed": self.government_formed,
            "government_party": self.government_party,
            "coalition_size": len(self.government_coalition),
            "confidence_votes_passed": self.confidence_votes_passed,
            "confidence_votes_failed": self.confidence_votes_failed,
            "presidential_dismissals": self.presidential_dismissals,
            "prime_minister_id": self.prime_minister.unique_id if self.prime_minister else None,
        }

    def get_system_stats(self) -> Dict[str, Any]:
        return {
            "system_type": f"semi_presidential_{self.config.variant}",
            "executive_party": self.executive_party,
            "president_id": self.president.unique_id if self.president else None,
            "bills_passed": self.bills_passed_counter,
            "bills_vetoed": self.bills_vetoed,
            "gridlock_events": self.gridlock_events,
        }

    def get_separation_of_powers_stats(self) -> Dict[str, Any]:
        party_seats, _ = self._tally_parties()
        majority_party = (
            max(party_seats, key=lambda k: party_seats[k]) if party_seats else None
        )
        # Cohabitation: president's party is not the parliamentary majority party.
        cohabitation = (
            self.executive_party is not None
            and majority_party is not None
            and self.executive_party != majority_party
        )
        # Divided government: executive's party is not in the governing coalition.
        divided_government = (
            self.executive_party is not None
            and self.executive_party not in self.government_coalition
        )
        total_decisions = self.bills_passed_counter + self.bills_vetoed + self.gridlock_events
        return {
            "cohabitation": cohabitation,
            "divided_government": divided_government,
            "executive_party": self.executive_party,
            "legislative_majority_party": majority_party,
            "veto_rate": self.bills_vetoed / max(1, total_decisions),
            "gridlock_rate": self.gridlock_events / max(1, total_decisions),
        }

    def get_committee_stats(self) -> Dict[str, Any]:
        if not self.committees:
            return {
                "num_committees": 0,
                "avg_committee_size": 0,
                "total_bills_considered": 0,
                "total_bills_killed": 0,
                "total_amendments": 0,
                "committee_details": [],
            }

        considered = sum(c.bills_considered for c in self.committees)
        killed = sum(c.bills_killed for c in self.committees)
        amended = sum(c.amendments_made for c in self.committees)
        avg_size = sum(len(c.members) for c in self.committees) / len(self.committees)
        return {
            "num_committees": len(self.committees),
            "avg_committee_size": avg_size,
            "total_bills_considered": considered,
            "total_bills_killed": killed,
            "total_amendments": amended,
            "avg_kill_rate": killed / considered if considered else 0.0,
            "avg_amendment_rate": amended / considered if considered else 0.0,
            "committee_details": [c.get_stats() for c in self.committees],
        }
