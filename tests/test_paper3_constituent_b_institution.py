import json

import pytest

from paper3 import coalition_contracts as old
from paper3 import constituent_b_institution as new
from paper3 import constituent_contract_bridge as bridge
from tests.test_paper3_constituent_contract_bridge import ConstituentContractBridgeTests


@pytest.fixture
def prepared():
    return bridge.prepare_equal_standing(
        ConstituentContractBridgeTests.fixed_standing_profile(),
        "fixed-standing", 0, citizens_per_district=9, priority_budget=4,
        coordinate_bound=5)


@pytest.mark.parametrize("arm", old.ARMS)
def test_mandate_prompt_explicit_and_institutional_rule_unchanged(prepared, arm):
    before = old.messages(prepared["contract_profile"], arm, 0, "draft", [])
    after = new.messages(prepared, arm, 0, "draft", [])
    assert old.ARM_RULES[arm] in after[0]["content"]
    assert "maximize YOUR district's mean utility" in after[0]["content"]
    assert "majority-vote rule" in after[0]["content"]
    assert "YOUR principal's total utility" not in after[0]["content"]
    assert after[0]["content"] != before[0]["content"]
    record, task = after[1]["content"].split("\n", 1)
    record = json.loads(record)
    assert record["district"] == "r0"
    assert record["equal_standing_specification"]["citizen_count"] == 63
    assert len(record["own_citizens"]) == 9
    assert record["district_summed_utilities"] == prepared["contract_profile"]["utilities"]
    assert "your district" in task
    assert "your principal" not in task


def test_prompt_snapshot_is_detached_and_source_game_is_unchanged(prepared):
    original = old.COMMON_RULES
    prompt = new.messages_snapshot(prepared, "public_promise", 0, "draft", [])
    prepared["electorate_profile"]["districts"]["r0"][0]["ideal"][0] = 999
    record = json.loads(prompt[1]["content"].split("\n", 1)[0])
    assert record["own_citizens"][0]["ideal"][0] != 999
    assert old.COMMON_RULES == original


def test_invalid_actor_and_arm_rejected(prepared):
    with pytest.raises(ValueError):
        new.messages(prepared, "bogus", 0, "draft", [])
    with pytest.raises(ValueError):
        new.messages(prepared, "public_promise", 7, "draft", [])


def test_public_district_row_cannot_disagree_with_citizens(prepared):
    prepared["contract_profile"]["utilities"][0]["A0"] += 1
    with pytest.raises(ValueError, match="district objective"):
        new.messages(prepared, "public_promise", 0, "draft", [])


@pytest.mark.parametrize("arm,passed", [
    ("public_promise", []),
    ("member_enforcement", ["A0", "B0"]),
    ("universal_clearance", ["A0", "B0"]),
])
def test_scripted_episode_preserves_controller_and_citizen_readout(prepared, arm, passed):
    # Fabricated actions certify integration, not model reasoning or an effect.
    offer = dict(projects=dict(A="A0", B="B0"), first="A",
                 coalition=[0, 1, 3, 4], message="test")
    seen = []

    def ask(actor, stage, messages, index):
        seen.append((actor, stage, index))
        if stage in ("draft", "final"):
            action = offer
        elif stage == "response":
            action = dict(offer, support=True)
        elif stage == "consent":
            action = dict(consent=True)
        else:
            action = dict(vote=False)
        return json.dumps(action)

    result = new.episode(prepared, arm, ask)
    assert len(seen) == result["calls"] == 30
    assert result["outcome"]["passed"] == passed
    assert result["citizen_outcome"]["overall"]["citizen_count"] == 63
    assert result["citizen_outcome"]["overall"]["citizens_worse_than_q"] == (
        0 if arm == "public_promise" else 39)
