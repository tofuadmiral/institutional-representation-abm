"""No-model state/benchmark tests for the separate prospective Pivot B engine."""
import copy
import itertools
import json
from fractions import Fraction

import pytest

from paper3 import coalition_contracts as c


def offer(coalition=(0, 1, 3, 4), first="A"):
    return dict(projects=dict(A="A0", B="B0"), first=first,
                coalition=list(coalition), message="fixture")


def history(approvals=None, coalition=(0, 1, 3, 4), first="A"):
    return [dict(type="final", actor=0, action=offer(coalition, first)),
            dict(type="consent", approvals=approvals if approvals is not None else [True]*7)]


@pytest.mark.parametrize("arm", c.ARMS)
def test_activation_all_consent_patterns(arm):
    for bits in itertools.product((False, True), repeat=7):
        h = history(list(bits))
        expected = all(bits) if arm == "universal_clearance" else all(bits[i] for i in (0, 1, 3, 4))
        state = c.contract_state(h, arm)
        assert state["active"] == expected
        assert state["due"] == ([0, 1, 3, 4] if expected else [])


@pytest.mark.parametrize("arm", c.ARMS)
def test_all_requested_ballots_resolve_exactly(arm):
    h = history()
    for bits in itertools.product((False, True), repeat=7):
        e = c.resolve_vote(h, arm, list(bits), "first_vote")
        expected = [bool(bits[i] or (arm != "public_promise" and i in (0, 1, 3, 4))) for i in c.ACTORS]
        assert e["requested"] == list(bits)
        assert e["executed"] == expected
        assert e["passed"] == (sum(expected) >= 4)
        assert e["changed_ballots"] == [i for i in c.ACTORS if expected[i] != bits[i]]
        state = c.contract_state(h+[e], arm)
        due = e["passed"] and all(expected[i] for i in (0, 1, 3, 4))
        assert state["due"] == ([0, 1, 3, 4] if due else [])


def test_nonpivotal_member_breach_lapses_promise():
    h = history()
    e = c.resolve_vote(h, "public_promise", [False, True, True, True, True, False, False], "first_vote")
    assert e["passed"]
    assert not c.contract_state(h+[e], "public_promise")["due"]


@pytest.mark.parametrize("arm", c.ARMS)
def test_empty_contract_never_activates(arm):
    h = history(coalition=())
    assert not c.contract_state(h, arm)["active"]
    e = c.resolve_vote(h, arm, [False]*7, "first_vote")
    assert not e["passed"] and not e["enforced_members"]


def test_outsider_clearance_is_not_outsider_vote_commitment():
    e = c.resolve_vote(history(), "universal_clearance", [False]*7, "first_vote")
    assert e["executed"] == [True, True, False, True, True, False, False]
    h = history([True, True, True, True, True, True, False])
    assert c.contract_state(h, "member_enforcement")["active"]
    assert not c.contract_state(h, "universal_clearance")["active"]


def test_execution_order_is_explicit_not_dictionary_order():
    h = history(first="B")
    one = c.resolve_vote(h, "member_enforcement", [False]*7, "first_vote")
    two = c.resolve_vote(h+[one], "member_enforcement", [False]*7, "second_vote")
    assert (one["project"], two["project"]) == ("B0", "A0")
    assert c.contract_state(h+[one, two], "member_enforcement")["status"] == "completed"


@pytest.mark.parametrize("edit", [
    lambda v: v.update(coalition=[0, 0, 3, 4]),
    lambda v: v.update(coalition=[True, 1, 3, 4]),
    lambda v: v.update(coalition=[0, 1, 3]),
    lambda v: v.update(coalition=[0, 1, 3, 7]),
    lambda v: v.update(first="A0"),
    lambda v: v.update(projects={"A": "B0", "B": "A0"}),
    lambda v: v.update(message="x"*601),
    lambda v: v.update(extra="instruction"),
])
def test_invalid_offers_are_not_repaired(edit):
    v = offer(); edit(v)
    with pytest.raises(ValueError):
        c.parse_action(json.dumps(v), "final")


