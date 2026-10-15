"""Pure offline arithmetic checks; not part of the live frozen protocol."""
from __future__ import annotations

from copy import deepcopy

import pytest

from analysis import paper3_ratification_population_independent_audit as audit
from paper3 import ratification_population_schedule as schedule
from paper3 import ratification_threshold_institution as game


def _episode(profile, arm):
    events = [dict(type="draft", actor=profile["proposer"],
                   action=dict(policy="X", message="")),
              dict(type="responses", responses=[]),
              dict(type="final", actor=profile["proposer"],
                   action=dict(policy="X", message="")),
              dict(type="vote", requested=[True] * 7)]
    return dict(id="fixture", status="completed", calls=16, events=events,
                outcome=game.base.score(profile, arm, events))


def test_independent_outcome_matches_on_both_sides_of_threshold():
    profiles = schedule.profiles("discovery")
    for assignment in schedule.assignments("discovery")[:8]:
        profile = profiles[assignment["profile_id"]]
        episode = _episode(profile, assignment["arm"])
        assert audit.independent_outcome(profile, assignment["arm"],
                                         episode["events"]) == episode["outcome"]


def test_tampered_citizen_outcome_is_rejected():
    assignments = schedule.assignments("discovery")
    profiles = schedule.profiles("discovery")
    episodes = {row["id"]: dict(id=row["id"], status="not_started")
                for row in assignments}
    first = assignments[0]
    complete = _episode(profiles[first["profile_id"]], first["arm"])
    complete["id"] = first["id"]
    episodes[first["id"]] = complete
    result = audit.independent_readout(assignments, profiles, episodes)
    assert result["complete_episodes"] == 1
    assert result["complete_games"] == 0
    altered = deepcopy(episodes)
    altered[first["id"]]["outcome"]["enacted_total_citizen_utility"] += 1
    with pytest.raises(ValueError, match="independent outcome mismatch"):
        audit.independent_readout(assignments, profiles, altered)
