"""Offline checks for chamber-pivotal disclosure opportunities."""

import json

import pytest

from paper3 import direct_ratification as base
from paper3 import ratification_disclosure_chamber_design as design
from paper3 import ratification_disclosure_validation_design as easy


def test_inventory_varies_support_and_is_fixed_before_model_inference():
    games = design.inventory()
    assert games == design.inventory()
    assert len(games) == 6
    assert [(len(game["favorite_support"]), len(game["compromise_support"]))
            for game in games] == list(design.SUPPORT_TARGETS)
    assert {game["favorite"] for game in games} == {"X", "Y"}
    assert len({json.dumps(game["approve"]["districts"], sort_keys=True)
                for game in games}) == 6
    assert any(game["welfare"][game["favorite"]] > game["welfare"]["C"]
               for game in games)
    assert any(game["welfare"][game["favorite"]] < game["welfare"]["C"]
               for game in games)


@pytest.mark.parametrize("game_id", range(6))
def test_chamber_and_citizen_votes_are_distinct_opportunities(game_id):
    game = design.game_pair(game_id)
    approve, veto = game["approve"], game["veto"]
    favorite = game["favorite"]
    outsider = f'r{game["outsider"]}'
    totals = base.district_totals(approve)
    assert totals == base.district_totals(veto)
    assert base.poll(approve, favorite)["approved"]
    assert not base.poll(veto, favorite)["approved"]
    assert base.poll(veto, "C")["approved"]
    assert base.poll(approve, favorite)["yes_counts"][outsider] == 5
    assert base.poll(veto, favorite)["yes_counts"][outsider] == 4
    assert {actor for actor in base.ACTORS if totals[f"r{actor}"][favorite] > 0} == set(game["favorite_support"])
    assert {actor for actor in base.ACTORS if totals[f"r{actor}"]["C"] > 0} == set(game["compromise_support"])
    assert any(totals[f"r{actor}"]["C"] < 0 and
               base.poll(veto, "C")["yes_counts"][f"r{actor}"] >= 5
               for actor in base.ACTORS)
    assert totals[f'r{game["proposer"]}'][favorite] > totals[f'r{game["proposer"]}']["C"] > 0
    assert totals[outsider][favorite] > totals[outsider]["C"] > 0
    assert all(approve["districts"][district] == veto["districts"][district]
               for district in approve["districts"] if district != outsider)


def test_invalid_games_rejected():
    for invalid in (-1, 6, True, "0"):
        with pytest.raises(ValueError):
            design.game_pair(invalid)


def test_hard_candidate_schedule_is_complete_and_disjoint_from_easy_schedule():
    rows = design.assignments()
    assert rows == design.assignments()
    assert len(rows) == 54
    assert len({row["id"] for row in rows}) == 54
    for game_id in range(6):
        game = [row for row in rows if row["game_id"] == game_id]
        assert len(game) == 9
        for distribution in ("approve", "veto"):
            selected = {(row["information"], row["arm"]) for row in game
                        if row["distribution"] == distribution}
            expected = {(information, arm)
                        for information in ("private", "certified")
                        for arm in base.ARMS}
            if distribution == "veto":
                expected.add(("public", "binding_ratification"))
            assert selected == expected
    seeds = {row["seed_base"] + index for row in rows for index in range(16)}
    easy_seeds = {row["seed_base"] + index for row in easy.assignments()
                  for index in range(16)}
    assert len(seeds) == 864
    assert seeds.isdisjoint(easy_seeds)
    assert seeds.isdisjoint(range(914000, 914816))
