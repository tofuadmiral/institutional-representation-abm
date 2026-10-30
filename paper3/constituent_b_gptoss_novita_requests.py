"""Prospective gpt-oss/Novita provider gate; old frozen requests remain intact.

The same model and local action validator are retained. Only the route,
pricing ceiling, fresh seeds, and simpler tool-parameter schema differ.
This is an engineering qualification, not institutional evidence.
"""
from __future__ import annotations

from decimal import Decimal
import json

from paper3 import constituent_b_gptoss_gate_design as design
from paper3 import constituent_b_gptoss_simple_actions as simple


MODEL = simple.MODEL
PROVIDER_TAG = "novita/fp4"
PROVIDER_NAME = "Novita"
QUANTIZATION = "fp4"
PRICE_INPUT_PER_M = Decimal("0.05")
PRICE_OUTPUT_PER_M = Decimal("0.25")
OUTPUT_CAP = simple.OUTPUT_CAP
OUTPUT_BILLABLE_BOUND = simple.OUTPUT_BILLABLE_BOUND
INPUT_BOUND = simple.INPUT_BOUND
TOOL_NAME = simple.TOOL_NAME
SEED_BASE = 669000
CAP = Decimal("0.12")


def request(case, seed):
    value = (simple.request(case, seed) if case["kind"] == "action"
             else simple.base.request(case, seed))
    value["provider"] = dict(only=[PROVIDER_TAG], order=[PROVIDER_TAG],
                             allow_fallbacks=False, require_parameters=True,
                             quantizations=[QUANTIZATION],
                             max_price=dict(prompt=float(PRICE_INPUT_PER_M),
                                            completion=float(PRICE_OUTPUT_PER_M),
                                            request=0))
    return value


def reservation(value):
    wire = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    bound = len(wire.encode()) + 1024
    if bound > INPUT_BOUND:
        raise ValueError("conservative input bound exceeded")
    reserve = ((Decimal(bound) * PRICE_INPUT_PER_M
                + Decimal(OUTPUT_BILLABLE_BOUND) * PRICE_OUTPUT_PER_M)
               / Decimal(1000000))
    return dict(wire=wire, input_token_bound=bound, reserved_usd=str(reserve))


def cases():
    result = []
    for index, context in enumerate(design.cases()):
        req = request(context, SEED_BASE + index)
        result.append(dict(id=context["name"], context=context, request=req,
                           **reservation(req)))
    if len(result) != 12 or sum(Decimal(row["reserved_usd"])
                                for row in result) > CAP:
        raise ValueError("provider gate exceeds cap")
    return result
