"""Offline arithmetic/disclosure tests; never provider or scientific evidence."""
from copy import deepcopy
from dataclasses import asdict, replace
import json

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design
from paper3 import retrospective_score_ledger as ledger
from paper3 import retrospective_serialization_contract as contract
from paper3 import retrospective_message_budget as message_budget


def fixture(width=6):
    first = []
    second = []
    for d in range(7):
        if d % 3 == 2:
            values = (0,) * 9
        elif d % 2:
            values = (2,) * 5 + (-8,) * 4
        else:
            values = (-2,) * 5 + (8,) * 4
        first.append(tuple(tuple(0 if p == 0 else v if p % 2 else -v
                                  for p in range(width)) for v in values))
        second.append(tuple(tuple(0 if p == 0 else (p + d) % 5 - 2
                                   for p in range(width)) for _ in range(9)))
    return institution.Game("offline-ledger-engineering", (tuple(first), tuple(second)), (0, 3), 24)


def retained(game, arm, d, p):
    vals = [row[p] for row in game.utilities[0][d]]
    return arm.startswith("advisory") or (sum(v >= 0 for v in vals) >= 5
        if arm.endswith("majority") else sum(vals) >= 0)


def scripted(stage, p=1):
    if stage in ("draft", "final"):
        return dict(policy=p, message="offline")
    if stage == "response":
        return dict(support=False, counter_policy=0, message="offline")
    return dict(vote=True)


@pytest.mark.parametrize("width", range(2, 9))
@pytest.mark.parametrize("arm", institution.ARMS)
def test_every_first_term_joint_policy_score_against_independent_formula(width, arm):
    game = fixture(width)
    result = ledger.readout(game, arm, 0, [], tuple(map(institution.incumbent, range(7))))
    assert result["current_enactment_resolved"] is False
    assert result["future_enactment_resolved"] is False
    for d in range(7):
        district = result["districts"][f"district_{d}"]
        assert district["original_incumbent_retained"] is None
        assert district["resolved_office_bonus"] is None
        assert district["accrued_district_utility"] == 0
        assert district["future_utility_still_credited_after_removal"]
        policies = district["conditional_enacted_policies"]
        assert list(policies) == [f"policy_{p}" for p in range(width)]
        for p in range(width):
            keep = retained(game, arm, d, p)
            row = policies[f"policy_{p}"]
            assert row["current_district_utility"] == sum(v[p] for v in game.utilities[0][d])
            assert row["incumbent_retained_if_enacted"] == keep
            assert row["office_bonus_if_enacted"] == 24 * keep
            assert row["next_identity_if_enacted"] == (
                institution.incumbent(d) if keep else institution.successor(d))
            for q in range(width):
                expected = sum(v[p] for v in game.utilities[0][d]) + sum(v[q] for v in game.utilities[1][d]) + 24 * keep
                assert row["original_incumbent_score_by_future_enacted_policy"][f"policy_{q}"] == expected
    # Statusquo retains every incumbent, including zero-utility ties.
    assert all(result["districts"][f"district_{d}"]["conditional_enacted_policies"]
        ["policy_0"]["incumbent_retained_if_enacted"] for d in range(7))


@pytest.mark.parametrize("arm", institution.ARMS)
@pytest.mark.parametrize("alignment", ("aligned", "conflict"))
@pytest.mark.parametrize("yes", (True, False))
def test_thirty_actions_all_arms_preserve_payoffs_disclosure_schema_and_sealed_history(arm, alignment, yes):
    game = getattr(design.generate(9191001), alignment)
    seen = []
    def ask(actor, identity, term, stage, context, index):
        before = deepcopy(context)
        old = contract.messages(game, arm, actor, identity, term, stage, context)
        new = ledger.messages(game, arm, actor, identity, term, stage, context)
        assert context == before
        expected, actual = (json.loads(m[1]["content"]) for m in (old, new))
        readout = actual.pop("score_ledger")
        assert actual == expected  # Every role, history, payoff and task unchanged.
        assert new[0]["content"] == old[0]["content"] + ledger.NOTICE
        assert ledger.verify_readout(game, arm, term, actual["history"], actual["occupants"], readout) == readout
        assert ledger.structured(new, game, stage)["tools"] == contract.structured(old, game, stage)["tools"]
        assert ledger.structured(new, game, stage)["tool_choice"] == "auto"
        assert "requested" not in actual and "executed" not in actual
        if stage in ("draft", "response"):
            assert "responses" not in actual
        if stage in ("draft", "response", "final"):
            assert "final" not in actual
        value = scripted(stage)
        if stage == "vote":
            value["vote"] = yes
        # Adapter never executes a choice, clips a message, or overrides a vote.
        executed = message_budget.map_action(game, stage, value)["executed_action"]
        assert executed == value
        seen.append(readout)
        return value
    actual = institution.episode(game, arm, ask)
    expected = institution.episode(game, arm, lambda a, i, t, s, c, n:
        dict(vote=yes) if s == "vote" else scripted(s))
    assert asdict(actual) == asdict(expected)
    assert actual.calls == len(seen) == 30
    for d in range(7):
        row = seen[-1]["districts"][f"district_{d}"]
        assert row["accrued_district_utility"] == actual.terms[0].assessments[d].district_sum
        assert row["acting_identity"] == actual.terms[1].occupants[d]
        p = actual.terms[1].enacted
        consequence = row["conditional_enacted_policies"][f"policy_{p}"]
        assert consequence["original_incumbent_score_if_enacted"] == actual.initial_incumbent_scores[d]
        assert consequence["successor_score_if_enacted"] == actual.successor_scores[d]


