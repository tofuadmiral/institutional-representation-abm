"""Unallocated fixed-interface accountability discovery preflight.

Same two prospectively chosen matched frames, four arms, all citizen outcomes
and two-sided screen. No inherited qualification or model calls. The proposed
full-path cap exceeds remaining automatic-$8 headroom and needs new authority
before a frozen runner can be allocated. No truncated reasoning workaround.
"""
from decimal import Decimal
from functools import cache
from random import Random

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_labeled_discovery_requests as candidate
from paper3 import retrospective_labeled_interface as interface
from paper3 import retrospective_deepseek_route as route

FRAME_SEEDS = candidate.FRAME_SEEDS
DECISION_SEED_BASE = 3200000
ORDER_SEED = 3209999
PROPOSED_CAP = Decimal("5.10")

pairs = candidate.pairs


@cache
def assignments():
    rows = [dict(id=f"deepseek-accountability-{index}-{stratum}-{arm}",
                 seed=pair.seed, stratum=stratum, arm=arm, game=getattr(pair, stratum),
                 intended_calls=30, seed_base=DECISION_SEED_BASE + 64 * index)
            for index, pair in enumerate(pairs()) for stratum in ("aligned", "conflict")
            for arm in institution.ARMS]
    Random(ORDER_SEED).shuffle(rows)
    institution.require(len(rows) == 16 and len({row["id"] for row in rows}) == 16,
                        "sixteen full institution assignments")
    return tuple(rows)


def action_request(assignment, actor, identity, term, stage, context, index):
    institution.require(type(index) is int and 0 <= index < 30, "episode call index")
    game, arm = assignment["game"], assignment["arm"]
    messages = interface.messages(game, arm, actor, identity, term, stage, context)
    return route.request(interface.structured(messages, game, stage), assignment["seed_base"] + index)


@cache
def legal_history_bounds():
    """Compute actual new wire bytes over every legal first-term outcome.

No token estimates from favorable observed responses. Both longest passing
and rejecting public histories, maximum-length escaped messages, all policy
IDs and all four institutional arms; private reasoning is not public memory.
"""
    report = []
    for assignment in assignments():
        maxima = [0] * 30
        for policy, passing in [(p, True) for p in range(6)] + [(0, False)]:
            def ask(actor, identity, term, stage, context, index):
                request = action_request(assignment, actor, identity, term, stage, context, index)
                maxima[index] = max(maxima[index], route.reservation(request)["input_token_bound"])
                if stage in ("draft", "final"):
                    return dict(policy=policy if term == 0 else 5, message="\\" * 128)
                if stage == "response":
                    return dict(support=False, counter_policy=5, message="\\" * 128)
                return dict(vote=actor < 4 if passing else False)
            institution.episode(assignment["game"], assignment["arm"], ask)
        amount = sum((Decimal(bound) * route.PRICE_IN + Decimal(route.OUTPUT_BOUND) *
                      route.PRICE_OUT) / 1000000 for bound in maxima)
        report.append(dict(id=assignment["id"], input_bounds=tuple(maxima), reserved_usd=str(amount)))
    total = sum(Decimal(row["reserved_usd"]) for row in report)
    institution.require(total <= PROPOSED_CAP, "proposed full-path cap insufficient")
    return dict(assignments=tuple(report), maximum_calls=480, reservation_usd=str(total),
                proposed_cap_usd=str(PROPOSED_CAP),
                maximum_input_bound=max(max(row["input_bounds"]) for row in report),
                output_bound=route.OUTPUT_BOUND, context_floor=route.CONTEXT,
                qualification_inherited=False, allocation_authorized=False,
                cumulative_authority_extended=False,
                limitation="Offline preflight only: qualification pass, budget decision, tests and separate protocol freeze are required before any model calls.")
