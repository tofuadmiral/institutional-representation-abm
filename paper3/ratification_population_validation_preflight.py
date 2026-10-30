"""Offline inventory, full-path reservations and budget checks for holdout.

This is not a paid runner or an authorization to launch one. The two batches
are solely a conservative reservation device; all 15 untouched games form a
single prewritten behavioral test, without interim outcome selection.
"""
from __future__ import annotations

from decimal import Decimal

from experiments import paper3_ratification_population_discovery as discovery
from paper3 import ratification_population_schedule as schedule


BATCH_GAMES = {1: tuple(range(9, 17)), 2: tuple(range(17, 24))}
BATCH_CAPS = {1: Decimal("3.10"), 2: Decimal("2.72")}
STOP = Decimal("8")


def assignments(batch):
    if batch not in BATCH_GAMES:
        raise ValueError("unknown holdout batch")
    rows = [row for row in schedule.assignments("validation")
            if row["game_id"] in BATCH_GAMES[batch]]
    if len(rows) != 4 * len(BATCH_GAMES[batch]):
        raise ValueError("holdout batch assignment inventory")
    return rows


def seeds(batch):
    return {row["seed_base"] + index for row in assignments(batch)
            for index in range(schedule.CALLS_PER_EPISODE)}


def scripted_preflight(batch):
    """Reserve every 16-action path at the maximum legal message length."""
    profiles = schedule.profiles("validation")
    reserved = []
    for row in assignments(batch):
        profile = profiles[row["profile_id"]]

        def scripted(actor, stage, messages, index):
            request = discovery.request(messages, row["seed_base"] + index)
            reserved.append(discovery.reservation(request))
            if stage in ("draft", "final"):
                return '{"policy":"C","message":"' + "x" * 1500 + '"}'
            if stage == "response":
                return ('{"support":true,"preferred_policy":"C",'
                        '"message":"' + "x" * 1500 + '"}')
            return '{"vote":true}'

        result = discovery.game.episode(profile, row["arm"], scripted)
        if result["calls"] != schedule.CALLS_PER_EPISODE:
            raise ValueError("holdout scripted path length")
    intended = len(assignments(batch)) * schedule.CALLS_PER_EPISODE
    total = sum((Decimal(item["reserved_usd"]) for item in reserved),
                Decimal("0"))
    if len(reserved) != intended or total > BATCH_CAPS[batch]:
        raise ValueError("holdout reservation exceeds cap")
    return dict(batch=batch, games=list(BATCH_GAMES[batch]),
                assigned_episodes=len(assignments(batch)),
                intended_calls=intended, reservation_usd=str(total),
                cap_usd=str(BATCH_CAPS[batch]))


def check_budget(snapshot, batch):
    """Use the *current* conservative ledger, not OpenRouter's credit view."""
    if batch not in BATCH_CAPS:
        raise ValueError("unknown holdout batch")
    accounted = Decimal(snapshot["accounted_usd"])
    if snapshot["pending"] != 0 or accounted + BATCH_CAPS[batch] >= STOP:
        raise ValueError("holdout allocation violates pending or $8 stop")
    return dict(batch=batch, accounted_usd=str(accounted),
                stage_cap_usd=str(BATCH_CAPS[batch]),
                conservative_after_cap_usd=str(accounted + BATCH_CAPS[batch]),
                stop_usd=str(STOP))


def verify_inventory():
    first, second = seeds(1), seeds(2)
    discovery_seeds = {
        row["seed_base"] + index
        for row in schedule.assignments("discovery")
        for index in range(schedule.CALLS_PER_EPISODE)
    }
    if first & second or first & discovery_seeds or second & discovery_seeds:
        raise ValueError("holdout seed overlap")
    if len(first) != 512 or len(second) != 448 or len(first | second) != 960:
        raise ValueError("holdout seed inventory")
    return dict(batch_1_calls=len(first), batch_2_calls=len(second),
                validation_calls=len(first | second),
                discovery_overlap=0, within_holdout_overlap=0)
