"""Offline candidate: equivalent nullable integers, no calls or qualification.

Only changes flat object-property schemas from type=[integer,null] to an
anyOf of those types. Messages, answers, decoders and exact scoring stay fixed.
Provider support is unproven. Closed run sources must never import this module.
"""
from copy import deepcopy


def nullable_integers(parameters):
    """Fail closed on other union forms; preserve every sibling constraint.

The type union is a disjunction; anyOf of the same types is the same
disjunction. All other keywords continue to apply at the original property.
This is deliberately not a general recursive JSON Schema normalizer.
"""
    if (type(parameters) is not dict or parameters.get("type") != "object"
            or type(parameters.get("properties")) is not dict):
        raise ValueError("flat object-property schema required")
    result = deepcopy(parameters)
    for value in result["properties"].values():
        if type(value) is not dict:
            raise ValueError("property schema must be an object")
        kind = value.get("type")
        if type(kind) is list:
            if (len(kind) != 2 or set(kind) != {"integer", "null"}
                    or "anyOf" in value):
                raise ValueError("unsupported union or existing anyOf")
            value.pop("type")
            value["anyOf"] = [dict(type=t) for t in kind]
    return result


def fragment(original):
    """Copy one AUTO-tool request fragment; change only its parameter schema."""
    if (type(original) is not dict or original.get("tool_choice") != "auto"
            or type(original.get("tools")) is not list or len(original["tools"]) != 1
            or original["tools"][0].get("type") != "function"):
        raise ValueError("one automatic function-tool fragment required")
    result = deepcopy(original)
    function = result["tools"][0]["function"]
    function["parameters"] = nullable_integers(function["parameters"])
    return result
