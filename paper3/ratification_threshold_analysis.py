"""Frozen candidate readout and strict spending screen for threshold pilot."""
from __future__ import annotations

from paper3 import direct_ratification_analysis as prior
from paper3 import ratification_threshold_design as design


def readout(records):
    rows = design.profiles()
    original = prior.readout(rows, records)
    keyed = {item["profile"]["id"]: item for item in rows}
    for item in original["profiles"]:
        frame = keyed[item["profile_id"]]
        item.update(game_id=frame["game_id"],
                    favorite=frame["favorite"],
                    distribution=frame["distribution"],
                    outsider=frame["outsider"],
                    welfare=frame["welfare"])
    original["limitation"] = (
        "Two theory-selected payoff games, each with the same district totals "
        "in 5/9 and 4/9 outsider distributions; two request-seed blocks reuse "
        "the exact same citizen tables. Citizens, calls and blocks are not "
        "independent payoff games. Enactment-only differences are mechanical.")
    return original


def spending_screen(report):
    """All-cell feasibility and four-corner interaction, not paper evidence."""
    rows = report["profiles"]
    if len(rows) != 8:
        raise ValueError("eight distribution/game/block pairs required")
    coverage = report["completed_episodes"] == 16 and all(
        row["contrast"]["completed"] for row in rows)
    decisions = []
    for row in rows:
        favorite = row["favorite"]
        expected = "C" if row["distribution"] == "veto" else favorite
        advisory = row["arms"]["advisory_poll"]
        binding = row["arms"]["binding_ratification"]
        expected_advisory = favorite
        passed = bool(
            row["contrast"]["completed"] and
            advisory["outcome"]["final_policy"] == expected_advisory and
            binding["outcome"]["final_policy"] == expected and
            # Both control arms must demonstrate a chamber route for the
            # favorite; otherwise ratification is not the sole obstacle.
            (row["distribution"] == "veto" or
             (advisory["outcome"]["chamber_passed"] and
              binding["outcome"]["chamber_passed"])) and
            (row["distribution"] != "veto" or
             (advisory["outcome"]["chamber_passed"] and
              binding["outcome"]["chamber_passed"])))
        decisions.append(dict(game_id=row["game_id"], block=row["block"],
                              distribution=row["distribution"],
                              expected_advisory=expected_advisory,
                              expected_binding=expected,
                              complete=row["contrast"]["completed"],
                              required_pattern=passed))
    return dict(coverage=coverage, corners=decisions,
                triage=coverage and all(row["required_pattern"]
                                        for row in decisions),
                caveat="Demanding prewritten spending screen on two selected games; True is not a population or paper result, False is not a general null.")
