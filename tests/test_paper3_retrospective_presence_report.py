"""Pure offline checks. Closed cases are fixtures, never new qualifications."""
from copy import deepcopy
import json

from jsonschema import Draft202012Validator
import pytest

from paper3 import retrospective_atlas_nullable_qualification as fixtures
from paper3 import retrospective_presence_report as candidate
from tests.test_paper3_retrospective_portable_schema import action, trace, VALUES


def report(score):
    return dict(acting_identity="fixture", original_incumbent_score=-14,
                successor_score=score, third_term_bonus=0)


def test_lossless_presence_distinguishes_absence_from_zero_and_all_integer_scores():
    # Algebraically: absent <-> (false, 0); any integer n <-> (true, n).
    # These disjoint images cover the declared canonical wire domain.
    for value in (None, *range(-1000, 1001), -(10**100), 10**100):
        semantic = report(value)
        before = deepcopy(semantic)
        wire = candidate.encode(semantic)
        assert candidate.decode(wire) == semantic == before
        assert candidate.encode(candidate.decode(wire)) == wire
    assert candidate.encode(report(None)) != candidate.encode(report(0))


@pytest.mark.parametrize("case", fixtures.cases(), ids=lambda c: c["id"])
def test_all_eighteen_tasks_preserve_facts_information_and_legal_actions(case):
    before = deepcopy(case)
    changed = candidate.structured(case)
    old = fixtures.original.structured(case)
    schema = changed["tools"][0]["function"]["parameters"]
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    assert case == before
    assert changed["tool_choice"] == "auto" and len(changed["tools"]) == 1
    assert "const" not in json.dumps(schema)
    expected = action(case)
    if not candidate.terminal(case):
        assert changed == old
        assert candidate.score(case, trace(expected)) == fixtures.score(case, trace(expected))
        if case["kind"] == "action":
            for p in range(6):
                strategic = (dict(policy=p, message="any legal choice")
                    if case["stage"] in ("draft", "final") else
                    dict(support=bool(p % 2), counter_policy=p, message="legal")
                    if case["stage"] == "response" else dict(vote=bool(p % 2)))
                assert candidate.score(case, trace(strategic))["exact"]
        return
    wire = candidate.encode(expected)
    assert validator.is_valid(wire)
    assert candidate.score(case, trace(wire))["exact"]
    restored = deepcopy(changed)
    restored["tools"][0]["function"]["parameters"] = old["tools"][0]["function"]["parameters"]
    old_content = json.loads(old["messages"][1]["content"])
    new_content = json.loads(changed["messages"][1]["content"])
    assert new_content.pop("task").endswith(candidate.NEW_TASK)
    old_content.pop("task")
    assert new_content == old_content  # History/payoffs/assumptions are untouched.
    restored["messages"][1]["content"] = old["messages"][1]["content"]
    assert restored == old
    assert {prop["type"] for prop in schema["properties"].values()} == {
        "integer", "boolean", "string"}
    # No scalar coercion: exact Python types are authoritative, even where JSON
    # Schema regards e.g. 14.0 as an integer. Extra/missing fields are rejected.
    candidates = [None, {}, dict(wire, extra=0)]
    for key in wire:
        missing = deepcopy(wire)
        missing.pop(key)
        candidates.append(missing)
        candidates.extend(dict(wire, **{key: value}) for value in VALUES)
    for output in candidates:
        scored = candidate.score(case, trace(output))
        try:
            semantic = candidate.decode(output)
        except ValueError:
            assert not scored["valid_action"] and not scored["exact"]
        else:
            assert validator.is_valid(output)
            assert scored["valid_action"]
            assert scored["exact"] == (semantic == expected)
            assert fixtures.score(case, trace(semantic))["exact"] == scored["exact"]


@pytest.mark.parametrize("bad", [True, False, "null", "0", 0.0, .5, [], {}])
def test_no_semantic_coercion(bad):
    with pytest.raises(ValueError):
        candidate.encode(report(bad))
    with pytest.raises(ValueError):
        candidate.decode(dict(candidate.encode(report(None)), successor_score=bad))


def test_inconsistent_presence_and_wrong_facts_do_not_pass():
    case = next(c for c in fixtures.cases() if candidate.terminal(c)
                and c["expected"]["successor_score"] is None)
    wire = candidate.encode(case["expected"])
    for flag in (0, 1, "false", None, [], {}):
        assert not candidate.score(case, trace(dict(wire, successor_present=flag)))["valid_action"]
    assert not candidate.score(case, trace(dict(wire, successor_score=1)))["valid_action"]
    for key, wrong in (("acting_identity", "successor-r0"),
                       ("original_incumbent_score", wire["original_incumbent_score"] + 1),
                       ("third_term_bonus", 24), ("successor_present", True)):
        scored = candidate.score(case, trace(dict(wire, **{key: wrong})))
        assert scored["valid_action"] and not scored["exact"]
    # A real successor with score zero is valid but wrong for an absent one.
    present_zero = dict(wire, successor_present=True)
    assert candidate.decode(present_zero)["successor_score"] == 0
    assert not candidate.score(case, trace(present_zero))["exact"]
    # Historical nullable answers, including the actual string failure, are not
    # repaired or accepted by this prospective interface.
    for old in (case["expected"], dict(case["expected"], successor_score="null")):
        assert not candidate.score(case, trace(old))["valid_action"]


def test_no_unsupported_schema_or_task_constraints_silently_dropped():
    case = next(c for c in fixtures.cases() if candidate.terminal(c))
    constrained = deepcopy(case)
    constrained["parameters"]["properties"]["successor_score"]["enum"] = [None, 0]
    with pytest.raises(ValueError, match="unsupported terminal schema"):
        candidate.structured(constrained)
    bad_task = deepcopy(case)
    message = json.loads(bad_task["messages"][1]["content"])
    message["task"] = "unexpected different question"
    bad_task["messages"][1]["content"] = json.dumps(message)
    with pytest.raises(ValueError, match="unsupported terminal instructions"):
        candidate.structured(bad_task)
