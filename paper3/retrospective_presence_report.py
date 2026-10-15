"""Unfrozen, offline-only candidate for terminal qualification reports.

Replace nullable successor scores with an explicit presence bit and integer.
This changes report encoding/instructions, not the facts or institutional actions.
No provider compatibility, qualification, allocation or historical repair.
"""
from copy import deepcopy
import json

from paper3 import retrospective_interface as interface
from paper3 import retrospective_qualification as original


FIELDS = {"acting_identity", "original_incumbent_score", "successor_score",
          "third_term_bonus"}
WIRE_FIELDS = FIELDS | {"successor_present"}
OLD_TASK = ("Report acting_identity, original_incumbent_score, successor_score "
            "(null if no successor acts), and third_term_bonus.")
NEW_TASK = ("Report acting_identity, original_incumbent_score, successor_present, "
            "successor_score, and third_term_bonus. successor_present is a boolean "
            "indicating whether a successor acts. successor_score is an integer: "
            "use 0 if no successor acts; otherwise report the successor's score "
            "even if that score is 0. This is only the report encoding, not a "
            "change to identity, rewards or institutional rules.")


def _check_common(value, fields):
    if (type(value) is not dict or set(value) != fields
            or type(value["acting_identity"]) is not str
            or type(value["original_incumbent_score"]) is not int
            or type(value["third_term_bonus"]) is not int):
        raise ValueError("terminal factual field/type mismatch")


def encode(value):
    """Injective encoding of the original strictly typed semantic report."""
    _check_common(value, FIELDS)
    score = value["successor_score"]
    if score is not None and type(score) is not int:
        raise ValueError("successor score must be integer or null")
    return dict(deepcopy(value), successor_present=score is not None,
                successor_score=0 if score is None else score)


def decode(value):
    """Reject noncanonical absence, wrong types and extras; never coerce."""
    _check_common(value, WIRE_FIELDS)
    if (type(value["successor_present"]) is not bool
            or type(value["successor_score"]) is not int
            or (not value["successor_present"] and value["successor_score"] != 0)):
        raise ValueError("successor presence/score field/type mismatch")
    result = deepcopy(value)
    present = result.pop("successor_present")
    result["successor_score"] = result["successor_score"] if present else None
    return result


def terminal(case):
    return case["kind"] == "fact" and case["id"].endswith("-terminal")


def structured(case):
    """Adapt only four terminal reports; no changes to the other 14 tasks.

The flat wire schema deliberately has no conditional/provider-specific feature.
The local decoder additionally enforces absent => score zero. This rule is
disclosed for every terminal task, never supplied as its particular answer.
The source case is not mutated. Fresh live cases must be separately frozen.
"""
    fragment = original.structured(case)
    if not terminal(case):
        return fragment
    encode(case["expected"])  # Reject an unexpected oracle shape, not fix it.
    parameters = fragment["tools"][0]["function"]["parameters"]
    expected_schema = original._fact_schema(case["expected"])
    if parameters != expected_schema:
        raise ValueError("unsupported terminal schema; do not drop constraints")
    parameters["properties"]["successor_score"] = dict(type="integer",
        description="Successor's score when present; exactly zero when absent.")
    parameters["properties"]["successor_present"] = dict(type="boolean",
        description="Whether a successor acts, independently of its score value.")
    parameters["required"].append("successor_present")
    message = fragment["messages"][1]
    content = json.loads(message["content"])
    task = content["task"]
    if not task.endswith(OLD_TASK) or task.count(OLD_TASK) != 1:
        raise ValueError("unsupported terminal instructions")
    content["task"] = task[:-len(OLD_TASK)] + NEW_TASK
    message["content"] = json.dumps(content, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False)
    return fragment


def score(case, trace):
    """Prospective typed semantic scorer; transport/native/billing remain separate.

Only usable NEW-interface traces belong here. Never apply to an old run or
reinterpret its failed output. Nonterminal actions keep the original decoder
and all legal choices remain allowed, irrespective of the research hypothesis.
"""
    if not terminal(case):
        return original.score(case, trace)
    try:
        encode(case["expected"])
        action = interface.envelope.arguments(trace)
        semantic = decode(action)
        return dict(valid_action=True, exact=semantic == case["expected"],
                    action=action, semantic_action=semantic, failure=None)
    except (ValueError, TypeError, KeyError) as exc:
        return dict(valid_action=False, exact=False, action=None,
                    semantic_action=None, failure=str(exc))
