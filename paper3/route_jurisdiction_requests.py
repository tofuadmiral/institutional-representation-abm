"""Candidate OpenRouter requests and conservative reservations; offline only.

This module cannot send requests or allocate budget. Model/provider metadata,
seed history, billing behavior, credentials and source closure still require a
fresh preflight and approved frozen runner before any hosted inference.
"""
from __future__ import annotations

from decimal import Decimal
import json
import random

from paper3 import route_jurisdiction as game
from paper3 import route_jurisdiction_design as design
from paper3 import route_jurisdiction_gate as gate


MODEL = "qwen/qwen3.5-35b-a3b"
PROVIDER_TAG = "darkbloom/fp4"
PRICE_INPUT_PER_M = Decimal("0.08")
PRICE_OUTPUT_PER_M = Decimal("0.75")
OUTPUT_CAP = 8192
OUTPUT_BILLABLE_BOUND = 8208
INPUT_BOUND = 10000
GATE_SEED_BASE = 362000
GATE_CAP = Decimal("0.15")
PILOT_SEED_BASE = 363000
PILOT_CAP = Decimal("1.00")


def action_schema(stage):
    policy = dict(type="string", enum=["q", "p0", "p1", "p2"])
    if stage == "recommendation":
        properties = dict(policy_id=policy)
    elif stage == "offer":
        properties = dict(policy_id=policy, route=dict(type="string", enum=["floor", "committee"]))
    elif stage == "ballot":
        properties = dict(yes=dict(type="boolean"))
    elif stage == "review":
        properties = dict(approve=dict(type="boolean"))
    else:
        raise ValueError("unknown action stage")
    return dict(type="object", properties=properties, required=list(properties), additionalProperties=False)


def rule_schema():
    properties = dict(outcome=dict(type="string", enum=["q", "p0", "p1", "p2"]),
                      review_binding=dict(type="boolean"),
                      own_best_policy=dict(type="string", enum=["q", "p0", "p1", "p2"]))
    return dict(type="object", properties=properties, required=list(properties), additionalProperties=False)


def request(messages, seed, *, kind, stage=None):
    if type(seed) is not int or seed < 0 or type(messages) is not list:
        raise ValueError("invalid request input")
    schema = rule_schema() if kind == "rule" and stage is None else (
        action_schema(stage) if kind == "action" else None)
    if schema is None:
        raise ValueError("unknown request kind")
    return dict(model=MODEL, messages=messages, seed=seed, max_tokens=OUTPUT_CAP,
                temperature=1.0, top_p=.95, top_k=20, presence_penalty=1.5,
                repetition_penalty=1, reasoning=dict(enabled=True, exclude=False),
                response_format=dict(type="json_schema", json_schema=dict(
                    name="paper3_route_" + (stage if stage else "rule"),
                    strict=True, schema=schema)),
                stream=True, usage=dict(include=True), plugins=[],
                provider=dict(only=[PROVIDER_TAG], order=[PROVIDER_TAG],
                              allow_fallbacks=False, require_parameters=True,
                              quantizations=["fp4"],
                              max_price=dict(prompt=.08, completion=.75, request=0)))


def reservation(request_object):
    wire = json.dumps(request_object, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    # JSON bytes + 1,024 deliberately overbounds tokenized input; admission
    # must stop if the bound exceeds the declared cap, not silently enlarge it.
    input_upper = len(wire.encode()) + 1024
    if input_upper > INPUT_BOUND:
        raise ValueError("request exceeds conservative input bound")
    cost = ((Decimal(input_upper) * PRICE_INPUT_PER_M
             + Decimal(OUTPUT_BILLABLE_BOUND) * PRICE_OUTPUT_PER_M) / Decimal(1000000))
    return dict(wire=wire, input_token_bound=input_upper, reserved_usd=str(cost))


def gate_requests():
    output = []
    for index, case in enumerate(gate.cases()):
        req = request(case["messages"], GATE_SEED_BASE + index,
                      kind=case["kind"], stage=case.get("stage"))
        output.append(dict(name=case["name"], seed=GATE_SEED_BASE + index,
                           request=req, **reservation(req)))
    if len(output) != 12 or sum(Decimal(x["reserved_usd"]) for x in output) > GATE_CAP:
        raise ValueError("gate exceeds proposed 12-call/$0.15 cap")
    return output


def pilot_assignments():
    """Four constructed profiles crossed with two review rules, 16 calls each."""
    discovery = [p for p in design.frame() if p["split"] == "discovery_candidate"]
    pairs = [(p, arm) for p in discovery for arm in game.ARMS]
    random.Random(363999).shuffle(pairs)
    return [dict(id=f"episode-{index:02d}", profile=p, arm=arm,
                 seed_base=PILOT_SEED_BASE + 16 * index, intended_calls=16)
            for index, (p, arm) in enumerate(pairs)]


def scripted_pilot_preflight():
    """Exercise every prompt position with fabricated actions, never a model.

    This demonstrates request-size feasibility for one deterministic path. The
    live runner must recheck every actual request and stop if its bound fails.
    """
    reservations = []
    for assignment in pilot_assignments():
        profile = assignment["profile"]
        counter = 0

        def ask(messages):
            nonlocal counter
            context = json.loads(messages[1]["content"].split("\n", 1)[0])
            stage = context["stage"]
            req = request(messages, assignment["seed_base"] + counter,
                          kind="action", stage=stage)
            reservations.append(reservation(req))
            counter += 1
            if stage == "recommendation":
                return '{"policy_id":"p0"}'
            if stage == "offer":
                return '{"policy_id":"p0","route":"floor"}'
            if stage == "ballot":
                actor = context["acting_for"]
                return json.dumps(dict(yes=profile["utilities"][actor]["p0"] > 0))
            reviewer = profile["reviewer"]
            return json.dumps(dict(approve=profile["utilities"][reviewer]["p0"] > 0))

        result = game.run_episode(profile, assignment["arm"], ask)
        if result["status"] != "completed" or counter != 16:
            raise ValueError("scripted preflight episode incomplete")
    total = sum(Decimal(r["reserved_usd"]) for r in reservations)
    if len(reservations) != 128 or total > PILOT_CAP:
        raise ValueError("scripted preflight exceeds proposed pilot cap")
    return dict(intended_calls=128, maximum_input_bound=max(r["input_token_bound"] for r in reservations),
                scripted_path_reservations_usd=str(total),
                hard_input_limit=INPUT_BOUND, hard_output_billable_limit=OUTPUT_BILLABLE_BOUND,
                cap_usd=str(PILOT_CAP))
