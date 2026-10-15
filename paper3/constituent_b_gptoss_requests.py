"""Offline request candidate for the fresh gpt-oss-120b gate only.

Live endpoint metadata, price, historical seeds and the shared budget must be
rechecked by the separately frozen runner before any request is sent.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json

from paper3 import constituent_b_gptoss_gate_design as design
from paper3 import constituent_b_requests as schema_source
from paper3 import constituent_b_tool_interface as tool_source


MODEL = "openai/gpt-oss-120b"
PROVIDER_TAG = "coreweave/fp4"
PROVIDER_NAME = "CoreWeave"
PRICE_INPUT_PER_M = Decimal("0.03")
PRICE_OUTPUT_PER_M = Decimal("0.17")
OUTPUT_CAP = 16384
OUTPUT_BILLABLE_BOUND = 16400
INPUT_BOUND = 20000
CAP = Decimal("0.10")
SEED_BASE = 662000
TOOL_NAME = "submit_decision"


def schema(case):
    if case["kind"] == "fact":
        if case["fact_type"] == "mandate":
            return schema_source.schema("fact", name="mandate-00")
        if case["fact_type"] == "contract":
            return schema_source.schema("fact", name="contract-00")
        raise ValueError("unknown fact type")
    return schema_source.schema("action", stage=case["stage"])


def request(case, seed):
    if type(seed) is not int or seed < 0:
        raise ValueError("nonnegative integer seed required")
    messages = deepcopy(case["messages"])
    replacements = 0
    for item in messages:
        if item["role"] == "system":
            replacements += item["content"].count(tool_source.OLD_INSTRUCTION)
            item["content"] = item["content"].replace(tool_source.OLD_INSTRUCTION,
                                                        tool_source.NEW_INSTRUCTION)
    if replacements != 1:
        raise ValueError("expected one output-channel instruction")
    return dict(
        model=MODEL, messages=messages, seed=seed, max_tokens=OUTPUT_CAP,
        temperature=1, top_p=.95,
        reasoning=dict(effort="medium", exclude=False),
        tools=[dict(type="function", function=dict(
            name=TOOL_NAME,
            description="Record the requested factual report or this representative's decision; the controller validates and applies its fields.",
            parameters=schema(case)))],
        tool_choice=dict(type="function", function=dict(name=TOOL_NAME)),
        stream=True, usage=dict(include=True), plugins=[],
        provider=dict(only=[PROVIDER_TAG], order=[PROVIDER_TAG],
                      allow_fallbacks=False, require_parameters=True,
                      quantizations=["fp4"],
                      max_price=dict(prompt=.03, completion=.17, request=0)),
    )


def reservation(value):
    wire = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    upper = len(wire.encode()) + 1024
    if upper > INPUT_BOUND:
        raise ValueError("conservative input bound exceeded")
    cost = ((Decimal(upper) * PRICE_INPUT_PER_M
             + Decimal(OUTPUT_BILLABLE_BOUND) * PRICE_OUTPUT_PER_M)
            / Decimal(1000000))
    return dict(wire=wire, input_token_bound=upper, reserved_usd=str(cost))


def cases():
    result = []
    for index, case in enumerate(design.cases()):
        value = request(case, SEED_BASE + index)
        result.append(dict(id=case["name"], context=case, request=value,
                           **reservation(value)))
    if len(result) != 12 or sum(Decimal(row["reserved_usd"])
                                for row in result) > CAP:
        raise ValueError("proposed gate exceeds call or dollar cap")
    return result
