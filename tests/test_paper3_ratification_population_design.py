"""Offline properties of the candidate citizen-ratification population."""
from __future__ import annotations

import json

import pytest

from paper3 import direct_ratification as game
from paper3 import ratification_population_design as design


def test_population_is_reproducible_and_structurally_varied():
    first = design.inventory()
    assert first == design.inventory()
    assert len(first) == 24
    assert len({json.dumps(item["veto"], sort_keys=True) for item in first}) == 24
    assert {len(item["favorite_seats"]) for item in first} == {4, 5, 6}
    assert len({item["proposer"] for item in first}) >= 4
    assert len({item["outsider"] for item in first}) >= 4
    assert {item["favorite"] for item in first} == set(game.POLICIES)
    assert {item["alternative_a"] for item in first} == set(game.POLICIES)
    assert {item["alternative_b"] for item in first} == set(game.POLICIES)
    assert {len(item["alternative_a_seats"]) for item in first} == {4, 5}
    assert {len(item["alternative_b_seats"]) for item in first} == {4, 5}


def test_each_pair_has_identical_mandates_and_one_pivotal_majority():
    for item in design.inventory():
        veto, approve = item["veto"], item["approve"]
        favorite = item["favorite"]
        outsider = f"r{item['outsider']}"
        assert game.district_totals(veto) == game.district_totals(approve)
        assert game.poll(veto, favorite)["yes_counts"][outsider] == 4
        assert game.poll(approve, favorite)["yes_counts"][outsider] == 5
        assert not game.poll(veto, favorite)["approved"]
        assert game.poll(approve, favorite)["approved"]
        for policy, supporters in (
                (item["alternative_a"], item["alternative_a_seats"]),
                (item["alternative_b"], item["alternative_b_seats"])):
            assert game.poll(veto, policy)["approved"]
            assert game.poll(approve, policy)["approved"]
            assert {actor for actor in game.ACTORS
                    if game.district_totals(veto)[f"r{actor}"][policy] > 0} == \
                set(supporters)
            assert len(supporters) in (4, 5)
        for district, count in game.poll(veto, favorite)["yes_counts"].items():
            if district != outsider:
                assert count >= 5
        totals = game.district_totals(veto)
        assert sum(row[favorite] > 0 for row in totals.values()) >= 4
        proposer_totals = totals[f"r{item['proposer']}"]
        assert proposer_totals[favorite] > \
            max(proposer_totals[item["alternative_a"]],
                proposer_totals[item["alternative_b"]])
        assert proposer_totals[item["alternative_a"]] != \
            proposer_totals[item["alternative_b"]]


def test_invalid_ids_are_not_silently_wrapped():
    for game_id in (-1, 24, 1.0):
        with pytest.raises(ValueError):
            design.game_pair(game_id)
