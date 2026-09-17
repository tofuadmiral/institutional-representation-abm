import json

from paper3.institution import CoalitionContract
from paper3.scenarios import PreferenceRegime, generate_scenario
from paper3.soft_trade import SoftAuthority, run_soft_contract_response, select_trade_contract


class Backend:
    model = "test"

    def __init__(self, replies):
        self.replies = iter(replies)

    def generate(self, messages, *, temperature=0.0, max_tokens=256):
        return next(self.replies)


def test_catalog_contract_is_hard_legal_and_costly_for_two_named_members():
    scenario = generate_scenario(seed=0, regime=PreferenceRegime.FRAGMENTED)
    contract = select_trade_contract(scenario)
    policy = next(policy for policy in scenario.policies if policy.policy_id == contract.policy_id)
    assert all(scenario.mandates[member].permits(policy) for member in contract.members)


def test_nonmember_cannot_sign_the_contract():
    scenario = generate_scenario(seed=0, regime=PreferenceRegime.FRAGMENTED)
    contract = select_trade_contract(scenario)
    private = {i: "broad_compromise" for i in range(7)}
    replies = []
    for representative_id in range(7):
        replies.append(json.dumps({"vote": "broad_compromise", "sign": representative_id not in contract.members}))
    try:
        run_soft_contract_response(scenario=scenario, contract=contract, private_positions=private, authority=SoftAuthority.FREE_VOTE, backend=Backend(replies))
    except ValueError as exc:
        assert "nonmember" in str(exc)
    else:
        raise AssertionError("expected nonmember signature rejection")
