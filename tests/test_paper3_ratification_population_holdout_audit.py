"""Offline combined-audit gates; no hosted model data or calls."""
from __future__ import annotations

from pathlib import Path

import pytest

from analysis import paper3_ratification_population_holdout_audit as audit
from paper3 import ratification_population_schedule as schedule


def _fixture_batch(runner, positive_games=12, negative_games=1):
    rows = runner.assignments()
    records = {}
    for row in rows:
        index = row["game_id"] - schedule.VALIDATION_IDS[0]
        alternative = (
            (index < positive_games and row["distribution"] == "veto" and
             row["arm"] == "binding_ratification") or
            (positive_games <= index < positive_games + negative_games and
             row["distribution"] == "veto" and
             row["arm"] == "advisory_poll")
        )
        policy = row["alternative_a"] if alternative else row["favorite"]
        records[row["id"]] = dict(
            complete=True, outcome=dict(final_policy=policy),
            status="completed", failure=None)
    report = dict(assignments=[dict(id=row["id"], status="completed")
                               for row in rows],
                  completed_episodes=len(rows),
                  usable_actions=len(rows) * schedule.CALLS_PER_EPISODE,
                  feasibility_passed=True, accounted_usd="0.10",
                  global_safety_stop=False)
    return dict(protocol="a" * 64, report=report, records=records)


def _terminal(root):
    path = Path(root) / "sessions"
    path.mkdir(parents=True)
    (path / "terminal.json").write_text("{}")


def test_combined_rule_runs_only_after_both_terminal(tmp_path, monkeypatch):
    first_root, second_root = tmp_path / "first", tmp_path / "second"
    _terminal(first_root)
    with pytest.raises(ValueError, match="both holdout batches"):
        audit.readout(first_root, tmp_path / "first_archive",
                      second_root, tmp_path / "second_archive")
    _terminal(second_root)
    batches = iter((_fixture_batch(audit.first), _fixture_batch(audit.second)))
    monkeypatch.setattr(audit, "_verified_batch", lambda *args: next(batches))

    class FakeLedger:
        def __init__(self, root):
            self.root = root

        def snapshot(self):
            return dict(accounted_usd="4.50", pending=0)

    monkeypatch.setattr(audit, "Ledger", FakeLedger)
    result = audit.readout(first_root, tmp_path / "first_archive",
                           second_root, tmp_path / "second_archive")
    assert result["strict_holdout_lead"] is True
    assert result["behavioral"]["complete_games"] == 15
    assert result["behavioral"]["holdout_positive_games"] == 12
    assert result["combined_stage_cost_usd"] == "0.20"
    assert len(result["stages"]) == 2
