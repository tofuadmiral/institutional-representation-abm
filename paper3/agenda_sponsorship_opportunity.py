"""Offline opportunity frame for exclusive, outsider-sponsored agenda motions.

No model call, frozen protocol, or behavioral result is implied. Six outsiders
may each sponsor one of two rival compromise motions or neither; four matching
sponsors put a motion on the floor. A pre-filed chair policy is the fallback.
The pure certificate below checks that both rival motions *could* qualify,
while sincere first-choice sponsorship can either qualify one or split 3-3.
"""
from __future__ import annotations

import random

from paper3 import direct_ratification as base


STRUCTURES = ("split", "aligned_y", "aligned_c")
WELFARE = ("y_high", "c_high")
ORDER_STRATA = ("flexible_first", "flexible_last")
OFFSETS = (-1, -1, 0, 0, 0, 0, 0, 1, 1)


def draw(structure: str, welfare: str, seed: int,
         role_permutation=None, label_permutation=None) -> dict:
    """Condition one fresh 63-citizen payoff draw on a fixed opportunity rule.

    Each rejection is purely structural and is counted. No LLM behavior is
    involved. The returned distribution is opportunity-conditioned, not a
    random sample of electorates or of all possible utility tables.
    """
    if structure not in STRUCTURES or welfare not in WELFARE or type(seed) is not int:
        raise ValueError("unknown sponsorship factor")
    rng = random.Random(seed)
    if role_permutation is not None and (type(role_permutation) is not tuple or
                                         set(role_permutation) != set(base.ACTORS) or
                                         len(role_permutation) != 7):
        raise ValueError("invalid role permutation")
    if label_permutation is not None and (type(label_permutation) is not tuple or
                                          set(label_permutation) != set(base.POLICIES) or
                                          len(label_permutation) != 3):
        raise ValueError("invalid label permutation")
    roles = (list(role_permutation) if role_permutation is not None else
             rng.sample(list(base.ACTORS), len(base.ACTORS)))
    labels = (list(label_permutation) if label_permutation is not None else
              rng.sample(list(base.POLICIES), len(base.POLICIES)))
    favorite, y, c = labels
    y_core = 7 if welfare == "y_high" else 5
    c_core = 5 if welfare == "y_high" else 8
    flexible_tops = {"split": (y, c), "aligned_y": (y, y),
                     "aligned_c": (c, c)}[structure]
    for attempt in range(1, 501):
        rows = [(9, rng.choice((4, 5)), rng.choice((2, 3)))]
        rows.extend((rng.choice((-3, -2)), y_core + rng.choice((0, 1)),
                     rng.choice((-3, -2))) for _ in range(2))
        for top in flexible_tops:
            rows.append((rng.choice((-3, -2)),
                         rng.choice((6, 7)) if top == y else rng.choice((4, 5)),
                         rng.choice((6, 7)) if top == c else rng.choice((4, 5))))
        rows.extend((rng.choice((-3, -2)), rng.choice((-3, -2)),
                     c_core + rng.choice((0, 1))) for _ in range(2))
        districts = {}
        for canonical, values in enumerate(rows):
            actor = roles[canonical]
            per_policy = [rng.sample(OFFSETS, len(OFFSETS)) for _ in values]
            districts[f"r{actor}"] = [
                dict(id=f"sponsorship-{structure}-{welfare}-{seed}-r{actor}-c{index}",
                     utility={label: value + per_policy[column][index]
                              for column, (label, value) in enumerate(zip(labels, values))})
                for index in range(9)
            ]
        profile = dict(id=f"sponsorship-{structure}-{welfare}-{seed}",
                       proposer=roles[0], districts=districts)
        item = dict(profile=profile, structure=structure, welfare=welfare,
                    chair=roles[0], outsiders=tuple(roles[1:]),
                    flexible=tuple(roles[3:5]), favorite=favorite,
                    compromises=(y, c), canonical_roles=tuple(roles),
                    draw_attempts=attempt)
        try:
            certificate(item)
        except ValueError:
            continue
        return item
    raise ValueError("no qualified sponsorship profile in 500 draws")


