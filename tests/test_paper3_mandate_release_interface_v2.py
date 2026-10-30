"""Offline interface-compatibility tests; no model calls."""

import json

import pytest

from paper3 import mandate_release_design as design
from paper3 import mandate_release_interface_v2 as interface


def test_coalition_tokens_are_exactly_all_valid_choices():
    assert len(interface.TOKENS) == 36
    assert len(set(interface.TOKENS)) == 36
    assert interface.TOKENS[0] == "none"
    assert set(interface.TOKENS[1:]) == {
        "-".join(map(str, sorted(members)))
        for members in __import__("itertools").combinations(range(7), 4)
    }


@pytest.mark.parametrize("case", design.cases()[:2])
def test_decode_every_valid_coalition_in_rotated_cases(case):
    for token in interface.TOKENS:
        raw = json.dumps(dict(second_project=case.display_projects[0],
                              coalition=token, message="Test"))
        action = interface.decode(case, "final", raw)
        assert len(action["coalition"]) == (0 if token == "none" else 4)
        assert len(set(action["coalition"])) == len(action["coalition"])


def test_failed_v1_three_member_offer_is_unrepresentable():
    case = design.cases()[0]
    schema = interface.schema(case, "final")
    assert schema["properties"]["coalition"]["enum"] == list(interface.TOKENS)
    with pytest.raises(ValueError):
        interface.decode(case, "final", json.dumps(dict(
            second_project=case.display_projects[0], coalition="3-4-5",
            message="I meant myself plus three others")))
    with pytest.raises(ValueError):
        interface.decode(case, "final", json.dumps(dict(
            second_project=case.display_projects[0], coalition=[0, 3, 4, 5],
            message="Old v1 format is not accepted")))


def test_message_bound_matches_serialized_worst_case():
    case = design.cases()[0]
    assert len(json.dumps("😀" * interface.MAX_MESSAGE_CHARS,
                          ensure_ascii=True).encode()) == interface.MAX_MESSAGE_JSON_BYTES
    raw = json.dumps(dict(second_project=case.display_projects[0], coalition="none",
                          message="😀" * interface.MAX_MESSAGE_CHARS))
    assert len(interface.decode(case, "draft", raw)["message"]) == 150
    with pytest.raises(ValueError):
        interface.decode(case, "draft", json.dumps(dict(
            second_project=case.display_projects[0], coalition="none",
            message="a" * (interface.MAX_MESSAGE_CHARS + 1))))


def test_prompt_explicitly_counts_self_as_one_of_four():
    case = design.cases()[0]
    messages = interface.messages(case, 0, "draft", dict(proposer=0,
                                                          arm="irrevocable"))
    assert "including yourself" in messages[0]["content"]
    assert "Only the token" in messages[0]["content"]
