"""Prewritten hard-game classification checks, with fabricated actions only."""

from paper3 import ratification_disclosure_chamber_analysis as analysis
from paper3 import ratification_disclosure_chamber_design as design


def fabricated():
    profiles = {row["profile"]["id"]: row for row in design.profiles()}
    records = {}
    for assignment in design.assignments():
        item = profiles[assignment["profile_id"]]
        policy = ("C" if item["distribution"] == "veto" and
                  assignment["arm"] == "binding_ratification" else item["favorite"])
        records[(assignment["profile_id"], assignment["information"],
                 assignment["arm"])] = dict(
            status="completed", events=[], calls=16,
            outcome=dict(final_policy=policy, chamber_passed=True,
                         enacted_policy=policy))
    return records


def test_complete_fabricated_both_sufficient():
    report = analysis.readout(fabricated())
    result = analysis.discovery_screen(report)
    assert report["assignments"] == report["completed_episodes"] == 54
    assert result["coverage"]
    assert result["interpretable_selected_cases"]
    assert result["pathway"] == "both_sufficient_on_hard_games"
    assert result["private_veto_success"] == [True] * 6
    assert result["certified_veto_success"] == [True] * 6
    assert len(result["games"]) == 6


def test_certified_gain_keeps_all_games_and_decomposes_chamber_failure():
    records = fabricated()
    key = ("disclosure-chamber-0-veto", "private", "binding_ratification")
    records[key]["outcome"]["chamber_passed"] = False
    records[key]["outcome"]["enacted_policy"] = "q"
    result = analysis.discovery_screen(analysis.readout(records))
    assert result["pathway"] == "discordant_information_on_hard_games"
    assert result["certified_gain_game_ids"] == [0]
    assert result["private_veto_success"][0] is False
    assert result["games"][0]["comparisons"]["private"]["binding_veto_final_policy"] == "C"
    assert result["games"][0]["comparisons"]["private"]["binding_veto_chamber_passed"] is False


def test_failed_cell_and_failed_public_benchmark_are_not_rescued():
    records = fabricated()
    key = ("disclosure-chamber-0-veto", "private", "binding_ratification")
    records[key] = dict(status="failed", error="unusable_or_invalid_action")
    report = analysis.readout(records)
    result = analysis.discovery_screen(report)
    assert report["completed_episodes"] == 53
    assert not result["coverage"]
    assert result["pathway"] == "not_identified"
    failed = report["profiles"][1]["arms"]["private"]["binding_ratification"]
    assert failed["status"] == "failed"
    assert "finite_missingness_bounds" in failed

    records = fabricated()
    key = ("disclosure-chamber-0-veto", "public", "binding_ratification")
    records[key]["outcome"]["final_policy"] = "X"
    records[key]["outcome"]["enacted_policy"] = "q"
    result = analysis.discovery_screen(analysis.readout(records))
    assert not result["public_calibration"][0]
    assert result["pathway"] == "not_identified"
