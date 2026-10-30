from decimal import Decimal

import pytest

from paper3 import coalition_contracts as game
from paper3 import constituent_b_design as design
from paper3 import constituent_b_institution as institution
from paper3 import constituent_b_requests as requests


def test_exact_model_endpoint_and_gate_reservations():
    cases = requests.gate_requests()
    assert len(cases) == 12
    assert all(row["request"]["model"] == requests.MODEL for row in cases)
    assert all(row["request"]["provider"]["only"] == [requests.PROVIDER_TAG]
               for row in cases)
    assert all(row["request"]["reasoning"] == dict(enabled=True, exclude=False)
               for row in cases)
    assert sum(Decimal(row["reserved_usd"]) for row in cases) <= requests.GATE_CAP
    assert len({row["seed"] for row in cases}) == 12


def test_all_discovery_assignments_cross_arms_and_hold_phase_one():
    assignments = requests.discovery_assignments()
    assert len(assignments) == 12
    assert [a["phase"] for a in assignments] == [1] * 3 + [2] * 9
    assert len({a["id"] for a in assignments}) == 12
    assert len({a["profile_id"] for a in assignments}) == 4
    assert len({a["seed_base"] for a in assignments}) == 4
    assert set(a["arm"] for a in assignments[:3]) == {
        "public_promise", "member_enforcement", "universal_clearance"}


def test_paired_first_draft_has_identical_citizens_information_and_seed():
    first = design.frame(requests.DISCOVERY_FRAME_SEED)[0]["prepared"]
    profile = first["contract_profile"]
    assignments = requests.discovery_assignments()[:3]
    prompts = {}
    for assignment in assignments:
        assert assignment["profile_id"] == profile["id"]
        arm = assignment["arm"]
        messages = institution.messages(first, arm, profile["proposer"], "draft", [])
        prompts[arm] = requests.request(messages, assignment["seed_base"],
                                        kind="action", stage="draft")
    assert len({value["seed"] for value in prompts.values()}) == 1
    assert len({value["messages"][1]["content"] for value in prompts.values()}) == 1
    for arm, value in prompts.items():
        assert value["messages"][0]["content"] == (
            institution.common_rules(first) + "\n" + game.ARM_RULES[arm])
        assert value["provider"]["only"] == [requests.PROVIDER_TAG]


def test_scripted_full_length_path_reserves_under_cap():
    report = requests.scripted_discovery_preflight()
    assert report["intended_calls"] == 360
    assert Decimal(report["full_output_scripted_reservations_usd"]) <= requests.DISCOVERY_CAP
    assert report["max_input_bound"] <= requests.INPUT_BOUND


def test_request_validation_and_schema_variants():
    for kind, stage in (("action", "draft"), ("action", "response"),
                        ("action", "consent"), ("action", "second_vote")):
        shape = requests.schema(kind, stage)
        assert shape["additionalProperties"] is False
    assert requests.schema("fact", name="mandate-00")["properties"][
        "citizens_better_than_q"]["type"] == "integer"
    assert requests.schema("fact", name="contract-00")["properties"][
        "agreement_active"]["type"] == "boolean"
    with pytest.raises(ValueError):
        requests.request([], True, kind="action", stage="draft")
    with pytest.raises(ValueError):
        requests.schema("action", "unknown")
    with pytest.raises(ValueError):
        requests.schema("fact", name="unknown")
