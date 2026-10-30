"""Offline request and conservative cost plan for seven-profile B discovery."""
from __future__ import annotations

from decimal import Decimal
import json

from paper3 import constituent_b_gptoss_discovery_design as design
from paper3 import constituent_b_gptoss_simple_actions as interface
from paper3 import constituent_b_institution as institution


MODEL = interface.MODEL
PROVIDER_TAG = interface.PROVIDER_TAG
PROVIDER_NAME = interface.PROVIDER_NAME
OUTPUT_CAP = interface.OUTPUT_CAP
OUTPUT_BILLABLE_BOUND = interface.OUTPUT_BILLABLE_BOUND
INPUT_BOUND = interface.INPUT_BOUND
CAP = Decimal("3.00")
MAX_CALLS = len(design.assignments()) * design.CALLS_PER_EPISODE


def request(messages, seed, stage):
    case = dict(kind="action", stage=stage, messages=messages)
    return interface.request(case, seed)


def reservation(value):
    return interface.base.reservation(value)


def scripted_preflight():
    profiles = {item["prepared"]["contract_profile"]["id"]: item["prepared"]
                for item in design.profiles()}
    costs = []
    for assignment in design.assignments():
        prepared = profiles[assignment["profile_id"]]
        index = 0

        def ask(actor, stage, messages, position):
            nonlocal index
            if position != index:
                raise ValueError("scripted decision index changed")
            value = request(messages, assignment["seed_base"] + position, stage)
            costs.append(reservation(value))
            index += 1
            if stage in ("draft", "response", "final"):
                answer = dict(projects=dict(A="A0", B="B0"), first="A",
                              coalition=[0, 1, 3, 4], message="x" * 600)
                if stage == "response":
                    answer["support"] = True
            elif stage == "consent":
                answer = dict(consent=True)
            else:
                answer = dict(vote=True)
            return json.dumps(answer)

        outcome = institution.episode(prepared, assignment["arm"], ask)
        if outcome["calls"] != design.CALLS_PER_EPISODE:
            raise ValueError("scripted episode length changed")
    total = sum(Decimal(row["reserved_usd"]) for row in costs)
    if len(costs) != MAX_CALLS or total > CAP:
        raise ValueError("preflight exceeds call or dollar cap")
    return dict(intended_calls=len(costs),
                distinct_request_seeds=len({row["seed_base"] + position
                                            for row in design.assignments()
                                            for position in range(30)}),
                max_input_bound=max(row["input_token_bound"] for row in costs),
                full_output_scripted_reservations_usd=str(total),
                cap_usd=str(CAP))
