import json

from paper3.comprehension import evaluate_representative, expected_policy
from paper3.institution import Mandate, Policy


class Backend:
    model = "test"

    def __init__(self, response):
        self.response = response

    def generate(self, messages, *, temperature=0.0, max_tokens=256):
        return self.response


POLICIES = (Policy("bad", (2.0, 0.0)), Policy("best", (0.1, 0.0)), Policy("okay", (0.4, 0.0)))
MANDATE = Mandate(0, (0.0, 0.0), hard_loss_limit=0.5)


def test_expected_policy_respects_hard_constraint_before_lowest_loss():
    assert expected_policy(MANDATE, POLICIES) == "best"


def test_gate_marks_exact_response_only_when_schema_and_action_are_correct():
    result = evaluate_representative(
        scenario_id="s",
        representative_id=0,
        mandate=MANDATE,
        policies=POLICIES,
        order_block=1,
        backend=Backend(json.dumps({"choice": "best", "listed_loss": 0.1, "within_hard_mandate": True})),
    )
    assert result.valid_json and result.exact
    bad = evaluate_representative(
        scenario_id="s",
        representative_id=0,
        mandate=MANDATE,
        policies=POLICIES,
        order_block=0,
        backend=Backend(json.dumps({"choice": "bad", "listed_loss": 2.0, "within_hard_mandate": True})),
    )
    assert bad.valid_json and not bad.exact
