"""Prospective episode-local resource failure; no transport or old-run rescoring.

Accepted actions use the unchanged frozen validator. Only a completed, pinned,
fully reserved length ending may be safe to ISOLATE, never safe to EXECUTE.
Reported native-count inconsistencies remain failures, not corrected usage.
Source/ledger guards belong to the separately frozen production coordinator.
"""
from copy import deepcopy

from paper3 import retrospective_deepinfra_classifier_v1 as previous
from paper3 import retrospective_serialization_contract as grammar
from paper3 import retrospective_deepinfra_route_v1 as route

VERSION = "episode-local-verified-output-limit-v1"


def _length_channels(trace):
    """Validate structural channels without decoding or repairing any action."""
    text, tools, identifier, name, finish = False, False, None, None, False
    for frame in grammar._frames(trace):
        if frame.get("error"):
            raise ValueError("stream error")
        choices = frame.get("choices", [])
        if type(choices) is not list or len(choices) > 1:
            raise ValueError("one choice")
        for choice in choices:
            if type(choice) is not dict or type(choice.get("index")) is not int or choice["index"] != 0:
                raise ValueError("choice identity")
            delta = choice.get("delta", {})
            if type(delta) is not dict or delta.get("role") not in (None, "assistant"):
                raise ValueError("assistant delta")
            if finish:
                if (type(frame.get("usage")) is not dict or
                    choice.get("finish_reason") not in (None, "length") or
                    not set(delta) <= {"content", "role", "tool_calls"} or
                    delta.get("content") not in (None, "") or
                    delta.get("tool_calls") not in (None, [])):
                    raise ValueError("payload after finish")
                continue
            if any(delta.get(k) for k in ("function_call", "refusal", "audio")):
                raise ValueError("unsupported channel")
            content = delta.get("content")
            if content is not None:
                if type(content) is not str:
                    raise ValueError("text type")
                text |= bool(content.strip())
            fragments = delta.get("tool_calls")
            if fragments is None:
                fragments = []
            if type(fragments) is not list or len(fragments) > 1:
                raise ValueError("one tool fragment")
            for part in fragments:
                tools = True
                if (type(part) is not dict or type(part.get("index")) is not int or
                    part["index"] != 0 or part.get("type") not in (None, "function")):
                    raise ValueError("indexed function")
                candidate = part.get("id")
                if candidate is not None:
                    if type(candidate) is not str or not candidate or identifier not in (None, candidate):
                        raise ValueError("conflicting tool id")
                    identifier = candidate
                function = part.get("function", {})
                if type(function) is not dict:
                    raise ValueError("function object")
                candidate = function.get("name")
                if candidate is not None:
                    if candidate != grammar.TOOL_NAME or name not in (None, candidate):
                        raise ValueError("tool name")
                    name = candidate
                if function.get("arguments") is not None and type(function["arguments"]) is not str:
                    raise ValueError("argument fragment type")
            if text and tools:
                raise ValueError("dual channels")
            if choice.get("finish_reason") is not None:
                if choice["finish_reason"] != "length":
                    raise ValueError("length only")
                finish = True
    if not finish:
        raise ValueError("missing length finish")
    return dict(text_present=text, tool_fragments_present=tools, action_decoded=False)


def classify(row, request, game, stage):
    """Never changes accepted-action criteria or the supplied evidence row."""
    result = previous.classify(row, request, game, stage)
    if result["status"] != "unsafe_failed":
        return result
    # The old validator reaches native_evidence ONLY after exact game/actor/
    # prompt/schema/request/hash/reservation and saved-assessment equality.
    # Never recover provenance errors merely because an SSE says 'length'.
    if "native_evidence" not in result:
        return result
    try:
        assessment = result["assessment"]
        stream = assessment["stream"]
        native = result["native_evidence"]
        usage = stream["usage"]
        count = native["reported_tokens"]
        if not (assessment["passed"] is True and stream["complete"] is True and
                stream["finish_reasons"] == ["length"] and
                native["present"] is True and
                type(usage["completion_tokens"]) is int and
                usage["completion_tokens"] == route.OUTPUT_BOUND and
                request["max_tokens"] == route.OUTPUT_BOUND and
                (count is None or type(count) is int and count >= 0)):
            return result
        channels = _length_channels(row["stream"])
    except (KeyError, ValueError, TypeError):
        return result
    return dict(**{k: deepcopy(v) for k, v in result.items()
                   if k not in ("status", "reason")},
        status="resource_failed", reason="verified_output_limit_no_action",
        independent_episode_safe=True, accepted_action=False,
        resource_failure=dict(version=VERSION, channels=channels,
            native_count_anomaly_retained=not native["reported_count_consistent"],
            raw_evidence_preserved=True, action_inferred=False))
