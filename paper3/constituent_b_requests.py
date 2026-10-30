"""Unfrozen candidate OpenRouter requests and conservative cost bounds.

No network, credential or ledger access here. A separately approved runner
must recheck live endpoint metadata, exact source closure, historical seeds,
each request reservation and every certified/uncertified cost before inference.
"""
from __future__ import annotations

from decimal import Decimal
import json
import random

from paper3 import coalition_contracts as game
from paper3 import constituent_b_design as design
from paper3 import constituent_b_gate as gate
from paper3 import constituent_b_institution as institution


MODEL = "deepseek/deepseek-v3.2"
PROVIDER_TAG = "deepinfra/fp4"
PROVIDER_NAME = "DeepInfra"
PRICE_INPUT_PER_M = Decimal("0.26")
PRICE_OUTPUT_PER_M = Decimal("0.38")
OUTPUT_CAP = 16384
OUTPUT_BILLABLE_BOUND = 16400
INPUT_BOUND = 20000
GATE_SEED_BASE = 641900
DISCOVERY_FRAME_SEED = 641001
DISCOVERY_SEED_BASE = 642000
GATE_CAP = Decimal("0.15")
DISCOVERY_CAP = Decimal("4.00")


def _object(properties):
    return dict(type="object", properties=properties,
                required=list(properties), additionalProperties=False)


def schema(kind, stage=None, name=None):
    if kind == "fact":
        if name is None:
            raise ValueError("factual case name required")
        if name.startswith("mandate-"):
            return _object(dict(district_total_utility=dict(type="integer"),
                                citizens_better_than_q=dict(type="integer"),
                                citizens_worse_than_q=dict(type="integer")))
        if name.startswith("contract-"):
            return _object(dict(agreement_active=dict(type="boolean"),
                                executed_yes_count=dict(type="integer"),
                                project_passed=dict(type="boolean")))
        raise ValueError("unknown factual case")
    if kind != "action":
        raise ValueError("unknown request kind")
    if stage in ("draft", "response", "final"):
        projects = _object(dict(A=dict(type="string", enum=list(game.PROJECTS["A"])),
                                B=dict(type="string", enum=list(game.PROJECTS["B"]))))
        properties = dict(projects=projects, first=dict(type="string", enum=["A", "B"]),
                          coalition=dict(type="array", items=dict(type="integer", minimum=0,
                                                                    maximum=6),
                                         minItems=0, maxItems=4, uniqueItems=True),
                          message=dict(type="string", maxLength=600))
        if stage == "response":
            properties["support"] = dict(type="boolean")
        return _object(properties)
    if stage == "consent":
        return _object(dict(consent=dict(type="boolean")))
    if stage in ("first_vote", "second_vote"):
        return _object(dict(vote=dict(type="boolean")))
    raise ValueError("unknown action stage")


def request(messages, seed, *, kind, stage=None, name=None):
    if type(seed) is not int or seed < 0 or type(messages) is not list:
        raise ValueError("invalid request input")
    shape = schema(kind, stage, name)
    schema_name = f"paper3_constituent_b_{stage or ('mandate' if name.startswith('mandate-') else 'contract')}"
    return dict(model=MODEL, messages=messages, seed=seed, max_tokens=OUTPUT_CAP,
                temperature=1, top_p=.95, top_k=20, min_p=0,
                presence_penalty=0, repetition_penalty=1,
                reasoning=dict(enabled=True, exclude=False),
                response_format=dict(type="json_schema", json_schema=dict(
                    name=schema_name, strict=True, schema=shape)),
                stream=True, usage=dict(include=True), plugins=[],
                provider=dict(only=[PROVIDER_TAG], order=[PROVIDER_TAG],
                              allow_fallbacks=False, require_parameters=True,
                              quantizations=["fp4"],
                              max_price=dict(prompt=.26, completion=.38, request=0)))


def reservation(request_object):
    wire = json.dumps(request_object, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    input_upper = len(wire.encode()) + 1024
    if input_upper > INPUT_BOUND:
        raise ValueError("request exceeds conservative input bound")
    cost = ((Decimal(input_upper) * PRICE_INPUT_PER_M
             + Decimal(OUTPUT_BILLABLE_BOUND) * PRICE_OUTPUT_PER_M) / Decimal(1000000))
    return dict(wire=wire, input_token_bound=input_upper,
                reserved_usd=str(cost))


def gate_requests():
    output = []
    for index, case in enumerate(gate.cases()):
        req = request(case["messages"], GATE_SEED_BASE + index,
                      kind=case["kind"], stage=case.get("stage"), name=case["name"])
        output.append(dict(name=case["name"], seed=GATE_SEED_BASE + index,
                           request=req, **reservation(req)))
    if len(output) != 12 or sum(Decimal(x["reserved_usd"]) for x in output) > GATE_CAP:
        raise ValueError("gate exceeds proposed cap")
    return output


def discovery_assignments():
    assignments = design.schedule(DISCOVERY_FRAME_SEED, DISCOVERY_SEED_BASE)
    first_profile = design.frame(DISCOVERY_FRAME_SEED)[0]["prepared"]["contract_profile"]["id"]
    first = [row for row in assignments if row["profile_id"] == first_profile]
    rest = [row for row in assignments if row["profile_id"] != first_profile]
    random.Random(642999).shuffle(first)
    random.Random(643999).shuffle(rest)
    return [dict(id=f"episode-{index:02d}", phase=1 if index < 3 else 2,
                 intended_calls=30, **row)
            for index, row in enumerate(first + rest)]


def scripted_discovery_preflight():
    """Fabricated max-length messages exercise 360 request positions offline."""
    profiles = {item["prepared"]["contract_profile"]["id"]: item["prepared"]
                for item in design.frame(DISCOVERY_FRAME_SEED)}
    reservations = []
    for assignment in discovery_assignments():
        prepared = profiles[assignment["profile_id"]]
        counter = 0

        def ask(actor, stage, messages, index):
            nonlocal counter
            if index != counter:
                raise ValueError("decision index mismatch")
            req = request(messages, assignment["seed_base"] + index,
                          kind="action", stage=stage)
            reservations.append(reservation(req))
            counter += 1
            if stage in ("draft", "final", "response"):
                reply = dict(projects=dict(A="A0", B="B0"), first="A",
                             coalition=[0, 1, 3, 4], message="x" * 600)
                if stage == "response":
                    reply["support"] = True
            elif stage == "consent":
                reply = dict(consent=True)
            else:
                reply = dict(vote=False)
            return json.dumps(reply)

        outcome = institution.episode(prepared, assignment["arm"], ask)
        if outcome["calls"] != 30 or counter != 30:
            raise ValueError("scripted episode count mismatch")
    total = sum(Decimal(row["reserved_usd"]) for row in reservations)
    if len(reservations) != 360 or total > DISCOVERY_CAP:
        raise ValueError("scripted discovery exceeds proposed cap")
    return dict(intended_calls=360, max_input_bound=max(
                    row["input_token_bound"] for row in reservations),
                full_output_scripted_reservations_usd=str(total),
                cap_usd=str(DISCOVERY_CAP))
