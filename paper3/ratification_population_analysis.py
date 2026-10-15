"""Prospective paired-action statistic and missingness bounds for ratification.

No inference is made from controller enactment alone. The independent unit is
the payoff game; four arms within a game are paired, not four observations.
"""
from __future__ import annotations

from paper3 import direct_ratification as institution
from paper3 import ratification_population_schedule as schedule


CELL_TERMS = (
    ("veto", "binding_ratification", 1),
    ("veto", "advisory_poll", -1),
    ("approve", "binding_ratification", -1),
    ("approve", "advisory_poll", 1),
)


def readout(stage, records):
    """Score all assigned cells, preserving incomplete cells and finite bounds.

    `records` maps assignment id to an episode record. A complete record must
    have a scored outcome with a legal final policy; no guessed policy is used
    for a missing or failed episode.
    """
    assigned = schedule.assignments(stage)
    expected = {row["id"] for row in assigned}
    if set(records) - expected:
        raise ValueError("unassigned episode records")
    by_game = {game_id: {} for game_id in schedule.game_ids(stage)}
    for row in assigned:
        record = records.get(row["id"])
        cell = (row["distribution"], row["arm"])
        outcome = None if record is None else record.get("outcome")
        complete = bool(record is not None and record.get("complete") is True
                        and isinstance(outcome, dict) and
                        outcome.get("final_policy") in institution.POLICIES)
        final_policy = outcome["final_policy"] if complete else None
        by_game[row["game_id"]][cell] = dict(
            assignment_id=row["id"], complete=complete,
            final_policy=final_policy,
            alternative_proposed=(final_policy != row["favorite"]
                                  if complete else None),
            outcome=outcome if complete else None,
            failure=None if record is None else record.get("failure"))
    games = []
    for game_id in schedule.game_ids(stage):
        cells = by_game[game_id]
        lower = upper = 0
        for distribution, arm, coefficient in CELL_TERMS:
            value = cells[(distribution, arm)]["alternative_proposed"]
            if value is None:
                lower += min(0, coefficient)
                upper += max(0, coefficient)
            else:
                lower += coefficient * int(value)
                upper += coefficient * int(value)
        complete = all(cell["complete"] for cell in cells.values())
        archive_cells = {f"{distribution}|{arm}": cell
                         for (distribution, arm), cell in cells.items()}
        games.append(dict(game_id=game_id, cells=archive_cells,
                          complete=complete,
                          interaction=lower if complete else None,
                          interaction_bound=[lower, upper]))
    n = len(games)
    complete = sum(item["complete"] for item in games)
    bounds = [sum(item["interaction_bound"][i] for item in games) / n
              for i in (0, 1)]
    lead = None
    if stage == "discovery" and complete == len(games):
        positives = sum(item["interaction"] > 0 for item in games)
        negatives = sum(item["interaction"] < 0 for item in games)
        corner_counts = {
            f"{distribution}|{arm}": sum(
                item["cells"][f"{distribution}|{arm}"]["alternative_proposed"]
                for item in games)
            for distribution in ("veto", "approve")
            for arm in institution.ARMS
        }
        lead = (positives >= 7 and negatives <= 1 and
                corner_counts["veto|binding_ratification"] >= 7 and
                corner_counts["veto|advisory_poll"] <= 2 and
                corner_counts["approve|binding_ratification"] <= 2 and
                corner_counts["approve|advisory_poll"] <= 2)
    else:
        positives = negatives = None
        corner_counts = None
    return dict(stage=stage, assigned_episodes=len(assigned),
                complete_episodes=sum(cell["complete"]
                                      for item in games for cell in item["cells"].values()),
                independent_games=n, complete_games=complete,
                mean_interaction_bound=bounds, games=games,
                positive_games=positives, negative_games=negatives,
                corner_alternative_counts=corner_counts,
                strict_discovery_lead=lead,
                caveat="A positive discovery screen is selected-run mechanism evidence, not publication confirmation. Policy/citizen outcomes must be audited separately; referendum enactment alone is mechanical.")
