"""Prospective enforced-tool candidate only; no calls, gate inheritance or repair.

Native reasoning, route, completion and billing must still be checked by a
separately frozen runner. A supported tool-choice flag is not reliability proof.
"""
from copy import deepcopy

from paper3 import retrospective_action_contract_v2 as contract

VERSION = "required_submit_decision_v1"
INSTRUCTION = """Use native reasoning, then call submit_decision exactly once with the requested
fields. Submit a real function call, not a function name or JSON in final text.
The structured fields, not promises in a message, determine your action.
"""
CHOICE = dict(type="function", function=dict(name=contract.TOOL_NAME))


def fragment(value):
    """Only replace the output paragraph and enforce the sole named tool."""
    if (type(value) is not dict or value.get("tool_choice") != "auto"
            or len(value.get("tools", [])) != 1
            or value["tools"][0].get("type") != "function"
            or value["tools"][0].get("function", {}).get("name") != contract.TOOL_NAME
            or len(value.get("messages", [])) != 2
            or value["messages"][0] != dict(role="system", content=contract.SYSTEM)
            or value["messages"][1].get("role") != "user"):
        raise ValueError("unchanged single-tool dual-channel fragment required")
    result = deepcopy(value)
    result["messages"][0]["content"] = contract.SYSTEM.replace(contract.NEW, INSTRUCTION)
    result["tool_choice"] = deepcopy(CHOICE)
    return result


def check_support(endpoint):
    """Admission prerequisite, not permission to switch provider/precision."""
    if endpoint.get("status") != 0:
        raise ValueError("endpoint not healthy")
    if endpoint.get("supports_tool_choice", {}).get("function") is not True:
        raise ValueError("endpoint does not advertise enforced function choice")
    required = {"reasoning", "tools", "tool_choice"}
    if not required <= set(endpoint.get("supported_parameters", [])):
        raise ValueError("reasoning/tools/choice support missing")


def decision(trace):
    evidence = contract.decision(trace)
    if evidence["channel"] != "tool":
        raise ValueError("actual function call required; no final-text fallback")
    return evidence


def decode(game, stage, trace):
    decision(trace)
    return contract.decode(game, stage, trace)
