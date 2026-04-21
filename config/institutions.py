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


@dataclass(frozen=True)
class ParliamentaryConfig:
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
