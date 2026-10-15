"""Candidate schedule/analysis tests; no hosted actions."""
from __future__ import annotations

import json

from paper3 import direct_ratification as institution
from paper3 import ratification_population_analysis as analysis
from paper3 import ratification_population_schedule as schedule


def _records(stage, *, alternate_veto_binding=True):
    result = {}
    for row in schedule.assignments(stage):
        policy = (row["alternative_a"] if
                  alternate_veto_binding and row["distribution"] == "veto" and
                  row["arm"] == "binding_ratification" else row["favorite"])
        result[row["id"]] = dict(complete=True,
                                 outcome=dict(final_policy=policy,
                                              enacted_policy=policy))
    return result


def test_schedule_has_four_matched_arms_per_game_and_disjoint_seeds():
    discovery = schedule.assignments("discovery")
    validation = schedule.assignments("validation")
    assert len(discovery) == 36
    assert len(validation) == 60
    assert set(schedule.game_ids("discovery")).isdisjoint(
        schedule.game_ids("validation"))
    assert len(schedule.profiles("discovery")) == 18
    assert len(schedule.profiles("validation")) == 30
    assert discovery == schedule.assignments("discovery")
    for stage, rows in (("discovery", discovery), ("validation", validation)):
        for game_id in schedule.game_ids(stage):
            cells = {(row["distribution"], row["arm"])
                     for row in rows if row["game_id"] == game_id}
            assert cells == {(distribution, arm)
                             for distribution in ("veto", "approve")
                             for arm in institution.ARMS}
    seeds = [row["seed_base"] + i for row in discovery + validation
             for i in range(schedule.CALLS_PER_EPISODE)]
    assert len(seeds) == len(set(seeds)) == 1536


def test_expected_behavior_passes_strict_discovery_screen():
    result = analysis.readout("discovery", _records("discovery"))
    assert result["strict_discovery_lead"] is True
    assert result["complete_games"] == 9
    assert result["mean_interaction_bound"] == [1, 1]
    assert result["positive_games"] == 9
    json.dumps(result, sort_keys=True)


def test_enactment_only_and_missing_cells_do_not_pass():
    rows = _records("discovery", alternate_veto_binding=False)
    assert analysis.readout("discovery", rows)["strict_discovery_lead"] is False
    first = schedule.assignments("discovery")[0]
    del rows[first["id"]]
    report = analysis.readout("discovery", rows)
    assert report["strict_discovery_lead"] is None
    assert report["complete_games"] == 8
    assert report["mean_interaction_bound"][0] < \
        report["mean_interaction_bound"][1]
