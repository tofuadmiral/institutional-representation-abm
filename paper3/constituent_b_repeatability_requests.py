"""Offline token-bound and cost preflight for the repeatability Qwen pilot."""
from __future__ import annotations

from decimal import Decimal
import json

from experiments import paper3_qwen_channel_gate as gate
from paper3 import constituent_b_institution as institution
from paper3 import constituent_b_repeatability_design as design


CAP = Decimal("4.25")
MAX_CALLS = len(design.assignments()) * design.CALLS_PER_EPISODE


def request(messages, seed):
    return gate.request_for(messages, seed)


def reservation(value):
    wire = gate.t.canonical(value)
    bound = len(wire.encode()) + 1024
    if bound + gate.CONFIG["output_bound"] > gate.CONTEXT:
        raise ValueError("conservative Qwen context bound exceeded")
    cost = ((Decimal(bound) * gate.PRICE_IN
             + Decimal(gate.CONFIG["output_bound"]) * gate.PRICE_OUT)
            / Decimal(1000000))
    return dict(wire=wire, input_token_bound=bound, reserved_usd=str(cost))


def scripted_preflight():
    profiles = {row["prepared"]["contract_profile"]["id"]: row["prepared"]
                for row in design.profiles()}
    reservations = []
    for assignment in design.assignments():
        prepared = profiles[assignment["profile_id"]]

        def ask(actor, stage, messages, index):
            req = request(messages, assignment["seed_base"] + index)
            reservations.append(reservation(req))
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
            raise ValueError("scripted Qwen episode length changed")
    total = sum(Decimal(row["reserved_usd"]) for row in reservations)
    if len(reservations) != MAX_CALLS or total > CAP:
        raise ValueError("Qwen repeatability preflight exceeds cap")
    return dict(intended_calls=len(reservations),
                distinct_request_seeds=len({assignment["seed_base"] + i
                                            for assignment in design.assignments()
                                            for i in range(30)}),
                max_input_bound=max(row["input_token_bound"] for row in reservations),
                full_output_scripted_reservations_usd=str(total),
                cap_usd=str(CAP))
