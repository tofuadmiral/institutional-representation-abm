"""Offline implementation of the prewritten 15-game ratification holdout rule.

This module was prepared while the nine-game discovery run was live. It does
not alter that frozen protocol or authorize any model requests. The rule was
recorded in Obsidian before any complete discovery four-corner game.
"""
from __future__ import annotations

from paper3 import ratification_population_analysis as analysis
from paper3 import ratification_population_schedule as schedule


def readout(records):
    """Retain the frozen cell readout and apply the strict all-cell gate."""
    report = analysis.readout("validation", records)
    expected_games = len(schedule.game_ids("validation"))
    if expected_games != 15 or report["assigned_episodes"] != 60:
        raise ValueError("validation assignment inventory changed")
    if report["complete_games"] != expected_games:
        return dict(**report, holdout_positive_games=None,
                    holdout_negative_games=None,
                    holdout_corner_alternative_counts=None,
                    strict_holdout_lead=None)

    positives = sum(game["interaction"] > 0 for game in report["games"])
    negatives = sum(game["interaction"] < 0 for game in report["games"])
    corners = {
        cell: sum(int(game["cells"][cell]["alternative_proposed"])
                  for game in report["games"])
        for cell in ("veto|binding_ratification", "veto|advisory_poll",
                     "approve|binding_ratification", "approve|advisory_poll")
    }
    lead = (positives >= 11 and negatives <= 2 and
            corners["veto|binding_ratification"] >= 12 and
            all(corners[cell] <= 4 for cell in
                ("veto|advisory_poll", "approve|binding_ratification",
                 "approve|advisory_poll")))
    return dict(**report, holdout_positive_games=positives,
                holdout_negative_games=negatives,
                holdout_corner_alternative_counts=corners,
                strict_holdout_lead=lead)
