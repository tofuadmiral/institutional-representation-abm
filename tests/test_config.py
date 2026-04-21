from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from config import (
    CommitteeConfig,
    LegislatorConfig,
    ParliamentaryConfig,
    RepublicanConfig,
)


def test_configs_are_frozen():
    parl = ParliamentaryConfig()
    with pytest.raises(FrozenInstanceError):
        parl.discipline_strength = 0.1  # type: ignore[misc]

    rep = RepublicanConfig()
    with pytest.raises(FrozenInstanceError):
        rep.override_threshold_fraction = 0.5  # type: ignore[misc]


def test_nested_config_factories_produce_independent_instances():
    a = ParliamentaryConfig()
    b = ParliamentaryConfig()
    assert a.committee is not b.committee
    assert a.legislator is not b.legislator


def test_parliamentary_config_defaults():
    c = ParliamentaryConfig()
    assert c.confidence_threshold == 0.5
    assert c.discipline_strength == 0.8
    assert c.opposition_discipline_multiplier == 0.7
    assert c.confidence_matter_rate == 0.3
    assert c.legislative_activity_rate == 0.2
    assert c.num_committees == 3
    assert c.committee_size == 5


def test_republican_config_defaults():
    c = RepublicanConfig()
    assert c.discipline_strength == 0.4
    assert c.executive_opposition_rate == 0.3
    assert c.largest_party_presidency_prob == 0.7
    assert c.max_veto_probability == 0.8
    assert c.veto_distance_scale == 2.0
    assert c.override_threshold_fraction == pytest.approx(0.67)
    assert c.legislative_activity_rate == 0.3


def test_committee_config_defaults():
    c = CommitteeConfig()
    assert c.strong_support_threshold == 0.6
    assert c.moderate_support_threshold == 0.4
    assert c.min_support_probability == 0.1
    assert c.amendment_strength == 0.3


def test_legislator_config_defaults():
    c = LegislatorConfig()
    assert c.vote_support_threshold == 1.0
