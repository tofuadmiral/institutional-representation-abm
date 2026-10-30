"""Fresh profiles for the bounded-advocacy common-transcript rerun.

The institutional estimand and two-sided discovery rule remain those of
the frozen v1 protocol, which stopped before either arm was observed.
"""
from __future__ import annotations

import random

from paper3 import agenda_common_design as prior
from paper3 import agenda_sponsorship_institution as game
from paper3 import agenda_sponsorship_opportunity as opportunity
from paper3 import direct_ratification as base


SEED_BASE = 1380000
ORDER_SEED = 2026100900
PROFILE_SPECS = tuple((structure, welfare, order, seed + 100)
                      for structure, welfare, order, seed in prior.PROFILE_SPECS)


def profiles():
    result = []
    for index, (structure, welfare, order, seed) in enumerate(PROFILE_SPECS):
        roles = tuple((index + actor + 3) % 7 for actor in range(7))
        labels = tuple(base.POLICIES[(index + offset + 1) % 3]
                       for offset in range(3))
        item = opportunity.draw(structure, welfare, seed,
                                role_permutation=roles,
                                label_permutation=labels)
        result.append(opportunity.with_order(item, order, seed + 307))
    if len(result) != 12 or len({row["profile"]["id"] for row in result}) != 12:
        raise ValueError("fresh profile inventory")
    return result


def assignments():
    rows = [dict(profile_id=item["profile"]["id"],
                 structure=item["structure"], welfare=item["welfare"],
                 order_stratum=item["order_stratum"])
            for item in profiles()]
    random.Random(ORDER_SEED).shuffle(rows)
    result = [dict(id=f"bounded-advocacy-{index:02d}",
                   seed_base=SEED_BASE + 64 * index,
                   arm_order=(list(game.ARMS) if index % 2 == 0
                              else list(reversed(game.ARMS))),
                   intended_calls=33, **row)
              for index, row in enumerate(rows)]
    seeds = [row["seed_base"] + offset for row in result
             for offset in range(33)]
    if len(result) != 12 or len(seeds) != 396 or len(set(seeds)) != 396:
        raise ValueError("fresh action seed inventory")
    return result


def screen(outcomes):
    """Same frozen 8-split/4-control two-sided selected-case rule as v1."""
    if type(outcomes) is not dict:
        raise ValueError("outcome map")
    items = {item["profile"]["id"]: item for item in profiles()}
    if not set(outcomes) <= {(pid, arm) for pid in items for arm in game.ARMS}:
        raise ValueError("unknown outcome assignment")
    rows = []
    for pid, item in items.items():
        sealed = outcomes.get((pid, "sealed"))
        public = outcomes.get((pid, "public_sequential"))
        if sealed is not None and (type(sealed) is not dict or
                                   sealed.get("arm") != "sealed"):
            raise ValueError("invalid sealed outcome")
        if public is not None and (type(public) is not dict or
                                   public.get("arm") != "public_sequential"):
            raise ValueError("invalid public outcome")
        complete = sealed is not None and public is not None
        delta = (public["enacted_total_citizen_utility"] -
                 sealed["enacted_total_citizen_utility"] if complete else None)
        floor_changed = (public["floor_policy"] != sealed["floor_policy"]
                         if complete else None)
        rows.append(dict(profile_id=pid, structure=item["structure"],
                         welfare=item["welfare"],
                         order_stratum=item["order_stratum"],
                         paired_complete=complete, welfare_delta=delta,
                         harmed_citizen_delta=(public["harmed_citizen_count"] -
                                               sealed["harmed_citizen_count"]
                                               if complete else None),
                         district_utility_delta=({district:
                             public["enacted_district_utility"][district] -
                             sealed["enacted_district_utility"][district]
                             for district in sealed["enacted_district_utility"]}
                             if complete else None),
                         floor_changed=floor_changed,
                         enacted_changed=(public["enacted_policy"] !=
                                          sealed["enacted_policy"]
                                          if complete else None),
                         public_benefit=(floor_changed and delta >= 18
                                         if complete else None),
                         public_harm=(floor_changed and delta <= -18
                                      if complete else None),
                         control_stable=(complete and
                             bool(public["qualified_motion"]) and
                             public["qualified_motion"] ==
                             sealed["qualified_motion"] and
                             public["floor_policy"] == sealed["floor_policy"] and
                             public["enacted_policy"] == sealed["enacted_policy"])
                             if item["structure"] != "split" else None))
    split = [row for row in rows if row["structure"] == "split"]
    controls = [row for row in rows if row["structure"] != "split"]
    missing = sum(not row["paired_complete"] for row in split)
    benefit = sum(row["public_benefit"] is True for row in split)
    harm = sum(row["public_harm"] is True for row in split)
    negative = sum(row["paired_complete"] and row["welfare_delta"] < 0
                   for row in split)
    positive = sum(row["paired_complete"] and row["welfare_delta"] > 0
                   for row in split)
    stable = sum(row["control_stable"] is True for row in controls)
    beneficial = stable >= 3 and benefit >= 6 and negative + missing <= 1
    harmful = stable >= 3 and harm >= 6 and positive + missing <= 1
    if beneficial:
        classification = "selected_case_public_benefit_lead"
    elif harmful:
        classification = "selected_case_public_harm_lead"
    elif missing > 1 or stable < 3:
        classification = "incomplete_or_control_failed"
    else:
        classification = "no_prespecified_constituent_lead"
    return dict(rows=rows, split_pairs_complete=8 - missing,
                stable_control_pairs=stable, public_benefit_pairs=benefit,
                public_harm_pairs=harm, negative_welfare_pairs=negative,
                positive_welfare_pairs=positive, missing_split_pairs=missing,
                beneficial_lead=beneficial, harmful_lead=harmful,
                classification=classification,
                caveat="Twelve fresh opportunity-conditioned selected profiles on one model; same v1 two-sided rule; not population or paper evidence. Every failure and person-level loss remains visible.")
