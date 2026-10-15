"""Offline payoff-card discovery bounds; no runner, qualification or allocation.

Preserves the preselected matched electorates, all four arms, two-sided screen
and full native reasoning allowance. An actual launch would require separate
qualification, source freeze and sufficient cumulative spending authority.
"""
from decimal import Decimal
from functools import cache
from random import Random

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_labeled_discovery_requests as candidate
from paper3 import retrospective_keyed_interface as interface
from paper3 import retrospective_deepseek_route as route

FRAME_SEEDS = candidate.FRAME_SEEDS
DECISION_SEED_BASE = 3260000
ORDER_SEED = 3269999
pairs = candidate.pairs


@cache
def assignments():
    rows = [dict(id=f"keyed-accountability-{index}-{stratum}-{arm}",
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
    report = []
    for assignment in assignments():
        maxima = [0] * 30
        width = len(assignment["game"].utilities[0][0][0])
        for policy, passing in [(p, True) for p in range(width)] + [(0, False)]:
            def ask(actor, identity, term, stage, context, index):
                request = action_request(assignment, actor, identity, term, stage, context, index)
                maxima[index] = max(maxima[index], route.reservation(request)["input_token_bound"])
                if stage in ("draft", "final"):
                    return dict(policy=policy if term == 0 else width - 1, message="\\" * 128)
                if stage == "response":
                    return dict(support=False, counter_policy=width - 1, message="\\" * 128)
                return dict(vote=actor < 4 if passing else False)
            institution.episode(assignment["game"], assignment["arm"], ask)
        amount = sum((Decimal(bound) * route.PRICE_IN + Decimal(route.OUTPUT_BOUND) * route.PRICE_OUT)
                     / 1000000 for bound in maxima)
        report.append(dict(id=assignment["id"], input_bounds=tuple(maxima), reserved_usd=str(amount)))
    return dict(assignments=tuple(report), maximum_calls=480,
        reservation_usd=str(sum(Decimal(r["reserved_usd"]) for r in report)),
        maximum_input_bound=max(max(r["input_bounds"]) for r in report),
        output_bound=route.OUTPUT_BOUND, context_floor=route.CONTEXT,
        qualification_inherited=False, allocation_authorized=False, cumulative_authority_extended=False,
        limitation="Offline-only byte bounds, not token usage or expected price; no executor or allocation. Qualification, cumulative authority and separate protocol freeze required.")