def with_order(item: dict, order_stratum: str, seed: int) -> dict:
    """Assign a public-order stratum; sealed calls ignore earlier filings."""
    certificate(item)
    if order_stratum not in ORDER_STRATA or type(seed) is not int:
        raise ValueError("unknown sponsorship order")
    rng = random.Random(seed)
    flexible = rng.sample(list(item["flexible"]), 2)
    core = rng.sample([actor for actor in item["outsiders"]
                       if actor not in item["flexible"]], 4)
    order = (flexible + core if order_stratum == "flexible_first"
             else core + flexible)
    return {**item, "sponsor_order": tuple(order),
            "order_stratum": order_stratum, "order_seed": seed}


def certificate(item: dict) -> dict:
    """Verify opportunity using fixed sincere actions, not model predictions."""
    profile = item["profile"]
    base.validate(profile)
    if profile["proposer"] != item["chair"]:
        raise ValueError("chair mismatch")
    favorite = item["favorite"]
    y, c = item["compromises"]
    totals = base.district_totals(profile)
    chair = item["chair"]
    outsiders = item["outsiders"]
    if (len(outsiders) != 6 or set(outsiders) != set(base.ACTORS) - {chair}
            or set(item["flexible"]) != set(item["canonical_roles"][3:5])):
        raise ValueError("role frame mismatch")
    if not totals[f"r{chair}"][favorite] > max(totals[f"r{chair}"][y],
                                                totals[f"r{chair}"][c]):
        raise ValueError("chair favorite mismatch")
    potential = {policy: tuple(actor for actor in outsiders
                               if totals[f"r{actor}"][policy] >
                               max(0, totals[f"r{actor}"][favorite]))
                 for policy in (y, c)}
    sincere = {actor: max((y, c), key=lambda p: totals[f"r{actor}"][p])
               for actor in outsiders}
    if any(totals[f"r{actor}"][y] == totals[f"r{actor}"][c]
           for actor in outsiders):
        raise ValueError("indifferent sincere sponsor")
    counts = {policy: sum(choice == policy for choice in sincere.values())
              for policy in (y, c)}
    expected = {"split": (3, 3), "aligned_y": (4, 2),
                "aligned_c": (2, 4)}[item["structure"]]
    if (tuple(counts.values()) != expected or
            any(len(supporters) != 4 for supporters in potential.values()) or
            any(sum(totals[f"r{actor}"][policy] > 0 for actor in base.ACTORS) != 5
                for policy in (y, c))):
        raise ValueError("sponsorship opportunity failed")
    welfare = {policy: sum(row[policy] for row in totals.values())
               for policy in (y, c)}
    if not ((item["welfare"] == "y_high" and welfare[y] > welfare[c]) or
            (item["welfare"] == "c_high" and welfare[c] > welfare[y])):
        raise ValueError("welfare factor failed")
    # The two outsider cores oppose the rival compromise; concessions must
    # come from the two flexible representatives, not from a harmed core.
    roles = item["canonical_roles"]
    if (any(totals[f"r{actor}"][c] >= 0 for actor in roles[1:3]) or
            any(totals[f"r{actor}"][y] >= 0 for actor in roles[5:7]) or
            any(min(totals[f"r{actor}"][y], totals[f"r{actor}"][c]) <= 0
                for actor in item["flexible"])):
        raise ValueError("distributional frame failed")
    return dict(profile_id=profile["id"], structure=item["structure"],
                welfare=item["welfare"], favorite=favorite,
                compromises=(y, c), sincere_sponsors=sincere,
                sincere_counts=counts, potential_sponsors=potential,
                total_citizen_utility=welfare,
                sincere_qualifies=any(count >= 4 for count in counts.values()))
