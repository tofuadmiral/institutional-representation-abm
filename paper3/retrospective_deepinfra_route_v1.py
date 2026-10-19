"""Approved prospective DeepInfra FP4 route; no inherited provider pass.

Full sampling/native reasoning/AUTO configuration and prices stay fixed.
Provider compliance remains unproven. The first included institutional episode
is the technical shakedown; this module defines no standalone qualification.
No calls or institutional launch on import.
"""
from decimal import Decimal
import json

from paper3 import retrospective_accountability as institution

MODEL = "deepseek/deepseek-v3.2"
MODEL_ALIAS = MODEL + "-20251201"
PROVIDER = "DeepInfra"
TAG = "deepinfra/fp4"
PRICE_IN = Decimal(".26")
PRICE_OUT = Decimal(".38")
OUTPUT_BOUND = 14000
CONTEXT = 163840
METADATA_URL = "https://openrouter.ai/api/v1/models/" + MODEL + "/endpoints"


def request(fragment, seed):
    institution.require(type(seed) is int and seed >= 0, "request seed")
    institution.require(fragment["tool_choice"] == "auto" and len(fragment["tools"]) == 1,
                        "automatic single-tool interface")
    return dict(model=MODEL, **fragment, seed=seed, max_tokens=OUTPUT_BOUND,
        temperature=.6, top_p=.95, top_k=20, min_p=0, presence_penalty=0,
        repetition_penalty=1, reasoning=dict(enabled=True, exclude=False), stream=True,
        usage=dict(include=True), plugins=[],
        provider=dict(only=[TAG], order=[TAG], allow_fallbacks=False,
                      require_parameters=True, quantizations=["fp4"],
                      max_price=dict(prompt=float(PRICE_IN), completion=float(PRICE_OUT), request=0)))


def reservation(value):
    wire = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    bound = len(wire.encode()) + 1024
    institution.require(bound + OUTPUT_BOUND <= CONTEXT, "conservative context bound")
    cost = (Decimal(bound) * PRICE_IN + Decimal(OUTPUT_BOUND) * PRICE_OUT) / 1000000
    return dict(request_text=wire, input_token_bound=bound, reserved_usd=str(cost))


def check_endpoint(metadata):
    institution.require(metadata["data"]["id"] == MODEL, "metadata model")
    matches = [row for row in metadata["data"]["endpoints"] if row.get("tag") == TAG]
    institution.require(len(matches) == 1, "endpoint absent/ambiguous")
    endpoint = matches[0]
    institution.require(endpoint["provider_name"] == PROVIDER and endpoint["model_id"] == MODEL and
        endpoint["name"].split(" | ")[-1] == MODEL_ALIAS and
        endpoint["quantization"] == "fp4" and endpoint["status"] == 0, "endpoint identity/status")
    institution.require(endpoint["context_length"] >= CONTEXT and
        endpoint["max_completion_tokens"] >= OUTPUT_BOUND, "endpoint capacity")
    required = {"reasoning", "max_tokens", "temperature", "top_p", "top_k", "min_p",
                "seed", "presence_penalty", "repetition_penalty", "tools", "tool_choice"}
    institution.require(required <= set(endpoint["supported_parameters"]) and
        endpoint.get("supports_tool_choice", {}).get("auto") is True, "reasoning/auto unsupported")
    for key, ceiling in (("prompt", PRICE_IN), ("completion", PRICE_OUT)):
        observed = Decimal(endpoint["pricing"][key]) * 1000000
        institution.require(observed.is_finite() and 0 <= observed <= ceiling, "price ceiling")
    return endpoint
