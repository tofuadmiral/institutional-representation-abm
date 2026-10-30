"""Offline design checks; no model calls and no claim that agents pass."""
from copy import deepcopy
import json

import pytest

from paper3 import coalition_mandate_diagnostic as d


def test_full_design_and_paired_seeds():
    cases = d.cases((100, 200))
    assert json.loads(json.dumps(cases)) == cases
    assert len(cases) == len({c["id"] for c in cases}) == 56
    assert len({c["seed"] for c in cases}) == 28
    for repeat in (0, 1):
        for profile in (0, 1):
            for actor in range(7):
                pair = [c for c in cases if (c["repeat"], c["profile_index"], c["actor"]) ==
                        (repeat, profile, actor)]
                assert len(pair) == 2 and pair[0]["seed"] == pair[1]["seed"]
                assert pair[0]["expected"] == pair[1]["expected"]


@pytest.mark.parametrize("profile", (0, 1))
@pytest.mark.parametrize("actor", range(7))
def test_information_equal_and_answers(profile, actor):
    a, b = (d.context(profile, actor, encoding) for encoding in d.ENCODINGS)
    left, right = deepcopy(a["record"]), deepcopy(b["record"])
    rows = left.pop("utilities_for_all_principals")
    mapping = right.pop("utilities_for_all_principals")
    assert left == right and rows == [mapping[str(i)] for i in range(7)]
    assert a["messages"][0] == b["messages"][0]
    expected = a["expected"]
    assert expected["own_utilities"] == rows[actor]
    assert expected["package_utility"] == (6 if actor < 6 else (0 if profile == 0 else -24))
    assert (expected["member_active"], expected["universal_active"]) == (
        (True, True), (True, False), (False, False))[actor % 3]
    assert expected["bound_if_active"] == (actor in (0, 1, 3, 4))
    assert d.score_content(json.dumps(expected), expected)["correct"]


def test_wrong_answer_is_valid_but_not_correct():
    expected = d.context(0, 3, "row_array")["expected"]
    value = deepcopy(expected); value["own_utilities"]["A0"] = 9
    result = d.score_content(json.dumps(value), expected)
    assert result["valid"] and not result["correct"]
    assert result["fields"]["own_utilities"] is False


def test_rule_answers_not_constant():
    answers = [c["expected"] for c in d.cases((100, 200))]
    assert {(a["member_active"], a["universal_active"]) for a in answers} == {
        (True, True), (True, False), (False, False)}
    assert {a["bound_if_active"] for a in answers} == {True, False}


@pytest.mark.parametrize("raw", ['{}', '[]', 'null', 'NaN', 'not json',
                                '{"own_utilities":{},"own_utilities":{}}'])
def test_bad_content_not_repaired(raw):
    assert not d.score_content(raw, d.context(0, 0, "row_array")["expected"])["valid"]


@pytest.mark.parametrize("field,bad", [("package_utility", True), ("member_active", 1),
                                     ("universal_active", "false"), ("bound_if_active", None)])
def test_strict_types(field, bad):
    expected = d.context(0, 0, "row_array")["expected"]
    value = deepcopy(expected); value[field] = bad
    assert not d.score_content(json.dumps(value), expected)["valid"]


def test_nested_boolean_duplicate_and_extra_key_rejected():
    expected = d.context(0, 0, "row_array")["expected"]
    value = deepcopy(expected); value["own_utilities"]["A0"] = True
    assert not d.score_content(json.dumps(value), expected)["valid"]
    raw = json.dumps(expected).replace('"A0": 9', '"A0": 9, "A0": 9')
    assert not d.score_content(raw, expected)["valid"]
    assert not d.score_content(json.dumps(dict(expected, explanation="extra")), expected)["valid"]


@pytest.mark.parametrize("bases", [(0, 0), (100, 110), (-1, 100), (True, 100), (100,)])
def test_invalid_seed_design(bases):
    with pytest.raises(ValueError):
        d.cases(bases)
