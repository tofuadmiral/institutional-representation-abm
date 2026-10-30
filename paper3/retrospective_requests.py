"""Prospective joint gate/discovery requests and legal-history cost bounds.

No network, credentials, budget allocation or model calls. Public metadata
must be fetched and frozen separately before launch. Automatic server tool
selection, strict one-function client acceptance; no prose fallback.
"""
from dataclasses import replace
from decimal import Decimal
from functools import cache
import json
from random import Random

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design
from paper3 import retrospective_interface as interface
from paper3 import retrospective_qualification as qualification

MODEL = "qwen/qwen3-32b"
MODEL_ALIAS = MODEL + "-04-28"
PROVIDER = "DeepInfra"
TAG = "deepinfra/fp8"
PRICE_IN = Decimal("0.08")
PRICE_OUT = Decimal("0.28")
OUTPUT_BOUND = 14000
CONTEXT = 40960
CAP = Decimal("2.90")
STOP = Decimal("8")
FRAME_SEEDS = (3101001, 3101002)
GATE_SEED_BASE = 3110000
DECISION_SEED_BASE = 3120000
ORDER_SEED = 3129999
METADATA_URL = "https://openrouter.ai/api/v1/models/" + MODEL + "/endpoints"


@cache
def pairs():
    values = []
    for index, seed in enumerate(FRAME_SEEDS):
        pair = design.generate(seed)
        # Opaque IDs avoid telling the model which distribution stratum it sees.
        values.append(replace(pair,
            aligned=replace(pair.aligned, game_id=f"electorate-{2 * index:03d}"),
            conflict=replace(pair.conflict, game_id=f"electorate-{2 * index + 1:03d}")))
    return tuple(values)


@cache
def assignments():
    rows = [dict(id=f"accountability-{index}-{stratum}-{arm}", seed=pair.seed,
                 stratum=stratum, arm=arm, game=getattr(pair, stratum), intended_calls=30,
                 seed_base=DECISION_SEED_BASE + 64 * index)
            for index, pair in enumerate(pairs()) for stratum in ("aligned", "conflict")
            for arm in institution.ARMS]
    Random(ORDER_SEED).shuffle(rows)
    institution.require(len(rows) == 16 and len({row["id"] for row in rows}) == 16,
                        "discovery assignment inventory")
    return tuple(rows)


def request(fragment, seed):
    institution.require(type(seed) is int and seed >= 0, "request seed")
    institution.require(fragment["tool_choice"] == "auto" and len(fragment["tools"]) == 1,
                        "automatic single-tool interface")
    return dict(model=MODEL, **fragment, seed=seed, max_tokens=OUTPUT_BOUND,
                temperature=.6, top_p=.95, top_k=20, min_p=0,
                presence_penalty=0, repetition_penalty=1,
                reasoning=dict(enabled=True, exclude=False), stream=True,
                usage=dict(include=True), plugins=[],
                provider=dict(only=[TAG], order=[TAG], allow_fallbacks=False,
                              require_parameters=True, quantizations=["fp8"],
                              max_price=dict(prompt=float(PRICE_IN), completion=float(PRICE_OUT),
                                             request=0)))


def reservation(value):
    wire = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    bound = len(wire.encode()) + 1024
    institution.require(bound + OUTPUT_BOUND <= CONTEXT, "conservative context bound")
    cost = (Decimal(bound) * PRICE_IN + Decimal(OUTPUT_BOUND) * PRICE_OUT) / 1000000
    return dict(request_text=wire, input_token_bound=bound, reserved_usd=str(cost))


@cache
def gate_requests():
    return tuple(dict(id=case["id"], context=case,
                      request=(value := request(qualification.structured(case), GATE_SEED_BASE + index)),
                      **reservation(value)) for index, case in enumerate(qualification.cases()))


