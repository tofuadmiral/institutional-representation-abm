"""Prospective dual-channel contract; offline only, not a historical repair.

Accept one real AUTO tool call OR one exact final-text JSON object. A future
runner must separately check native reasoning, provider/transport and billing.
This module makes no requests and does not inherit previous qualification.
"""
from copy import deepcopy
from dataclasses import asdict
import json
import math

from paper3 import constituent_b_tool_interface as envelope
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_keyed_interface as keyed

VERSION = "retrospective-action-contract-v1"
TOOL_NAME = envelope.TOOL_NAME
OLD = """Use native reasoning, then call submit_decision exactly once with the requested
fields. The structured fields, not promises in a message, determine your action.
"""
NEW = """Use native reasoning, then submit exactly one structured decision with the
requested fields. Either call submit_decision once, with no other final text,
or put exactly one JSON object in your final text, without a tool call. In the
text form only, the exact label submit_decision followed by a newline may
precede the JSON object. No markdown fences, explanations, extra fields or
second decision are allowed. Both forms use the same requested field schema.
The structured fields, not promises in a message, determine your action.
"""
if keyed.SYSTEM.count(OLD) != 1:
    raise ValueError("expected one unchanged output instruction")
SYSTEM = keyed.SYSTEM.replace(OLD, NEW)


def replace_instruction(messages_value):
    """Change only the output paragraph of the validated keyed prompt."""
    if (type(messages_value) is not list or len(messages_value) != 2
            or messages_value[0] != dict(role="system", content=keyed.SYSTEM)
            or messages_value[1].get("role") != "user"):
        raise ValueError("unchanged keyed messages required")
    result = deepcopy(messages_value)
    result[0]["content"] = SYSTEM
    return result


def messages(game, arm, actor, identity, term, stage, context):
    return replace_instruction(keyed.messages(game, arm, actor, identity, term, stage, context))


def structured(messages_value, game, stage):
    if (type(messages_value) is not list or len(messages_value) != 2
            or messages_value[0] != dict(role="system", content=SYSTEM)):
        raise ValueError("new contract messages required")
    return keyed.structured(messages_value, game, stage)


def _nonfinite(_):
    raise ValueError("nonfinite JSON value")


def _float(raw):
    result = float(raw)
    if not math.isfinite(result):
        raise ValueError("nonfinite JSON number")
    return result


def _object(raw):
    value = json.loads(raw, object_pairs_hook=envelope._unique,
                       parse_constant=_nonfinite, parse_float=_float)
    if type(value) is not dict:
        raise ValueError("exactly one JSON object required")
    return value


def _frames(trace):
    """Complete SSE with strict JSON, one DONE, and no later data frames."""
    if type(trace) is not dict or type(trace.get("lines")) is not list:
        raise ValueError("stream lines required")
    pending, done = [], False
    for line in [*trace["lines"], ""]:
        if type(line) is not str:
            raise ValueError("string stream lines required")
        if line == "":
            if not pending:
                continue
            raw = "\n".join(pending)
            pending = []
            if done:
                raise ValueError("data after DONE")
            if raw == "[DONE]":
                done = True
            else:
                yield _object(raw)
        elif line.startswith("data:"):
            pending.append(line[5:].lstrip(" "))
    if not done:
        raise ValueError("incomplete stream")


def decision(trace):
    """Return raw channel evidence plus strict arguments; never extract prose.

    Multiplicity/conflict checks apply even when both channels agree. Whitespace
    alone is not a second action. No retries, coercion, repair or fallback here.
    """
    texts, tool_parts = [], []
    call_id = name = finish = None
    tool_seen = False
    for frame in _frames(trace):
        if frame.get("error"):
            raise ValueError("stream error")
        choices = frame.get("choices", [])
        if type(choices) is not list or len(choices) > 1:
            raise ValueError("one choice required")
        for choice in choices:
            if type(choice) is not dict or type(choice.get("index")) is not int or choice["index"] != 0:
                raise ValueError("unexpected choice")
            if finish is not None:
                raise ValueError("choice after finish")
            delta = choice.get("delta", {})
            if type(delta) is not dict:
                raise ValueError("object delta required")
            if delta.get("role") not in (None, "assistant"):
                raise ValueError("non-assistant action")
            if any(delta.get(k) for k in ("function_call", "refusal", "audio")):
                raise ValueError("unsupported action channel")
            content = delta.get("content")
            if content is not None:
                if type(content) is not str:
                    raise ValueError("text content required")
                texts.append(content)
            fragments = delta.get("tool_calls", [])
            if type(fragments) is not list or len(fragments) > 1:
                raise ValueError("one tool fragment required")
            for part in fragments:
                tool_seen = True
                if (type(part) is not dict or type(part.get("index")) is not int
                        or part["index"] != 0 or part.get("type") not in (None, "function")):
                    raise ValueError("one indexed function required")
                identifier = part.get("id")
                if identifier is not None:
                    if type(identifier) is not str or not identifier or call_id not in (None, identifier):
                        raise ValueError("conflicting tool id")
                    call_id = identifier
                function = part.get("function", {})
                if type(function) is not dict:
                    raise ValueError("function object required")
                candidate = function.get("name")
                if candidate is not None:
                    if candidate != TOOL_NAME or name not in (None, candidate):
                        raise ValueError("wrong or conflicting tool name")
                    name = candidate
                raw = function.get("arguments")
                if raw is not None:
                    if type(raw) is not str:
                        raise ValueError("string tool arguments required")
                    tool_parts.append(raw)
            candidate = choice.get("finish_reason")
            if candidate is not None:
                if candidate not in ("stop", "tool_calls"):
                    raise ValueError("incomplete or unsupported finish")
                finish = candidate
    raw_text = "".join(texts)
    stripped = raw_text.strip(" \t\r\n")
    if tool_seen:
        if stripped or not call_id or name != TOOL_NAME or finish != "tool_calls":
            raise ValueError("ambiguous or incomplete tool decision")
        raw_action, channel = "".join(tool_parts), "tool"
    else:
        if finish != "stop":
            raise ValueError("complete text stop required")
        prefix = TOOL_NAME + "\n"
        labelled = stripped.startswith(prefix)
        raw_action = stripped[len(prefix):] if labelled else stripped
        channel = "labelled_json" if labelled else "json"
    return dict(arguments=_object(raw_action), channel=channel,
                raw_action=raw_action, final_text=raw_text)


def decode(game, stage, trace):
    """Same typed institutional action semantics for all allowed channels."""
    action = decision(trace)["arguments"]
    if stage in ("draft", "final"):
        return asdict(institution.parse_offer(game, action))
    if stage == "response":
        return asdict(institution.parse_response(game, action))
    institution.require(stage == "vote", "action stage")
    return dict(vote=institution.parse_vote(action))
