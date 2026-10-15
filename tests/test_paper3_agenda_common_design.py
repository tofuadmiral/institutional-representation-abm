"""Pure offline tests; no model calls or scientific result implied."""
from collections import Counter
import json

import pytest

from paper3 import agenda_common_design as design
from paper3 import agenda_common_transcript as institution
from paper3 import agenda_sponsorship_institution as base_game


def test_profile_and_seed_inventory():
    items = design.profiles()
    assignments = design.assignments()
    assert len(items) == len(assignments) == 12
    assert Counter(item["structure"] for item in items) == {
        "split": 8, "aligned_y": 2, "aligned_c": 2}
    assert len({item["profile"]["id"] for item in items}) == 12
    assert all(item["draw_attempts"] >= 1 for item in items)
    assert {row["profile_id"] for row in assignments} == {
        item["profile"]["id"] for item in items}
    assert sum(row["intended_calls"] for row in assignments) == 396
    assert len({row["seed_base"] + i for row in assignments
                for i in range(33)}) == 396
    assert Counter(tuple(row["arm_order"]) for row in assignments) == {
        ("sealed", "public_sequential"): 6,
        ("public_sequential", "sealed"): 6}


def test_arm_blind_advocacy_and_shared_transcript():
    item = design.profiles()[0]
    calls = []

    def ask(actor, stage, messages, index):
        calls.append((actor, stage, index, messages))
        assert base_game.RULES["sealed"] not in messages[0]["content"]
        assert base_game.RULES["public_sequential"] not in messages[0]["content"]
        assert institution.NEUTRAL_RULE in messages[0]["content"]
        assert "reason privately" not in messages[0]["content"]
        assert json.loads(messages[1]["content"].split("\n", 1)[0])[
            "public_advocacy"] == []
        return json.dumps(dict(message=f"Representative {actor} advocacy"))

    transcript = institution.advocacy(item, ask)
    assert len(calls) == len(transcript) == 7
    assert [entry["actor"] for entry in transcript] == list(range(7))
    original = json.dumps(transcript, sort_keys=True)
    outcomes = {}

    for arm in base_game.ARMS:
        seen = []

        def action(actor, stage, messages, index):
            seen.append((stage, index, messages))
            record = json.loads(messages[1]["content"].split("\n", 1)[0])
            assert record["public_advocacy"] == transcript
            assert institution.NEUTRAL_RULE not in messages[0]["content"]
            if stage == "sponsor":
                return json.dumps(dict(policy=item["compromises"][0]))
            return json.dumps(dict(vote=True))

        result = institution.arm_episode(item, arm, transcript, action)
        assert result["calls"] == len(seen) == 13
        assert [stage for stage, _, _ in seen] == ["sponsor"] * 6 + ["vote"] * 7
        outcomes[arm] = result["outcome"]
    assert json.dumps(transcript, sort_keys=True) == original
    assert outcomes["sealed"]["enacted_policy"] == outcomes["public_sequential"][
        "enacted_policy"]
    assert outcomes["sealed"]["controller_changed_actions"] == 0


def fabricated(arm, total, floor, *, harmed=0):
    return dict(arm=arm, enacted_total_citizen_utility=total,
                qualified_motion=([floor] if floor != "q" else []),
                floor_policy=floor, enacted_policy=floor,
                harmed_citizen_count=harmed,
                enacted_district_utility={f"r{i}": total // 7
                                          for i in range(7)})


def test_two_sided_screen_and_missingness_bounds():
    items = design.profiles()
    outcomes = {}
    for item in items:
        pid = item["profile"]["id"]
        outcomes[pid, "sealed"] = fabricated("sealed", 0, "q")
        outcomes[pid, "public_sequential"] = (
            fabricated("public_sequential", 72, "X", harmed=9)
            if item["structure"] == "split" else
            fabricated("public_sequential", 0, "X"))
        if item["structure"] != "split":
            outcomes[pid, "sealed"] = fabricated("sealed", 0, "X")
    good = design.screen(outcomes)
    assert good["classification"] == "selected_case_public_benefit_lead"
    assert good["public_benefit_pairs"] == 8
    assert good["stable_control_pairs"] == 4
    split = [item for item in items if item["structure"] == "split"]
    outcomes[split[0]["profile"]["id"], "sealed"] = None
    one_missing = design.screen(outcomes)
    assert one_missing["beneficial_lead"]
    outcomes[split[1]["profile"]["id"], "sealed"] = None
    assert design.screen(outcomes)["classification"] == "incomplete_or_control_failed"
    for item in split:
        pid = item["profile"]["id"]
        outcomes[pid, "sealed"] = fabricated("sealed", 72, "X")
        outcomes[pid, "public_sequential"] = fabricated(
            "public_sequential", 0, "q")
    assert design.screen(outcomes)["classification"] == (
        "selected_case_public_harm_lead")


def test_opposite_welfare_even_without_floor_change_blocks_lead():
    items = design.profiles()
    outcomes = {}
    split = [item for item in items if item["structure"] == "split"]
    for item in items:
        pid = item["profile"]["id"]
        outcomes[pid, "sealed"] = fabricated("sealed", 0, "q")
        outcomes[pid, "public_sequential"] = (
            fabricated("public_sequential", 72, "X")
            if item["structure"] == "split" else
            fabricated("public_sequential", 0, "X"))
        if item["structure"] != "split":
            outcomes[pid, "sealed"] = fabricated("sealed", 0, "X")
    for item in split[:2]:
        pid = item["profile"]["id"]
        outcomes[pid, "public_sequential"] = fabricated(
            "public_sequential", -9, "q")
    report = design.screen(outcomes)
    assert report["public_benefit_pairs"] == 6
    assert report["negative_welfare_pairs"] == 2
    assert report["classification"] == "no_prespecified_constituent_lead"


def test_invalid_context_rejected():
    item = design.profiles()[0]
    with pytest.raises(ValueError, match="arm-blind"):
        institution.messages(item, "sealed", 0, "advocacy")
    with pytest.raises(ValueError, match="common advocacy"):
        institution.arm_episode(item, "sealed", [], lambda *_: "{}")
