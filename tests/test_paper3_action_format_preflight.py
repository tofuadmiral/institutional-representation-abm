import itertools
import json

import pytest

from analysis.paper3_action_format_preflight import fixtures
from paper3.agenda_rights import validate_action


@pytest.mark.parametrize("name,stage,available", [
    ("pairwise", "pairwise", ["p3", "p6"]),
    ("single_pairwise", "pairwise", ["p7"]),
    ("ratification", "ratification", ["p3", "p6"]),
    ("single_ratification", "ratification", ["p7"]),
    ("public", "opening", ["p3", "p6"]),
])
def test_component_examples_match_existing_strict_action_contract(name, stage, available):
    schema, legal, invalid = fixtures()[name]
    assert schema["additionalProperties"] is False
    for value in legal:
        assert validate_action(json.dumps(value), stage, available) == value
    for raw in invalid:
        with pytest.raises(ValueError):
            validate_action(raw, stage, available)


def test_selector_grammar_examples_allow_all_answers_not_only_correct_ones():
    schema, legal, _ = fixtures()["selector_gate"]
    assert set(schema["properties"]["selected_policy"]["enum"]) == {"policy_k", "policy_m"}
    combinations = {(row["selected_policy"], row["votes"]["policy_k"], row["votes"]["policy_m"])
                    for row in legal}
    assert combinations == set(itertools.product(("policy_k", "policy_m"), (False, True), (False, True)))
