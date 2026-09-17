import json

from paper3.commitment_memory import profile, ask
from paper3.grounded_interface import GroundedInterface, authorization_case


class Capture:
    def generate(self, messages, **kwargs):
        self.messages = messages
        return '{"sign":false}'


def test_identity_is_explicit_without_changing_evidence_or_prescribing_action():
    base = Capture()
    ask(GroundedInterface(base), profile(7), 6, [], 'Ratify or reject final-2 for your principal. Return {"sign":true}.', {"sign": bool})
    assert "representative 6, acting exclusively for principal 6" in base.messages[0]["content"]
    payload, task = base.messages[-1]["content"].split("\n", 1)
    assert json.loads(payload)["utilities_for_all_principals"]["6"]["A0"] == -6
    assert '{"sign":true}' not in task
    assert "true or false" in task


def test_gate_contains_strict_accept_and_reject_choices():
    for seed in (7, 10):
        for actor in (0, 3, 6):
            for package in (0, 3):
                plain, expected = authorization_case(profile(seed), actor, package, False)
                quoted, same = authorization_case(profile(seed), actor, package, True)
                assert same == expected
                assert expected["principal_utility_if_accepted"] != 0
                assert expected["accept"] is not (actor == 6 and package == 0)
                assert plain[0] == quoted[0]
