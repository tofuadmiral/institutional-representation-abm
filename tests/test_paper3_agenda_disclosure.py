import json

import pytest

from paper3 import agenda_rights as game
from paper3 import agenda_disclosure as late
from paper3.agenda_benchmarks import generated_profile


def scripted_ask(profile, choose):
    """Fabricated responses only; returns a valid action for every stage."""
    calls = []
    def ask(messages, position):
        calls.append((messages, position))
        context = json.loads(messages[1]["content"].split("\n", 1)[0])
        stage = context["stage"]
        candidates = context.get("candidate_policy_ids")
        if stage == "ratification":
            return json.dumps(dict(votes={p: True for p in candidates}))
        pid = choose(context, stage, candidates)
        if stage == "pairwise":
            return json.dumps(dict(policy_id=pid))
        return json.dumps(dict(policy_id=pid, message="ok"))
    return ask, calls


def fixed(context, stage, candidates):
    if candidates:
        return candidates[-1]
    return {"opening": "p1", "responses": "p2", "locked_proposal": "p3", "amendment": "p4"}[stage]


def test_rule_text_splits_into_shared_parts_and_two_selectors():
    prefix, selectors, suffix = late.rule_parts()
    for arm in game.ARMS:
        assert prefix + selectors[arm] + suffix == game.rules(arm)
    undrawn = late.rules_late(None)
    assert selectors["D"] in undrawn and selectors["B"] in undrawn
    assert "1/2" in undrawn and "After the leader's locked proposal" in undrawn
    for arm in game.ARMS:
        drawn = late.rules_late(arm)
        assert drawn.startswith(undrawn)
        assert late.DRAWN[arm] in drawn and late.DRAWN[game.ARMS[1 - game.ARMS.index(arm)]] not in drawn


def test_late_messages_differ_from_early_only_in_rule_text():
    profile = game.profiles()[0]
    early = game.messages(profile, "D", "r3", "responses", [])
    lottery = late.messages_late(profile, "r3", "responses", [], None)
    assert lottery[1] == early[1]
    assert lottery[0]["content"] == early[0]["content"].replace(game.rules("D"), late.rules_late(None))
    assert game.rules("D") not in lottery[0]["content"] and game.rules("B") not in lottery[0]["content"]


def test_prefix_never_reveals_rule_and_branches_share_exact_prefix():
    profile = game.profiles()[0]
    ask, calls = scripted_ask(profile, fixed)
    result = late.run_late(profile, ask, ("D", "B"))
    assert result["status"] == "completed"
    prefix = [c for c in calls if c[1] < late.PREFIX_DECISIONS]
    assert len(prefix) == 9 and len(calls) == 9 + 16 + 16
    for messages, _ in prefix:
        system = messages[0]["content"]
        assert late.rules_late(None) in system
        assert all(late.DRAWN[a] not in system for a in game.ARMS)
        assert "authority_draw" not in messages[1]["content"]
    for arm in game.ARMS:
        branch = result["branches"][arm]
        assert branch["status"] == "completed"
        assert [a["stage"] for a in branch["actions"]][:9] == ["opening"] + ["responses"] * 7 + ["locked_proposal"]
        assert len(branch["actions"]) == 25
        assert branch["events"][:3] == result["prefix_events"]
        assert branch["events"][3] == dict(stage="authority_draw", rule=arm)
    positions = sorted(p for _, p in calls if p >= 9)
    assert positions == sorted(list(range(9, 25)) * 2)


def test_branch_resolution_uses_drawn_rule():
    profile = game.profiles()[0]
    # Every pairwise ballot favours the amendment p4; the leader selects p3.
    def choose(context, stage, candidates):
        if stage == "pairwise":
            return "p4"
        if stage == "leader_selection":
            return "p3"
        return fixed(context, stage, candidates)
    ask, _ = scripted_ask(profile, choose)
    result = late.run_late(profile, ask, ("B", "D"))
    assert result["branches"]["D"]["resolution"]["selected"] == "p3"
    assert result["branches"]["B"]["resolution"]["selected"] == "p4"
    assert result["branch_order"] == ["B", "D"]


def test_invalid_branch_action_fails_only_that_branch():
    profile = game.profiles()[0]
    ask, calls = scripted_ask(profile, fixed)
    def flaky(messages, position):
        context = json.loads(messages[1]["content"].split("\n", 1)[0])
        drawn = [e for e in context["official_events"] if e.get("stage") == "authority_draw"]
        if drawn and drawn[0]["rule"] == "D" and context["stage"] == "amendment":
            return "not json"
        return ask(messages, position)
    result = late.run_late(profile, flaky, ("D", "B"))
    assert result["branches"]["D"]["status"] == "failed"
    assert result["branches"]["B"]["status"] == "completed"
    assert result["status"] == "partial"


def test_prefix_failure_fails_both_branches_without_continuations():
    profile = game.profiles()[0]
    ask, calls = scripted_ask(profile, fixed)
    def broken(messages, position):
        if position == 4:
            return "{}"
        return ask(messages, position)
    result = late.run_late(profile, broken, ("D", "B"))
    assert result["status"] == "failed"
    assert all(result["branches"][a]["status"] == "failed" for a in game.ARMS)
    assert max(p for _, p in calls) < 9


def test_interaction_contrast():
    profile = generated_profile(1004003)
    outcomes = {"early": {"D": "p4", "B": "p3"}, "late": {"D": "p4", "B": "p4"}}
    result = late.interaction(profile, outcomes)
    m = {k: {a: game.metrics(profile, p) for a, p in v.items()} for k, v in outcomes.items()}
    expected = (m["late"]["B"]["mean_regret"] - m["late"]["D"]["mean_regret"]) - (
        m["early"]["B"]["mean_regret"] - m["early"]["D"]["mean_regret"])
    assert result["mean_regret_interaction"] == pytest.approx(expected)
    assert set(result["principal_utility_interaction"]) == set(game.ROLES)
    with pytest.raises(ValueError):
        late.interaction(profile, {"early": {"D": "p4"}, "late": outcomes["late"]})


def test_selection_rule_is_theory_only_and_reproducible():
    frame = late.select_profiles()
    assert frame["positive"] == [1004003, 1004007]
    assert frame["zero_control"] == [1004000, 1004005]
    assert late.select_profiles() == frame