@pytest.mark.parametrize("arm", institution.ARMS)
@pytest.mark.parametrize("width", range(2, 9))
def test_second_term_all_conditional_policies_not_just_actual_outcome(arm, width):
    game = fixture(width)
    episode = institution.episode(game, arm, lambda a, i, t, s, c, n: scripted(s))
    prior = episode.terms[0]
    value = ledger.readout(game, arm, 1, [asdict(prior)], prior.next_occupants)
    for d in range(7):
        past = sum(v[prior.enacted] for v in game.utilities[0][d])
        keep = retained(game, arm, d, prior.enacted)
        district = value["districts"][f"district_{d}"]
        for p in range(width):
            future = sum(v[p] for v in game.utilities[1][d])
            score = district["conditional_enacted_policies"][f"policy_{p}"]
            assert score["original_incumbent_score_if_enacted"] == past + future + 24 * keep
            assert score["successor_score_if_enacted"] == (None if keep else future)
            assert score["acting_identity_score_if_enacted"] == (past + future + 24 if keep else future)
    assert value["third_term_bonus"] == 0 and value["role_scores_are_not_a_shared_budget"]


@pytest.mark.parametrize("tamper", ("history", "roster", "bonus", "score", "recommendation", "bool"))
def test_invalid_public_history_roster_and_tampered_ledger_rejected(tamper):
    game = fixture()
    episode = institution.episode(game, "binding_majority", lambda a, i, t, s, c, n: scripted(s))
    history, occupants = [asdict(episode.terms[0])], episode.terms[0].next_occupants
    value = ledger.readout(game, "binding_majority", 1, history, occupants)
    if tamper == "history":
        history[0]["assessments"][0]["district_sum"] += 1
    elif tamper == "roster":
        occupants = tuple(map(institution.incumbent, range(7)))
    elif tamper == "bonus":
        value["districts"]["district_0"]["resolved_office_bonus"] += 1
    elif tamper == "score":
        value["districts"]["district_0"]["conditional_enacted_policies"]["policy_1"]["original_incumbent_score_if_enacted"] += 1
    elif tamper == "bool":
        value["districts"]["district_0"]["resolved_office_bonus"] = False
    else:
        value["recommended_policy"] = 1
    with pytest.raises(ValueError):
        ledger.verify_readout(game, "binding_majority", 1, history, occupants, value)


def test_removal_future_positive_negative_zero_and_zero_office_value():
    game = fixture()
    game = replace(game, office_value=0)
    ep = institution.episode(game, "binding_majority", lambda a, i, t, s, c, n: scripted(s))
    value = ledger.readout(game, "binding_majority", 1, [asdict(ep.terms[0])], ep.terms[0].next_occupants)
    d = value["districts"]["district_0"]
    assert d["original_incumbent_retained"] is False
    assert d["resolved_office_bonus"] == 0
    future = {row["current_district_utility"] for row in d["conditional_enacted_policies"].values()}
    assert any(x < 0 for x in future) and 0 in future and any(x > 0 for x in future)
    past = d["accrued_district_utility"]
    assert all(row["original_incumbent_score_if_enacted"] == past + row["current_district_utility"]
        for row in d["conditional_enacted_policies"].values())


@pytest.mark.parametrize("term", (True, -1, 2))
def test_invalid_term_never_coerced(term):
    with pytest.raises(ValueError):
        ledger.readout(fixture(), "advisory_sum", term, [], tuple(map(institution.incumbent, range(7))))


@pytest.mark.parametrize("tamper", ("ledger", "payoff", "stage"))
def test_structured_builder_revalidates_ledger_and_original_payoffs(tamper):
    game = fixture()
    captured = []
    def ask(actor, identity, term, stage, context, index):
        if index == 0:
            captured.append(ledger.messages(game, "binding_majority", actor, identity, term, stage, context))
        return scripted(stage)
    institution.episode(game, "binding_majority", ask)
    messages = captured[0]
    value = json.loads(messages[1]["content"])
    if tamper == "ledger":
        value["score_ledger"]["districts"]["district_0"]["accrued_district_utility"] = 1
    elif tamper == "payoff":
        card = value["payoff_cards"]["term_0"]["district_0"]["policy_1"]
        card["citizen_utilities"][0] += 1
        card["district_sum"] += 1
    else:
        value["stage"] = "vote"
    messages[1]["content"] = json.dumps(value)
    with pytest.raises(ValueError):
        ledger.structured(messages, game, "draft")