def action_request(assignment, actor, identity, term, stage, context, index):
    institution.require(type(index) is int and 0 <= index < 30, "episode call position")
    game, arm = assignment["game"], assignment["arm"]
    messages = interface.messages(game, arm, actor, identity, term, stage, context)
    return request(interface.structured(messages, game, stage), assignment["seed_base"] + index)


def check_endpoint(metadata):
    institution.require(metadata["data"]["id"] == MODEL, "metadata model")
    matches = [row for row in metadata["data"]["endpoints"] if row.get("tag") == TAG]
    institution.require(len(matches) == 1, "endpoint absent/ambiguous")
    endpoint = matches[0]
    institution.require(endpoint["provider_name"] == PROVIDER and endpoint["model_id"] == MODEL and
                        endpoint["name"].split(" | ")[-1] == MODEL_ALIAS and
                        endpoint["quantization"] == "fp8" and endpoint["status"] == 0,
                        "endpoint identity/status")
    institution.require(endpoint["context_length"] >= CONTEXT and
                        endpoint["max_completion_tokens"] >= OUTPUT_BOUND, "endpoint capacity")
    required = {"reasoning", "max_tokens", "temperature", "top_p", "top_k", "min_p",
                "seed", "presence_penalty", "repetition_penalty", "tools", "tool_choice"}
    institution.require(required <= set(endpoint["supported_parameters"]) and
                        endpoint.get("supports_tool_choice", {}).get("auto") is True,
                        "automatic tool/reasoning parameters unsupported")
    for key, ceiling in (("prompt", PRICE_IN), ("completion", PRICE_OUT)):
        observed = Decimal(endpoint["pricing"][key]) * 1000000
        institution.require(observed.is_finite() and 0 <= observed <= ceiling, "price ceiling")
    return endpoint


@cache
def legal_history_bounds():
    """Upper request cost per action over legal prehistory/serialization states.

    Six possible enacted policies plus the longest rejecting (all-no) history.
    Minimal passing coalition gives the longest passing boolean serialization.
    All message slots use 128 backslashes: four UTF-8 wire bytes per character,
    a maximum also reached by four-byte Unicode. Non-text controls are illegal.
    Policy/actor IDs are single digits. False support fields are longest.
    Current sealed policy votes do not enter the next request. Native private
    reasoning and API envelopes are never replayed in institutional history.
    """
    report = []
    for assignment in assignments():
        maxima = [0] * 30
        for first_policy, passing in [(p, True) for p in range(6)] + [(0, False)]:
            def ask(actor, identity, term, stage, context, index):
                value = action_request(assignment, actor, identity, term, stage, context, index)
                maxima[index] = max(maxima[index], reservation(value)["input_token_bound"])
                policy = first_policy if term == 0 else 5
                if stage in ("draft", "final"):
                    return dict(policy=policy, message="\\" * 128)
                if stage == "response":
                    return dict(support=False, counter_policy=5, message="\\" * 128)
                return dict(vote=(actor < 4 if passing else False))
            institution.episode(assignment["game"], assignment["arm"], ask)
        report.append(dict(id=assignment["id"], input_bounds=tuple(maxima),
                           reserved_usd=str(sum((Decimal(bound) * PRICE_IN +
                           Decimal(OUTPUT_BOUND) * PRICE_OUT) / 1000000 for bound in maxima))))
    qualification_reserve = sum(Decimal(row["reserved_usd"]) for row in gate_requests())
    discovery_reserve = sum(Decimal(row["reserved_usd"]) for row in report)
    institution.require(qualification_reserve + discovery_reserve <= CAP, "joint cap insufficient")
    return dict(assignments=tuple(report), qualification_calls=18, discovery_calls=480,
                max_calls=498, qualification_reserve_usd=str(qualification_reserve),
                discovery_reserve_usd=str(discovery_reserve),
                joint_reserve_usd=str(qualification_reserve + discovery_reserve),
                cap_usd=str(CAP), context=CONTEXT, output_bound=OUTPUT_BOUND,
                endpoint_live_verified=False)
