"""Offline interface revision and fresh-profile checks; no model calls."""
import json

import pytest

from paper3 import agenda_common_design as prior
from paper3 import agenda_common_design_v2 as design
from paper3 import agenda_common_interface_v2 as interface


def test_bounded_advocacy_accepts_prior_failure_shape_without_reusing_answer():
    answer = json.dumps({"message": "x" * 574})
    assert interface.parse_action(answer, "advocacy", ("X", "Y")) == {
        "message": "x" * 574}
    assert interface.schema("advocacy", ("X", "Y"))["properties"][
        "message"]["maxLength"] == 1000
    with pytest.raises(ValueError, match="bounded advocacy"):
        interface.parse_action(json.dumps({"message": "x" * 1001}),
                               "advocacy", ("X", "Y"))
    with pytest.raises(ValueError, match="bounded advocacy"):
        interface.parse_action('{"message":"ok","reason":"extra"}',
                               "advocacy", ("X", "Y"))
    with pytest.raises(ValueError, match="duplicate"):
        interface.parse_action('{"message":"a","message":"b"}',
                               "advocacy", ("X", "Y"))


def test_fresh_profile_and_seed_inventory():
    old = prior.profiles()
    fresh = design.profiles()
    assignments = design.assignments()
    assert len(fresh) == len(assignments) == 12
    assert not ({item["profile"]["id"] for item in fresh} &
                {item["profile"]["id"] for item in old})
    assert set(design.PROFILE_SPECS) != set(prior.PROFILE_SPECS)
    assert sum(row["intended_calls"] for row in assignments) == 396
    assert len({row["seed_base"] + i for row in assignments
                for i in range(33)}) == 396


def test_v2_same_scientific_screen_as_preoutcome_v1():
    original = {}
    fresh = {}
    for old_item, new_item in zip(prior.profiles(), design.profiles(), strict=True):
        for arm in ("sealed", "public_sequential"):
            outcome = dict(arm=arm, qualified_motion=["X"],
                           floor_policy="X", enacted_policy="X",
                           enacted_total_citizen_utility=42,
                           harmed_citizen_count=0,
                           enacted_district_utility={f"r{i}": 6
                                                     for i in range(7)})
            original[old_item["profile"]["id"], arm] = outcome
            fresh[new_item["profile"]["id"], arm] = outcome
    def compare():
        previous = prior.screen(original)
        revised = design.screen(fresh)
        for key in ("classification", "split_pairs_complete",
                    "stable_control_pairs", "public_benefit_pairs",
                    "public_harm_pairs", "negative_welfare_pairs",
                    "positive_welfare_pairs", "missing_split_pairs",
                    "beneficial_lead", "harmful_lead"):
            assert revised[key] == previous[key]
        return revised["classification"]

    assert compare() == "no_prespecified_constituent_lead"
    split = [(old, new) for old, new in zip(prior.profiles(), design.profiles(),
                                            strict=True)
             if old["structure"] == "split"]
    for old, new in split:
        for outcomes, item in ((original, old), (fresh, new)):
            pid = item["profile"]["id"]
            outcomes[pid, "sealed"] = dict(arm="sealed", qualified_motion=[],
                                            floor_policy="q", enacted_policy="q",
                                            enacted_total_citizen_utility=0,
                                            harmed_citizen_count=0,
                                            enacted_district_utility={
                                                f"r{i}": 0 for i in range(7)})
            outcomes[pid, "public_sequential"] = dict(
                arm="public_sequential", qualified_motion=["X"],
                floor_policy="X", enacted_policy="X",
                enacted_total_citizen_utility=72, harmed_citizen_count=9,
                enacted_district_utility={f"r{i}": 10 for i in range(7)})
    assert compare() == "selected_case_public_benefit_lead"
    for outcomes, item in ((original, split[0][0]), (fresh, split[0][1])):
        outcomes[item["profile"]["id"], "sealed"] = None
    assert compare() == "selected_case_public_benefit_lead"
    for outcomes, item in ((original, split[1][0]), (fresh, split[1][1])):
        outcomes[item["profile"]["id"], "public_sequential"][
            "enacted_total_citizen_utility"] = -1
    assert compare() == "no_prespecified_constituent_lead"
