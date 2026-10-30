"""Unfrozen institutional successor preflight; not an executable model runner.

Same scientific contrast and two-sided screen, fresh matched frames and seeds.
Requires the separately frozen labelled gate to pass before any allocation.
No inference, budget mutation or inherited qualification occurs here.
"""
from dataclasses import replace
from decimal import Decimal
from functools import cache
from random import Random

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design
from paper3 import retrospective_labeled_interface as interface
from paper3 import retrospective_requests as route

FRAME_SEEDS = (3171001, 3171002)
DECISION_SEED_BASE = 3180000
ORDER_SEED = 3189999
CAP = Decimal("2.90")


@cache
def pairs():
    rows = []
    for index, seed in enumerate(FRAME_SEEDS):
        pair = design.generate(seed)
        rows.append(replace(pair,
            aligned=replace(pair.aligned, game_id=f"electorate-{2 * index:03d}"),
            conflict=replace(pair.conflict, game_id=f"electorate-{2 * index + 1:03d}")))
    return tuple(rows)


@cache
def assignments():
    rows = [dict(id=f"labelled-accountability-{index}-{stratum}-{arm}",
                 seed=pair.seed, stratum=stratum, arm=arm, game=getattr(pair, stratum),
                 intended_calls=30, seed_base=DECISION_SEED_BASE + 64 * index)
            for index, pair in enumerate(pairs()) for stratum in ("aligned", "conflict")
            for arm in institution.ARMS]
    Random(ORDER_SEED).shuffle(rows)
    institution.require(len(rows) == 16 and len({row["id"] for row in rows}) == 16,
                        "sixteen fresh institution assignments")
    return tuple(rows)


def action_request(assignment, actor, identity, term, stage, context, index):
    institution.require(type(index) is int and 0 <= index < 30, "episode call index")
    game, arm = assignment["game"], assignment["arm"]
    messages = interface.messages(game, arm, actor, identity, term, stage, context)
    return route.request(interface.structured(messages, game, stage), assignment["seed_base"] + index)


@cache
def legal_history_bounds():
    """Recompute all six enacted histories and the longest rejecting history.

Every public message is filled to maximum serialized size. All IDs are one
digit; hidden reasoning is never history. This is a byte-based conservative
input reservation, not evidence of actual provider token use or competence.
"""
    report = []
    for assignment in assignments():
        maxima = [0] * 30
        for policy, passing in [(p, True) for p in range(6)] + [(0, False)]:
            def ask(actor, identity, term, stage, context, index):
                request = action_request(assignment, actor, identity, term, stage, context, index)
                bound = route.reservation(request)["input_token_bound"]
                maxima[index] = max(maxima[index], bound)
                if stage in ("draft", "final"):
                    return dict(policy=policy if term == 0 else 5, message="\\" * 128)
                if stage == "response":
                    return dict(support=False, counter_policy=5, message="\\" * 128)
                return dict(vote=actor < 4 if passing else False)
            institution.episode(assignment["game"], assignment["arm"], ask)
        amount = sum((Decimal(bound) * route.PRICE_IN +
                      Decimal(route.OUTPUT_BOUND) * route.PRICE_OUT) / 1000000 for bound in maxima)
        report.append(dict(id=assignment["id"], input_bounds=tuple(maxima), reserved_usd=str(amount)))
    total = sum(Decimal(row["reserved_usd"]) for row in report)
    institution.require(total <= CAP, "institutional successor cap insufficient")
    return dict(assignments=tuple(report), maximum_calls=480, reservation_usd=str(total),
                cap_usd=str(CAP), maximum_input_bound=max(max(row["input_bounds"]) for row in report),
                output_bound=route.OUTPUT_BOUND, context_floor=route.CONTEXT,
                qualification_inherited=False, allocation_authorized=False,
                limitation="Unfrozen offline preflight; gate pass and a separately frozen design/runner are prerequisites.")
