"""Pure offline tests of the previously written holdout decision rule."""
from __future__ import annotations

from paper3 import ratification_population_holdout as holdout
from paper3 import ratification_population_schedule as schedule


def _records(positive_games=12, negative_games=1):
    records = {}
    for row in schedule.assignments("validation"):
        game_index = row["game_id"] - schedule.VALIDATION_IDS[0]
        alternative = (
            (game_index < positive_games and row["distribution"] == "veto" and
             row["arm"] == "binding_ratification") or
            (positive_games <= game_index < positive_games + negative_games and
             row["distribution"] == "veto" and
             row["arm"] == "advisory_poll")
        )
        records[row["id"]] = dict(
            complete=True,
            outcome=dict(final_policy=(row["alternative_a"] if alternative
                                       else row["favorite"])))
    return records


def test_complete_predeclared_pattern_passes():
    report = holdout.readout(_records())
    assert report["strict_holdout_lead"] is True
    assert report["complete_games"] == 15
    assert report["holdout_positive_games"] == 12
    assert report["holdout_negative_games"] == 1
    assert report["holdout_corner_alternative_counts"] == {
        "veto|binding_ratification": 12,
        "veto|advisory_poll": 1,
        "approve|binding_ratification": 0,
        "approve|advisory_poll": 0,
    }


def test_threshold_failure_and_missing_cell_remain_distinct():
    assert holdout.readout(_records(11, 1))["strict_holdout_lead"] is False
    assert holdout.readout(_records(12, 3))["strict_holdout_lead"] is False
    records = _records()
    del records[schedule.assignments("validation")[0]["id"]]
    report = holdout.readout(records)
    assert report["strict_holdout_lead"] is None
    assert report["complete_games"] == 14
    assert report["mean_interaction_bound"][0] < \
        report["mean_interaction_bound"][1]
