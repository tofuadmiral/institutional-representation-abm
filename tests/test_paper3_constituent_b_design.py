import copy

import pytest

from paper3 import coalition_contracts as game
from paper3 import constituent_b_design as design


def test_frame_is_reproducible_equal_standing_and_all_arm_crossed():
    first = design.frame(641001)
    assert first == design.frame(641001)
    assert len(first) == 4
    assert [item["family"] for item in first] == [row[0] for row in design.FAMILIES]
    assert all(item["prepared"]["equal_standing_specification"] == dict(
        citizens_per_district=9, priority_budget=4,
        coordinate_bound=5, citizen_count=63) for item in first)
    assignments = design.schedule(641001, 641100)
    assert len(assignments) == 12
    for item in first:
        profile_id = item["prepared"]["contract_profile"]["id"]
        assert {x["arm"] for x in assignments if x["profile_id"] == profile_id} == set(game.ARMS)
    assert design.frame(641001) == first


def test_constructed_opportunities_and_controls_are_not_conflated():
    for seed in range(641000, 641008):
        frame = design.frame(seed)
        assert frame[0]["strict_exchange_offers"] > 0
        assert frame[0]["strict_with_outsider_harm"] > 0
        assert frame[1]["strict_exchange_offers"] > 0
        assert frame[1]["strict_with_outsider_harm"] > 0
        assert frame[2]["strict_exchange_offers"] == 0
        assert frame[3]["strict_exchange_offers"] == 0
    frame = design.frame(641001)
    assert [sorted(item["actor_types"]) for item in frame[:3]] == [
        sorted(["A"] * 3 + ["B"] * 3 + ["X"])] * 3
    changed = design.frame(641002)
    assert [item["actor_types"] for item in changed] != [
        item["actor_types"] for item in frame]
    assert sorted(tuple(sorted(row.items())) for item in frame[:2]
                  for row in item["prepared"]["contract_profile"]["utilities"]) != sorted(
        tuple(sorted(row.items())) for item in changed[:2]
        for row in item["prepared"]["contract_profile"]["utilities"])


def test_no_input_alias_or_invalid_seed():
    frame = design.frame(641001)
    old = copy.deepcopy(frame[0]["prepared"]["electorate_profile"])
    frame[0]["prepared"]["electorate_profile"]["districts"]["r0"][0]["ideal"][0] = 999
    assert design.frame(641001)[0]["prepared"]["electorate_profile"] == old
    for seed in (-1, True, 0.5, "1"):
        with pytest.raises(ValueError):
            design.frame(seed)


def test_schedule_rejects_invalid_seed_base():
    for seed_base in (-1, True, 0.5, "1"):
        with pytest.raises(ValueError):
            design.schedule(641001, seed_base)
