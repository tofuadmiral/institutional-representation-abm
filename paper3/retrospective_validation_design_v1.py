"""Fresh validation inventory, selected without any new model observations."""
from dataclasses import replace
from decimal import Decimal
from functools import cache
from random import Random

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_analysis as science
from paper3 import retrospective_deepinfra_design_v1 as original
from paper3 import retrospective_deepinfra_requests_v1 as requests
from paper3 import retrospective_electorates as electorates
from paper3.retrospective_receipt_recovery_v1 import bind

FRAME_SEEDS = (2026102801, 2026102802)
ORDER_SEED = 2026102803
DECISION_SEED_BASE = 2026102900
FORMAT = "paper3-independent-validation-freeze-v1"
EXPECTED_FULL_BOUND = Decimal("8.78646588")


@cache
def pairs():
    return tuple(replace(p,
        aligned=replace(p.aligned, game_id=f"validation-electorate-{2*i:03d}"),
        conflict=replace(p.conflict, game_id=f"validation-electorate-{2*i+1:03d}"))
        for i, p in enumerate(electorates.generate(s) for s in FRAME_SEEDS))


@cache
def assignments():
    rows = [dict(id=f"validation-r1-{i}-{stratum}-{arm}", seed=p.seed,
        stratum=stratum, arm=arm, game=getattr(p, stratum), intended_calls=30,
        seed_base=DECISION_SEED_BASE + 64*i)
        for i, p in enumerate(pairs()) for stratum in science.STRATA
        for arm in institution.ARMS]
    Random(ORDER_SEED).shuffle(rows)
    result = tuple(rows)
    science.validate(result, {a["id"]: (None, None) for a in result})
    return result


@cache
def full_bound():
    blocks = tuple(dict(frame_seed=seed, **requests.block_bound(
        tuple(a for a in assignments() if a["seed"] == seed), 40)) for seed in FRAME_SEEDS)
    full = sum((Decimal(b["full_reservation_usd"]) for b in blocks), Decimal(0))
    institution.require(full == EXPECTED_FULL_BOUND, "approved entire-study bound changed")
    return dict(blocks=blocks, logical_calls=480, maximum_physical_calls=560,
                full_reservation_usd=str(full))


seed_audit = bind(original.seed_audit, FRAME_SEEDS=FRAME_SEEDS,
                  ORDER_SEED=ORDER_SEED, assignments=assignments, FORMAT=FORMAT)
