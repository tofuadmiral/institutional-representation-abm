"""Offline action, visibility, and scoring tests for the new institution."""
from __future__ import annotations

import json

from paper3 import agenda_sponsorship_institution as institution
from paper3 import agenda_sponsorship_opportunity as opportunity
from paper3 import direct_ratification as base


def _item():
    return opportunity.with_order(
        opportunity.draw("split", "y_high", 2026093044),
        "flexible_last", 44)


def _sincere(item):
    return [dict(actor=actor, policy=opportunity.certificate(item)[
                "sincere_sponsors"][actor])
            for actor in item["sponsor_order"]]


def _votes(item, policy):
    totals = base.district_totals(item["profile"])
    return [totals[f"r{actor}"][policy] > 0 for actor in base.ACTORS]


def _advocacy():
    return [dict(actor=actor, message="test") for actor in base.ACTORS]


def test_split_sponsorship_and_one_flexible_concession():
    item = _item()
    sincere = _sincere(item)
    assert list(institution.motion(item, sincere)["counts"].values()) == [3, 3]
    fallback = item["favorite"]
    q = institution.score(item, "sealed", _advocacy(), sincere,
                          _votes(item, fallback))
    assert q["floor_policy"] == fallback
    assert q["enacted_policy"] == "q"
    assert q["enacted_total_citizen_utility"] == 0
    y, c = item["compromises"]
    for target in (y, c):
        changed = [dict(entry) for entry in sincere]
        mover = next(entry for entry in changed
                     if entry["actor"] in item["flexible"] and
                     entry["policy"] != target)
        mover["policy"] = target
        result = institution.score(item, "public_sequential", _advocacy(), changed,
                                   _votes(item, target))
        assert result["qualified_motion"] == [target]
        assert result["floor_policy"] == result["enacted_policy"] == target
        assert result["chamber_passed"] is True
        assert result["harmed_citizen_count"] == 18
        assert result["controller_changed_actions"] == 0


def test_identical_advocacy_information_and_sponsorship_visibility():
    item = _item()
    actor = item["sponsor_order"][1]
    sealed_opening = institution.messages(item, "sealed", actor,
                                          "advocacy", None)
    public_opening = institution.messages(item, "public_sequential", actor,
                                          "advocacy", None)
    assert sealed_opening[1] == public_opening[1]
    advocacy = _advocacy()
    prefix = [dict(actor=item["sponsor_order"][0],
                   policy=item["compromises"][0])]
    sealed = institution.messages(item, "sealed", actor, "sponsor",
                                  advocacy, prefix)
    public = institution.messages(item, "public_sequential", actor,
                                  "sponsor", advocacy, prefix)
    sealed_data = json.loads(sealed[1]["content"].split("\n", 1)[0])
    public_data = json.loads(public[1]["content"].split("\n", 1)[0])
    assert sealed_data["visible_formal_sponsorships"] == []
    assert public_data["visible_formal_sponsorships"] == prefix
    assert sealed_data["announced_sponsor_order"] == list(item["sponsor_order"])
    assert public_data["announced_sponsor_order"] == list(item["sponsor_order"])
    assert {key: value for key, value in sealed_data.items()
            if key != "visible_formal_sponsorships"} == {
            key: value for key, value in public_data.items()
            if key != "visible_formal_sponsorships"}


def test_complete_scripted_episode_keeps_every_action():
    item = _item()
    sincere = opportunity.certificate(item)["sincere_sponsors"]
    totals = base.district_totals(item["profile"])

    def ask(actor, stage, messages, index):
        assert len(messages) == 2 and index < 20
        if stage == "advocacy":
            return json.dumps({"message": f"district {actor}"})
        if stage == "sponsor":
            return json.dumps({"policy": sincere[actor]})
        floor = json.loads(messages[1]["content"].split("\n", 1)[0])[
            "floor_policy"]
        return json.dumps({"vote": totals[f"r{actor}"][floor] > 0})

    result = institution.episode(item, "sealed", ask)
    assert result["calls"] == 20
    assert len(result["advocacy"]) == 7
    assert len(result["sponsorships"]) == 6
    assert len(result["votes"]) == 7
    assert result["outcome"]["enacted_policy"] == "q"


def test_action_parser_rejects_extra_or_illegal_fields():
    compromises = ("Y", "C")
    for raw in ('{"policy":"X"}', '{"policy":"Y","why":"because"}',
                '{"policy":"Y","policy":"C"}'):
        try:
            institution.parse_action(raw, "sponsor", compromises)
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError("illegal sponsorship accepted")
    assert institution.parse_action(json.dumps({"message": "x" * 500}),
                                    "advocacy", compromises)["message"] == "x" * 500
    for text in ("x" * 501, "\\" * 300, "☃" * 100):
        try:
            institution.parse_action(json.dumps({"message": text}),
                                     "advocacy", compromises)
        except ValueError:
            pass
        else:
            raise AssertionError("oversized serialized advocacy accepted")
