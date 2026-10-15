"""Prospective tool-call action envelope for the constituent B successor.

This module makes no model calls. It does not modify or rescore the failed
bare-JSON gate. A future protocol must freeze this interface before inference.
"""
from __future__ import annotations

from copy import deepcopy
import json

from paper3 import constituent_b_gate as gate
from paper3 import constituent_b_requests as previous


TOOL_NAME = "submit_decision"
OLD_INSTRUCTION = "put only the requested JSON object in\nyour final answer."
NEW_INSTRUCTION = (
    "call the submit_decision function exactly once with the requested fields; "
    "do not put the action in a final text answer."
)


def request(messages, seed, *, kind, stage=None, name=None):
    """Keep the substantive task/model fixed while changing the action channel."""
    value = deepcopy(previous.request(messages, seed, kind=kind, stage=stage, name=name))
    replacements = 0
    for message in value["messages"]:
        if message["role"] == "system":
            replacements += message["content"].count(OLD_INSTRUCTION)
            message["content"] = message["content"].replace(OLD_INSTRUCTION, NEW_INSTRUCTION)
    if replacements != 1:
        raise ValueError("expected exactly one old output-channel instruction")
    value.pop("response_format")
    value["tools"] = [dict(type="function", function=dict(
        name=TOOL_NAME,
        description="Record this representative's decision or the requested factual report; the controller validates and applies its fields.",
        parameters=previous.schema(kind, stage, name),
    ))]
    value["tool_choice"] = dict(type="function", function=dict(name=TOOL_NAME))
    return value


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate tool-argument key")
        value[key] = item
    return value


def _frames(trace):
    pending = []
    done = 0
    for line in [*trace["lines"], ""]:
        if line == "":
            if not pending:
                continue
            raw = "\n".join(pending)
            pending = []
            if raw == "[DONE]":
                done += 1
                continue
            if done:
                raise ValueError("frame after DONE")
            try:
                frame = json.loads(raw)
            except (ValueError, TypeError) as exc:
                raise ValueError("malformed SSE frame") from exc
            if type(frame) is not dict:
                raise ValueError("non-object SSE frame")
            yield frame
        elif line.startswith("data:"):
            pending.append(line[5:].lstrip(" "))
    if done != 1:
        raise ValueError("expected exactly one DONE marker")


def arguments(trace):
    """Assemble exactly one streamed function call; never parse assistant prose.

    This checks the action envelope, not transport identity, cost, native
    reasoning or the substantive validity of the supplied arguments.
    """
    pieces, call_id, function_name, finish = [], None, None, set()
    seen = False
    for frame in _frames(trace):
        if frame.get("error"):
            raise ValueError("error frame")
        for choice in frame.get("choices") or []:
            if choice.get("index") != 0:
                raise ValueError("unexpected choice index")
            if choice.get("finish_reason"):
                finish.add(choice["finish_reason"])
            delta = choice.get("delta") or {}
            for fragment in delta.get("tool_calls") or []:
                seen = True
                if fragment.get("index") != 0:
                    raise ValueError("multiple or unindexed tool calls")
                if fragment.get("type") not in (None, "function"):
                    raise ValueError("non-function tool call")
                identifier = fragment.get("id")
                if identifier is not None:
                    if type(identifier) is not str or not identifier or (
                        call_id is not None and identifier != call_id
                    ):
                        raise ValueError("conflicting tool-call id")
                    call_id = identifier
                function = fragment.get("function") or {}
                name = function.get("name")
                if name is not None:
                    if type(name) is not str or (
                        function_name is not None and name != function_name
                    ):
                        raise ValueError("conflicting tool name")
                    function_name = name
                part = function.get("arguments")
                if part is not None:
                    if type(part) is not str:
                        raise ValueError("non-string tool arguments")
                    pieces.append(part)
    if not seen or not call_id or function_name != TOOL_NAME or finish != {"tool_calls"}:
        raise ValueError("missing or incomplete forced tool call")
    raw = "".join(pieces)
    try:
        value = json.loads(
            raw, object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite argument")),
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid tool arguments") from exc
    if type(value) is not dict:
        raise ValueError("tool arguments must be an object")
    return value


def score(trace, case):
    """Apply the unchanged substantive gate score to structured arguments."""
    try:
        value = arguments(trace)
    except (ValueError, KeyError, TypeError) as exc:
        return dict(status="failed", exact=False, reply=None, error=str(exc))
    result = gate.score(json.dumps(value, sort_keys=True, separators=(",", ":")), case)
    return dict(status=result["status"], exact=result["exact"],
                reply=result.get("reply"), error=result.get("error"))
