"""Offline semantic invariants only; no provider compatibility claim."""
from copy import deepcopy
import json

from jsonschema import Draft202012Validator
import pytest

from paper3 import retrospective_atlas_qualification as qualification
from paper3 import retrospective_portable_schema as portable


VALUES = [None, False, True, "", "14", "null", [], {}, .5, -1.5, 14.0,
          -(10**20), 10**20, *range(-180, 181)]


def action(case):
    if case["kind"] == "fact":
        return deepcopy(case["expected"])
    if case["stage"] in ("draft", "final"):
        return dict(policy=0, message="fabricated")
    if case["stage"] == "response":
        return dict(support=False, counter_policy=0, message="fabricated")
    return dict(vote=False)


def trace(value):
    frame = dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0,
        id="fabricated", type="function", function=dict(name="submit_decision",
        arguments=json.dumps(value)))]), finish_reason="tool_calls")])
    return dict(lines=["data: " + json.dumps(frame), "", "data: [DONE]", ""])


@pytest.mark.parametrize("case", qualification.cases(), ids=lambda c: c["id"])
def test_all_eighteen_schemas_answer_sets_and_scoring_unchanged(case):
    original = qualification.structured(case)
    before = deepcopy(original)
    changed = portable.fragment(original)
    old_schema = original["tools"][0]["function"]["parameters"]
    new_schema = changed["tools"][0]["function"]["parameters"]
    Draft202012Validator.check_schema(old_schema)
    Draft202012Validator.check_schema(new_schema)
    old, new = Draft202012Validator(old_schema), Draft202012Validator(new_schema)
    base = action(case)
    assert old.is_valid(base) and new.is_valid(base)
    changed_case = dict(case, parameters=new_schema)
    candidates = [base, None, {}, dict(base, extra=True)]
    for key in base:
        missing = deepcopy(base)
        missing.pop(key)
        candidates.append(missing)
        candidates.extend(dict(base, **{key: value}) for value in VALUES)
    for candidate in candidates:
        assert old.is_valid(candidate) == new.is_valid(candidate)
        assert qualification.score(case, trace(candidate)) == qualification.score(changed_case, trace(candidate))
    restored = deepcopy(changed)
    restored["tools"][0]["function"]["parameters"] = old_schema
    assert restored == original == before  # Information, tool name and mode fixed.
    if case["id"].endswith("-terminal"):
        assert new_schema["properties"]["successor_score"] == {
            "anyOf": [{"type": "integer"}, {"type": "null"}]}
    else:
        assert new_schema == old_schema


def test_nullable_domain_sibling_constraints_and_idempotence():
    original = dict(type="object", properties=dict(score=dict(type=["integer", "null"],
        minimum=0, maximum=24, enum=[None, 0, 24], description="No hint added.")),
        required=["score"], additionalProperties=False)
    converted = portable.nullable_integers(original)
    assert portable.nullable_integers(converted) == converted
    old, new = Draft202012Validator(original), Draft202012Validator(converted)
    for value in VALUES:
        assert old.is_valid(dict(score=value)) == new.is_valid(dict(score=value))
    assert original["properties"]["score"]["type"] == ["integer", "null"]
    assert converted["properties"]["score"]["description"] == "No hint added."


@pytest.mark.parametrize("bad", [dict(type=["string", "null"]),
    dict(type=["integer", "null"], anyOf=[dict(type="null")]),
    dict(type=["integer", "integer", "null"])])
def test_no_silent_broadening_of_unsupported_schema(bad):
    with pytest.raises(ValueError, match="unsupported"):
        portable.nullable_integers(dict(type="object", properties=dict(value=bad)))


def test_invalid_fragments_and_typed_scores_stay_strict():
    with pytest.raises(ValueError):
        portable.fragment(dict(tool_choice="required", tools=[]))
    case = next(c for c in qualification.cases() if c["id"].endswith("-terminal"))
    converted = dict(case, parameters=portable.nullable_integers(case["parameters"]))
    for bad in (True, "null", .5, "0"):
        report = qualification.score(converted, trace(dict(case["expected"], successor_score=bad)))
        assert not report["valid_action"] and not report["exact"]
