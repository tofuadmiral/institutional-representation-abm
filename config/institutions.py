from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LegislatorConfig:
    vote_support_threshold: float = 1.0


@dataclass(frozen=True)
class CommitteeConfig:
    strong_support_threshold: float = 0.6
    moderate_support_threshold: float = 0.4
    min_support_probability: float = 0.1
    amendment_strength: float = 0.3


# Behaviour when no governing coalition forms (empty cabinet list). Two
# defensible readings of a hung parliament:
#
#   cohesive_obstruction  — every MP counts as "opposition" and is whipped
#       against bills (anti-system blocs, Weimar-style polarised obstruction)
#   personal_vote         — with no whip in play every MP reverts to their own
#       preference (issue-by-issue majorities, Benelux/Scandinavian minority
#       governance)
HUNG_COHESIVE_OBSTRUCTION = "cohesive_obstruction"
HUNG_PERSONAL_VOTE = "personal_vote"


@dataclass(frozen=True)
class ParliamentaryConfig:
    hung_parliament_behavior: str = HUNG_COHESIVE_OBSTRUCTION
    confidence_threshold: float = 0.5
    discipline_strength: float = 0.8
    opposition_discipline_multiplier: float = 0.7
    confidence_matter_rate: float = 0.3
    legislative_activity_rate: float = 0.2
    num_committees: int = 3
    committee_size: int = 5
    committee_gatekeeping_power: float = 0.3
    committee: CommitteeConfig = field(default_factory=CommitteeConfig)
    legislator: LegislatorConfig = field(default_factory=LegislatorConfig)


@dataclass(frozen=True)
class RepublicanConfig:
    discipline_strength: float = 0.4
    executive_opposition_rate: float = 0.3
    largest_party_presidency_prob: float = 0.7
    max_veto_probability: float = 0.8
    veto_distance_scale: float = 2.0
    override_threshold_fraction: float = 0.67
    legislative_activity_rate: float = 0.3
    num_committees: int = 3
    committee_size: int = 5
    committee_gatekeeping_power: float = 0.4
    committee: CommitteeConfig = field(default_factory=CommitteeConfig)
    legislator: LegislatorConfig = field(default_factory=LegislatorConfig)


# Semi-presidential: a directly-elected president coexists with a cabinet
# responsible to parliament. Two Shugart-Carey variants differ on who forms the
# government and whether the president can unilaterally dismiss the PM.
#
#   premier_presidential  (France, Portugal, Ireland):
#       government_formation = "majority_driven"
#       president_can_dismiss_pm = False
#       cabinet responsible to parliament only
#
#   president_parliamentary  (Russia, Weimar Republic, Sri Lanka pre-1978):
#       government_formation = "president_driven"
#       president_can_dismiss_pm = True
#       cabinet responsible to both president and parliament

VARIANT_PREMIER_PRESIDENTIAL = "premier_presidential"
VARIANT_PRESIDENT_PARLIAMENTARY = "president_parliamentary"
GOV_FORMATION_MAJORITY_DRIVEN = "majority_driven"
GOV_FORMATION_PRESIDENT_DRIVEN = "president_driven"


@dataclass(frozen=True)
class SemiPresidentialConfig:
    # Variant tag is informational; behavior is driven by the two toggles below.
    variant: str = VARIANT_PREMIER_PRESIDENTIAL
    government_formation: str = GOV_FORMATION_MAJORITY_DRIVEN
    president_can_dismiss_pm: bool = False
    presidential_dismissal_rate: float = 0.05

    # Discipline sits between parliamentary (0.8) and republican (0.4) — MPs
    # split loyalty between their party-whip and an independently elected
    # president.
    discipline_strength: float = 0.6
    opposition_discipline_multiplier: float = 0.7
    hung_parliament_behavior: str = HUNG_COHESIVE_OBSTRUCTION
    confidence_threshold: float = 0.5
    confidence_matter_rate: float = 0.3
    legislative_activity_rate: float = 0.25

    # Presidential traits (from Republican), softened because the president
    # shares the executive with a PM.
    largest_party_presidency_prob: float = 0.6
    max_veto_probability: float = 0.6
    veto_distance_scale: float = 2.0
    override_threshold_fraction: float = 0.67
    executive_opposition_rate: float = 0.2

    # Committees
    num_committees: int = 3
    committee_size: int = 5
    committee_gatekeeping_power: float = 0.35

    committee: CommitteeConfig = field(default_factory=CommitteeConfig)
    legislator: LegislatorConfig = field(default_factory=LegislatorConfig)


def premier_presidential_config(**overrides) -> SemiPresidentialConfig:
    """France / Portugal-style preset: majority forms government, no PM dismissal."""
    return SemiPresidentialConfig(
        variant=VARIANT_PREMIER_PRESIDENTIAL,
        government_formation=GOV_FORMATION_MAJORITY_DRIVEN,
        president_can_dismiss_pm=False,
        **overrides,
    )


def president_parliamentary_config(**overrides) -> SemiPresidentialConfig:
    """Russia / Weimar-style preset: president forms government and can dismiss PM."""
    return SemiPresidentialConfig(
        variant=VARIANT_PRESIDENT_PARLIAMENTARY,
        government_formation=GOV_FORMATION_PRESIDENT_DRIVEN,
        president_can_dismiss_pm=True,
        **overrides,
    )
