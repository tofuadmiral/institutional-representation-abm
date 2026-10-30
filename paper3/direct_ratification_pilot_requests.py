"""Conservative full-path request and cost preflight for the Qwen pilot."""
from __future__ import annotations

from decimal import Decimal

from experiments import paper3_qwen_channel_gate as channel
from paper3 import direct_ratification as game
from paper3 import direct_ratification_pilot_design as design


CAP = Decimal("1.75")
MAX_CALLS = len(design.assignments()) * design.CALLS_PER_EPISODE


def request(messages, seed):
    return channel.request_for(messages, seed)


def reservation(value):
    wire = channel.t.canonical(value)
    bound = len(wire.encode()) + 1024
    if bound + channel.CONFIG["output_bound"] > channel.CONTEXT:
        raise ValueError("conservative Qwen context bound exceeded")
    cost = ((Decimal(bound) * channel.PRICE_IN +
             Decimal(channel.CONFIG["output_bound"]) * channel.PRICE_OUT) /
            Decimal(1000000))
    return dict(wire=wire, input_token_bound=bound, reserved_usd=str(cost))


def scripted_preflight():
    profiles = {row["profile"]["id"]: row["profile"]
                for row in design.profiles()}
    reservations = []
    for assignment in design.assignments():
        profile = profiles[assignment["profile_id"]]

        def ask(actor, stage, messages, index):
            req = request(messages, assignment["seed_base"] + index)
            reservations.append(reservation(req))
            if stage in ("draft", "final"):
                return '{"policy":"C","message":"' + "x" * 400 + '"}'
            if stage == "response":
                return '{"support":true,"preferred_policy":"C","message":"' + "x" * 400 + '"}'
            return '{"vote":true}'

        completed = game.episode(profile, assignment["arm"], ask)
        if completed["calls"] != design.CALLS_PER_EPISODE:
            raise ValueError("scripted episode length")
    total = sum(Decimal(row["reserved_usd"]) for row in reservations)
    if len(reservations) != MAX_CALLS or total > CAP:
        raise ValueError("full-path pilot reservation exceeds cap")
    return dict(intended_calls=MAX_CALLS,
                distinct_request_seeds=len({a["seed_base"] + i
                                            for a in design.assignments()
                                            for i in range(design.CALLS_PER_EPISODE)}),
                max_input_bound=max(row["input_token_bound"]
                                    for row in reservations),
                full_output_scripted_reservations_usd=str(total),
                cap_usd=str(CAP))