@pytest.mark.parametrize("raw", ['{"vote":1}', '{"vote":"yes"}',
    '{"vote":false,"vote":true}', '```json\n{"vote":true}\n```',
    '{"vote":NaN}', '{"vote":true} extra'])
def test_strict_vote_parse(raw):
    with pytest.raises(ValueError):
        c.parse_action(raw, "first_vote")


@pytest.mark.parametrize("p", c.fixtures(), ids=lambda p:p["id"])
@pytest.mark.parametrize("arm", c.ARMS)
def test_episode_seals_stages_and_preserves_requests(p, arm):
    requests = []
    def ask(actor, stage, messages, index):
        requests.append((actor, stage, copy.deepcopy(messages), index))
        if stage in ("draft", "final", "response"):
            value = offer()
            if stage == "response": value["support"] = True
        elif stage == "consent": value = dict(consent=True)
        else: value = dict(vote=False)
        return json.dumps(value)
    result = c.episode(p, arm, ask)
    assert len(requests) == result["calls"] == 30
    assert [r[3] for r in requests] == list(range(30))
    for stage in ("response", "consent", "first_vote", "second_vote"):
        bodies = [json.loads(r[2][1]["content"].split("\n", 1)[0]) for r in requests if r[1] == stage]
        assert len(bodies) == 7
        assert all(b["events"] == bodies[0]["events"] for b in bodies)
        assert all(b["public_contract_register"] == bodies[0]["public_contract_register"] for b in bodies)
    assert result["outcome"]["passed"] == ([] if arm == "public_promise" else ["A0", "B0"])
    assert 0 <= Fraction(result["outcome"]["mean_normalized_regret"]) <= 1


def test_invalid_call_terminates_no_scripted_replacement():
    calls = []
    def ask(*args):
        calls.append(args)
        return '{"vote":true}'
    with pytest.raises(ValueError):
        c.episode(c.fixtures()[0], c.ARMS[0], ask)
    assert len(calls) == 1


def test_outcome_universe_and_inventory():
    assert len(c.all_outcomes()) == len(set(c.all_outcomes())) == 9
    for p in c.fixtures():
        c.validate_profile(p)
        inventory = c.offer_inventory(p)
        assert len(inventory) == 4*2*36
        for item in inventory:
            assert item["full_delivery_utility"] == c.utility_vector(p, item["projects"].values())
            assert item["scripted_independent"] == c.scripted_independent(p, item["projects"])
        high = [v for v in inventory if v["projects"] == {"A":"A0","B":"B0"} and v["coalition"] == [0,1,3,4]]
        assert len(high) == 2
        if p["id"] == "aligned_control":
            assert high[0]["full_minus_independent"] == [0]*7
        else:
            assert high[0]["member_strict_improvement"]
            assert high[0]["scripted_independent"]["passed"] == []
    low, high, control = c.fixtures()
    assert sum(c.utility_vector(low, ("A0","B0"))) > sum(c.utility_vector(low, ("A1","B1")))
    assert sum(c.utility_vector(high, ("A0","B0"))) < sum(c.utility_vector(high, ("A1","B1")))
    assert c.utility_vector(low, ("A0","B0"))[:6] == c.utility_vector(high, ("A0","B0"))[:6]


def test_future_actions_are_not_in_history():
    with pytest.raises(ValueError):
        c.resolve_vote(history(), "member_enforcement", [True]*7, "second_vote")
    with pytest.raises(ValueError):
        c.resolve_vote([], "member_enforcement", [True]*7, "first_vote")


def test_offer_prompt_does_not_supply_a_solution_coalition():
    for stage in ("draft", "response", "final"):
        prompt = c.task_text(stage, [])
        assert "[0,1,3,4]" not in prompt and "[0, 1, 3, 4]" not in prompt
        assert '"A0"' not in prompt and '"B0"' not in prompt
    assert "keys support, projects, first, coalition, message" in c.task_text("response", [])
