"""Candidate synthetic election profiles; not a frozen or allocated run.

Two conflict profiles vary the focal representative's seat, supporter seats,
citizen values, and the mandate-election payoff gap. Two controls separate
majority alignment and the office incentive. These are purpose-built cases,
not independent draws from a population of legislatures.
"""
from __future__ import annotations

from paper3 import electoral_accountability as game


SPECS = (
    dict(id="credit-conflict-a", focal=3, supporters=(0, 1, 2),
         focal_values=(-2, -2, -2, -2, -2, 8, 8, 8, 8), office_bonus=30),
    dict(id="credit-conflict-b", focal=5, supporters=(0, 2, 6),
         focal_values=(9, -3, 9, -3, -3, 9, -3, 9, -3), office_bonus=30),
    dict(id="credit-aligned-control", focal=4, supporters=(0, 1, 2),
         focal_values=(3, -1, 3, -1, 3, -1, 3, -1, 3), office_bonus=30),
    dict(id="credit-no-office-control", focal=3, supporters=(0, 1, 2),
         focal_values=(-2, -2, -2, -2, -2, 8, 8, 8, 8), office_bonus=0),
)


def profile(spec):
    focal = spec["focal"]
    supporters = set(spec["supporters"])
    if focal in supporters or len(supporters) != 3:
        raise ValueError("exactly three nonfocal supporter seats required")
    districts = {}
    for actor in game.ACTORS:
        values = (spec["focal_values"] if actor == focal else
                  ((2,) * 9 if actor in supporters else (-2,) * 9))
        districts[f"r{actor}"] = [dict(id=f"{spec['id']}-c{actor}-{index}", p=value)
                                 for index, value in enumerate(values)]
    item = dict(id=spec["id"], focal=focal, districts=districts,
                office_bonus=spec["office_bonus"])
    game.validate(item)
    return item


def inventory():
    return [dict(id=spec["id"], focal=spec["focal"],
                 supporters=spec["supporters"],
                 focal_sum=sum(spec["focal_values"]),
                 focal_approval=sum(value > 0 for value in spec["focal_values"]),
                 office_bonus=spec["office_bonus"], profile=profile(spec))
            for spec in SPECS]


def candidate_assignments():
    """One-block 4-profile x 4-arm inventory; seeds/requests are not fixed."""
    return [dict(id=f"{item['id']}--{arm}", profile_id=item["id"], arm=arm)
            for item in inventory() for arm in game.ARMS]
