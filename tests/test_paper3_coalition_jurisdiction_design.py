"""Offline only: verifies design mechanics, never model competence/effects."""
from copy import deepcopy
import itertools
import json

import pytest

from paper3 import coalition_contracts as game
from paper3 import coalition_jurisdiction_design as d


def test_structural_opportunities_and_unique_rows():
    expected = [(2, 2), (4, 3), (4, 4), (7, 7)]
    for p, counts in zip(d.fixtures(), expected):
        game.validate_profile(p)
        assert len({tuple(row.values()) for row in p["utilities"]}) == 7
        assert tuple(sum(row[k] > 0 for row in p["utilities"]) for k in ("A0", "B0")) == counts
    p = d.fixtures()[0]
    assert game.utility_vector(p, ("A0", "B0")) == [6, 6, 6, 6, -8, -8, -8]
    assert game.scripted_independent(p, dict(A="A0", B="B0"))["passed"] == []
    assert game.scripted_independent(d.fixtures()[1], dict(A="A0", B="B0"))["passed"] == ["A0"]
    assert game.scripted_independent(d.fixtures()[2], dict(A="A0", B="B0"))["passed"] == ["A0", "B0"]


@pytest.mark.parametrize("fixture", range(4))
@pytest.mark.parametrize("form", (0, 1))
def test_all_finite_outcomes_preserved(fixture, form):
    original = d.fixtures()[fixture]
    before = deepcopy(original)
    mapped = d.display_profile(original, form)
    roles, policies = d.maps(form)
    assert mapped["proposer"] == roles[original["proposer"]]
    for outcome in game.all_outcomes():
        renamed = tuple(policies[k] for k in outcome)
        assert d.canonical_utilities(game.utility_vector(mapped, renamed), form) == game.utility_vector(original, outcome)
    assert original == before


@pytest.mark.parametrize("form", (0, 1))
def test_all_offer_terms_roundtrip(form):
    roles, policies = d.maps(form)
    for a, b, first, coalition in itertools.product(
            game.PROJECTS["A"], game.PROJECTS["B"], ("A", "B"), ((), *game.COALITIONS)):
        source = dict(projects=dict(A=a, B=b), first=first, coalition=list(coalition))
        mapped = [policies[a], policies[b]]
        offer = dict(projects={p[0]: p for p in mapped},
                     first=policies[source["projects"][first]][0],
                     coalition=[roles[i] for i in coalition])
        assert d.canonical_offer(offer, form) == source


def test_message_encoding_is_only_information_change():
    for p, arm, actor in itertools.product(d.fixtures(), game.ARMS, game.ACTORS):
        original = game.messages(p, arm, actor, "draft", [])
        before = deepcopy(original)
        changed = d.labelled_messages(original)
        assert original == before and changed[0] == original[0]
        old, q = original[1]["content"].split("\n", 1)
        new, q2 = changed[1]["content"].split("\n", 1)
        old, new = json.loads(old), json.loads(new)
        rows = old.pop("utilities_for_all_principals")
        mapping = new.pop("utilities_for_all_principals")
        assert old == new and q == q2 and rows == [mapping[str(i)] for i in range(7)]


def test_schedule_is_complete_paired_and_serializable():
    assignments = d.schedule(tuple(range(1000, 1800, 100)))
    assert len(assignments) == len({a["id"] for a in assignments}) == 24
    assert json.loads(json.dumps(assignments)) == assignments
    for block in range(8):
        members = [a for a in assignments if a["block"] == block]
        assert {a["arm"] for a in members} == set(game.ARMS)
        assert len({a["seed_base"] for a in members}) == 1
        assert len({(a["fixture_index"], a["form"]) for a in members}) == 1


@pytest.mark.parametrize("bases", [(0,) * 8, tuple(range(8)), (-1, 100, 200, 300, 400, 500, 600, 700),
                                    (True, 100, 200, 300, 400, 500, 600, 700), (100, 200)])
def test_bad_seed_design_refused(bases):
    with pytest.raises(ValueError):
        d.schedule(bases)


def test_controller_unchanged_and_no_ordinary_vote_veto():
    offer = dict(projects=dict(A="A0", B="B0"), first="A", coalition=[0, 1, 2, 3], message="")
    events = [dict(type="final", action=offer),
              dict(type="consent", approvals=[True, True, True, True, False, False, False])]
    assert game.contract_state(events, "member_enforcement")["active"]
    assert not game.contract_state(events, "universal_clearance")["active"]
    voted = game.resolve_vote(events, "universal_clearance", [True] * 4 + [False] * 3, "first_vote")
    assert voted["passed"] and voted["changed_ballots"] == []


@pytest.mark.parametrize("arm", game.ARMS)
def test_complete_episode_adapter_preserves_engine_and_all_thirty_decisions(arm):
    seen = []
    offer = dict(projects=dict(A="A0", B="B0"), first="A", coalition=[0, 1, 2, 3], message="")
    def answer(actor, stage, messages, index):
        if stage in ("draft", "final"):
            return json.dumps(offer)
        if stage == "response":
            return json.dumps(dict(offer, support=True))
        return json.dumps({"consent": True} if stage == "consent" else {"vote": False})
    def labelled_answer(actor, stage, messages, index):
        record = json.loads(messages[1]["content"].split("\n", 1)[0])
        assert set(record["utilities_for_all_principals"]) == {str(i) for i in range(7)}
        seen.append(index)
        return answer(actor, stage, messages, index)
    profile = d.fixtures()[0]
    assert d.episode(profile, arm, labelled_answer) == game.episode(profile, arm, answer)
    assert seen == list(range(30))
