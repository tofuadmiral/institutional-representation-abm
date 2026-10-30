"""Offline checks for untouched disclosure-validation opportunities."""

import json

import pytest

from paper3 import direct_ratification as base
from paper3 import ratification_disclosure_validation_design as design


def test_independent_game_inventory_is_deterministic_and_not_two_templates():
    games = design.inventory()
    assert games == design.inventory()
    assert len(games) == 6
    assert [game["roles"].count("favorite") for game in games] == [4, 5, 6, 4, 5, 6]
    assert {game["favorite"] for game in games} == {"X", "Y"}
    assert {game["proposer"] for game in games} >= {2, 3, 4, 6}
    tables = [json.dumps(game["approve"]["districts"], sort_keys=True)
              for game in games]
    assert len(set(tables)) == len(tables)
    assert any(game["welfare"][game["favorite"]] < game["welfare"]["C"]
               for game in games)
    assert any(game["welfare"][game["favorite"]] > game["welfare"]["C"]
               for game in games)


@pytest.mark.parametrize("game_id", range(6))
def test_veto_margin_changes_without_aggregate_or_other_district_change(game_id):
    game = design.game_pair(game_id)
    approve, veto = game["approve"], game["veto"]
    favorite = game["favorite"]
    outsider = f'r{game["outsider"]}'
    assert base.district_totals(approve) == base.district_totals(veto)
    assert base.district_totals(approve)[outsider][favorite] > base.district_totals(approve)[outsider]["C"]
    assert base.poll(approve, favorite)["yes_counts"][outsider] == 5
    assert base.poll(veto, favorite)["yes_counts"][outsider] == 4
    assert base.poll(approve, favorite)["approved"]
    assert not base.poll(veto, favorite)["approved"]
    assert base.poll(veto, "C")["approved"]
    assert all(approve["districts"][key] == veto["districts"][key]
               for key in approve["districts"] if key != outsider)
    assert len({citizen["id"] for district in approve["districts"].values()
                for citizen in district}) == 63


def test_seed_and_game_id_guardrails():
    for invalid in (-1, 6, True, "0"):
        with pytest.raises(ValueError):
            design.game_pair(invalid)
    with pytest.raises(ValueError):
        design.game_pair(0, seed="not-an-integer")


def test_candidate_schedule_is_complete_and_seed_disjoint_from_discovery():
    rows = design.assignments()
    assert rows == design.assignments()
    assert len(rows) == 54
    assert len({row["id"] for row in rows}) == 54
    assert {row["intended_calls"] for row in rows} == {16}
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
    assert len(seeds) == 864
    assert seeds.isdisjoint(range(914000, 914816))
