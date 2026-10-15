"""One toy opportunity witness for a possible distributive-rights study.

This is an existence proof, not a sampled profile population, a model
experiment, a frozen protocol, or a claim about likely LLM behavior. It
crosses the agenda holder's preferred compromise's pairwise coalition size
with whether that compromise maximizes aggregate citizen utility.
"""
from __future__ import annotations

from paper3 import amendment_institution as institution
from paper3 import direct_ratification as base


FAVORITE = "X"
OWN_COMPROMISE = "Y"
OTHER_COMPROMISE = "C"
ALIGNED_RIGHT_HOLDER = 1
OPPOSED_RIGHT_HOLDER = 6


def profile(own_coalition_size: int, own_welfare_high: bool):
    if own_coalition_size not in (4, 5) or type(own_welfare_high) is not bool:
        raise ValueError("unknown witness factor")
    overlap_own = 6 if own_welfare_high else 3
    overlap_other = 4 if own_welfare_high else 7
    rows = {
        0: (9, 5, 3),  # Agenda holder: favorite > own compromise > other.
        1: (3, 5, 2),  # Aligned right holder: sum favors Y, majority favors C.
        2: (3, 5, 4 if own_coalition_size == 4 else 2),
        3: (2, overlap_own, overlap_other),
        4: (2, overlap_own, overlap_other),
        5: (3, 4 if own_coalition_size == 5 else 2, 5),
        6: (3, 2, 5),  # Opposed right holder: sum favors C, majority favors Y.
    }
    districts = {}
    for actor, (favorite, own, other) in rows.items():
        districts[f"r{actor}"] = [
            dict(id=f"witness-{own_coalition_size}-{int(own_welfare_high)}-"
                    f"{actor}-{index}",
                 utility={FAVORITE: favorite,
                          OWN_COMPROMISE: (10 if index < 4 else 1)
                          if actor == ALIGNED_RIGHT_HOLDER else own,
                          OTHER_COMPROMISE: (10 if index < 4 else 1)
                          if actor == OPPOSED_RIGHT_HOLDER else other})
            for index in range(9)
        ]
    value = dict(id=f"distributive-witness-{own_coalition_size}-"
                    f"{int(own_welfare_high)}", proposer=0,
                 districts=districts)
    base.validate(value)
    return value


def opportunity(own_coalition_size: int, own_welfare_high: bool):
    value = profile(own_coalition_size, own_welfare_high)
    totals = base.district_totals(value)
    pairwise = {
        policy: tuple(actor for actor in base.ACTORS
                      if totals[f"r{actor}"][policy] >
                      totals[f"r{actor}"][FAVORITE])
        for policy in (OWN_COMPROMISE, OTHER_COMPROMISE)
    }
    welfare = {policy: sum(row[policy] for row in totals.values())
               for policy in base.POLICIES}
    if (len(pairwise[OWN_COMPROMISE]) != own_coalition_size or
            len(pairwise[OTHER_COMPROMISE]) != 9 - own_coalition_size or
            (welfare[OWN_COMPROMISE] > welfare[OTHER_COMPROMISE]) is not
            own_welfare_high):
        raise ValueError("witness factor construction failed")
    return dict(profile=value, pairwise_over_favorite=pairwise,
                total_citizen_utility=welfare,
                rights_holders=(ALIGNED_RIGHT_HOLDER,
                                OPPOSED_RIGHT_HOLDER))


def institution_item(witness, right_holder):
    if right_holder not in witness["rights_holders"]:
        raise ValueError("unknown right holder")
    item = dict(profile=witness["profile"], outsider=right_holder)
    institution.validate_item(item)
    return item
