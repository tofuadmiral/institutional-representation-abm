"""Offline candidate population for a fresh constituent-ratification study.

This is a *design candidate*, not a frozen assignment or authorization to run
model calls. Profiles are sampled from a documented opportunity-conditioned
synthetic family. The 4/9 and 5/9 versions preserve every district's policy
sum; only the distribution of one district's favorite-policy payoffs changes.
"""
from __future__ import annotations

from copy import deepcopy
import random

from paper3 import direct_ratification as institution


FRAME_SEED = 2026092817
GAME_COUNT = 24


def _positive_outsider_values(rng):
    """Four beneficiaries, five losers, positive cardinal sum and a legal flip."""
    for attempt in range(1, 1001):
        values = [rng.randint(4, 10) for _ in range(4)]
        values += [-rng.randint(1, 4) for _ in range(5)]
        rng.shuffle(values)
        if sum(values) <= 0:
            continue
        eligible = [(p, n) for p in range(9) for n in range(9)
                    if values[p] > 0 and values[n] < 0 and
                    values[p] > 1 - values[n]]
        if eligible:
            return values, rng.choice(eligible), attempt
    raise ValueError("outsider generation exhausted")


def _majority_approved_but_cardinally_harmful(rng):
    values = [rng.randint(1, 2) for _ in range(5)]
    values += [-rng.randint(3, 5) for _ in range(4)]
    rng.shuffle(values)
    if sum(values) >= 0:
        raise ValueError("majority/cardinal conflict disappeared")
    return values


def _positive_supporter(rng, low=1, high=4):
    return [rng.randint(low, high) for _ in range(9)]


def _proposer_alternatives(rng, high_is_a):
    """The agenda holder must have a strict ranking over the two live exits."""
    for attempt in range(1, 1001):
        high = _positive_supporter(rng, 2, 4)
        low = _positive_supporter(rng, 1, 3)
        if sum(high) > sum(low):
            return (high, low, attempt) if high_is_a else (low, high, attempt)
    raise ValueError("proposer alternatives exhausted")


def game_pair(game_id, seed=FRAME_SEED):
    """Return one independent payoff draw with matched veto/approval variants."""
    if type(game_id) is not int or not 0 <= game_id < GAME_COUNT:
        raise ValueError("game id")
    if type(seed) is not int:
        raise ValueError("seed")
    rng = random.Random(seed + 9973 * game_id)
    labels = list(institution.POLICIES)
    rng.shuffle(labels)
    favorite, alternative_a, alternative_b = labels
    outsider = rng.choice(institution.ACTORS)
    available = [a for a in institution.ACTORS if a != outsider]
    favorite_count = (4, 5, 6)[game_id % 3]
    favorite_seats = rng.sample(available, favorite_count)
    proposer = rng.choice(favorite_seats)
    alt_a_count = (4, 5)[game_id % 2]
    alt_b_count = (5, 4)[game_id % 2]
    alt_a_seats = {proposer, *rng.sample(
        [a for a in institution.ACTORS if a != proposer], alt_a_count - 1)}
    for _ in range(1000):
        alt_b_seats = {proposer, *rng.sample(
            [a for a in institution.ACTORS if a != proposer], alt_b_count - 1)}
        if len(alt_a_seats ^ alt_b_seats) >= 2:
            break
    else:
        raise ValueError("distinct alternative coalitions unavailable")
    districts = {}
    attempts = []
    outsider_flip = None
    for actor in institution.ACTORS:
        if actor == outsider:
            f_values, outsider_flip, n = _positive_outsider_values(rng)
            attempts.append(n)
        elif actor in favorite_seats:
            f_values = _positive_supporter(rng, 5, 8)
            attempts.append(1)
        else:
            f_values = _majority_approved_but_cardinally_harmful(rng)
            attempts.append(1)
        if actor == proposer:
            a_values, b_values, n = _proposer_alternatives(
                rng, high_is_a=game_id % 2 == 0)
            attempts[-1] += n - 1
        else:
            a_values = (_positive_supporter(rng) if actor in alt_a_seats else
                        _majority_approved_but_cardinally_harmful(rng))
            b_values = (_positive_supporter(rng) if actor in alt_b_seats else
                        _majority_approved_but_cardinally_harmful(rng))
        citizens = []
        for index in range(9):
            row = {favorite: f_values[index],
                   alternative_a: a_values[index],
                   alternative_b: b_values[index]}
            citizens.append(dict(id=f"citizen-{game_id:02d}-{actor}-{index}",
                                 utility=row))
        districts[f"r{actor}"] = citizens
    veto = dict(id=f"population-{game_id:02d}-veto", proposer=proposer,
                districts=districts)
    approve = deepcopy(veto)
    approve["id"] = f"population-{game_id:02d}-approve"
    positive, negative = outsider_flip
    source = approve["districts"][f"r{outsider}"]
    old_negative = source[negative]["utility"][favorite]
    delta = 1 - old_negative
    source[positive]["utility"][favorite] -= delta
    source[negative]["utility"][favorite] = 1
    for profile in (veto, approve):
        institution.validate(profile)
    if institution.district_totals(veto) != institution.district_totals(approve):
        raise ValueError("matched district sums changed")
    veto_counts = institution.poll(veto, favorite)["yes_counts"]
    approve_counts = institution.poll(approve, favorite)["yes_counts"]
    if (veto_counts[f"r{outsider}"] != 4 or
            approve_counts[f"r{outsider}"] != 5 or
            any(count < 5 for actor, count in veto_counts.items()
                if actor != f"r{outsider}") or
            institution.poll(veto, favorite)["approved"] or
            not institution.poll(approve, favorite)["approved"] or
            not institution.poll(veto, alternative_a)["approved"] or
            not institution.poll(veto, alternative_b)["approved"]):
        raise ValueError("referendum opportunity changed")
    totals = institution.district_totals(veto)
    if (sum(totals[f"r{a}"][favorite] > 0 for a in institution.ACTORS) < 4 or
            {a for a in institution.ACTORS
             if totals[f"r{a}"][alternative_a] > 0} != alt_a_seats or
            {a for a in institution.ACTORS
             if totals[f"r{a}"][alternative_b] > 0} != alt_b_seats or
            totals[f"r{proposer}"][favorite] <=
            max(totals[f"r{proposer}"][alternative_a],
                totals[f"r{proposer}"][alternative_b]) or
            totals[f"r{proposer}"][alternative_a] ==
            totals[f"r{proposer}"][alternative_b]):
        raise ValueError("chamber opportunity changed")
    return dict(game_id=game_id, favorite=favorite,
                alternative_a=alternative_a, alternative_b=alternative_b,
                proposer=proposer, outsider=outsider,
                favorite_seats=tuple(sorted(favorite_seats)),
                alternative_a_seats=tuple(sorted(alt_a_seats)),
                alternative_b_seats=tuple(sorted(alt_b_seats)),
                construction_attempts=tuple(attempts),
                veto=veto, approve=approve)


def inventory(count=GAME_COUNT, seed=FRAME_SEED):
    if type(count) is not int or not 0 <= count <= GAME_COUNT:
        raise ValueError("count")
    return [game_pair(i, seed) for i in range(count)]
