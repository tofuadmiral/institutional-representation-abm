import json

from paper3.coalition_probe import collect_private_positions, run_authority_arm, run_common_contract_response
from paper3.institution import AuthorityRule, CoalitionContract
from paper3.scenarios import PreferenceRegime, generate_scenario


class ScriptedBackend:
    model = "scripted"

    def __init__(self, responses):
        self.responses = iter(responses)

    def generate(self, messages, *, temperature=0.0, max_tokens=256):
        return next(self.responses)


def test_probe_keeps_private_positions_fixed_and_records_binding_overrides():
    scenario = generate_scenario(seed=2, regime=PreferenceRegime.FRAGMENTED)
    private = [json.dumps({"choice": "status_quo"})] * 7
    positions, _ = collect_private_positions(scenario=scenario, backend=ScriptedBackend(private))
    responses = [
        json.dumps({"members": [0, 1, 2, 3], "policy": "right_package", "reason": "test"}),
        *[json.dumps({"vote": "status_quo", "support": False, "reason": "test"}) for _ in range(7)],
    ]
    result = run_authority_arm(
        scenario=scenario,
        private_positions=positions,
        formateur_id=0,
        authority=AuthorityRule.COALITION_DISCIPLINE,
        backend=ScriptedBackend(responses),
    )
    assert result["private_positions"] == positions
    assert result["record"]["accepted"]
    assert result["record"]["overridden_members"] == (0, 1, 2, 3)


def test_common_contract_does_not_call_a_formateur_or_change_contract_across_arms():
    scenario = generate_scenario(seed=2, regime=PreferenceRegime.FRAGMENTED)
    positions = {representative_id: "status_quo" for representative_id in range(7)}
    contract = CoalitionContract(0, (0, 1, 2, 3), "right_package")
    result = run_common_contract_response(
        scenario=scenario,
        private_positions=positions,
        contract=contract,
        authority=AuthorityRule.FREE_RATIFICATION,
        backend=ScriptedBackend([json.dumps({"vote": "status_quo", "support": False, "reason": "test"}) for _ in range(7)]),
    )
    assert result["proposal"] == {"formateur_id": 0, "members": (0, 1, 2, 3), "policy_id": "right_package"}
    assert result["record"]["final_policy_id"] == "status_quo"
