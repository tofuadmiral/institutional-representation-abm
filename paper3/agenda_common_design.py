"""Prospective profile schedule and two-sided discovery screen.

The screen is a stringent selected-case triage, not a statistical test or
publication claim. No profiles are chosen using model outcomes.
"""
from __future__ import annotations

import random

from paper3 import agenda_sponsorship_institution as game
from paper3 import agenda_sponsorship_opportunity as opportunity
from paper3 import direct_ratification as base


SEED_BASE = 1360000
ORDER_SEED = 2026100800
PROFILE_SPECS = (
    ("split", "y_high", "flexible_first", 2026100500),
    ("split", "y_high", "flexible_first", 2026100501),
    ("split", "y_high", "flexible_last", 2026100502),
    ("split", "y_high", "flexible_last", 2026100503),
    ("split", "c_high", "flexible_first", 2026100504),
    ("split", "c_high", "flexible_first", 2026100505),
    ("split", "c_high", "flexible_last", 2026100506),
    ("split", "c_high", "flexible_last", 2026100507),
    ("aligned_y", "c_high", "flexible_first", 2026100508),
    ("aligned_y", "c_high", "flexible_last", 2026100509),
    ("aligned_c", "y_high", "flexible_first", 2026100510),
    ("aligned_c", "y_high", "flexible_last", 2026100511),
)


def profiles():
    result = []
    for index, (structure, welfare, order, seed) in enumerate(PROFILE_SPECS):
        roles = tuple((index + actor) % 7 for actor in range(7))
        labels = tuple(base.POLICIES[(index + offset) % 3]
                       for offset in range(3))
        item = opportunity.draw(structure, welfare, seed,
                                role_permutation=roles,
                                label_permutation=labels)
        result.append(opportunity.with_order(item, order, seed + 307))
    if len(result) != 12 or len({row["profile"]["id"] for row in result}) != 12:
        raise ValueError("common-transcript profile inventory")
    return result


def assignments():
    rows = [dict(profile_id=item["profile"]["id"],
                 structure=item["structure"], welfare=item["welfare"],
                 order_stratum=item["order_stratum"])
            for item in profiles()]
    random.Random(ORDER_SEED).shuffle(rows)
    result = [dict(id=f"common-advocacy-{index:02d}",
                   seed_base=SEED_BASE + 64 * index,
                   arm_order=(list(game.ARMS) if index % 2 == 0
                              else list(reversed(game.ARMS))),
                   intended_calls=33, **row)
              for index, row in enumerate(rows)]
    seeds = [assignment["seed_base"] + offset for assignment in result
             for offset in range(33)]
    if len(result) != 12 or len(seeds) != 396 or len(set(seeds)) != 396:
        raise ValueError("common-transcript request inventory")
    return result


def screen(outcomes):
    """outcomes maps (profile_id, arm) to complete outcome or None.

    Missing split pairs are counted against both possible lead directions,
    never turned into favorable signs. A policy must change through the
    sponsorship-selected floor and change citizen welfare by at least 18.
    """
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
        welfare_delta = (public["enacted_total_citizen_utility"] -
                         sealed["enacted_total_citizen_utility"]
                         if complete else None)
        floor_changed = (public["floor_policy"] != sealed["floor_policy"]
                         if complete else None)
        enacted_changed = (public["enacted_policy"] != sealed["enacted_policy"]
                           if complete else None)
        benefit = (floor_changed and welfare_delta >= 18) if complete else None
        harm = (floor_changed and welfare_delta <= -18) if complete else None
        rows.append(dict(profile_id=pid, structure=item["structure"],
                         welfare=item["welfare"],
                         order_stratum=item["order_stratum"],
                         paired_complete=complete, welfare_delta=welfare_delta,
                         harmed_citizen_delta=(public["harmed_citizen_count"] -
                                               sealed["harmed_citizen_count"]
                                               if complete else None),
                         district_utility_delta=({district:
                             public["enacted_district_utility"][district] -
                             sealed["enacted_district_utility"][district]
                             for district in sealed["enacted_district_utility"]}
                             if complete else None),
                         floor_changed=floor_changed,
                         enacted_changed=enacted_changed,
                         public_benefit=benefit, public_harm=harm,
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
    negative_welfare = sum(row["paired_complete"] and
                           row["welfare_delta"] < 0 for row in split)
    positive_welfare = sum(row["paired_complete"] and
                           row["welfare_delta"] > 0 for row in split)
    stable_controls = sum(row["control_stable"] is True for row in controls)
    eligible = stable_controls >= 3
    beneficial_lead = (eligible and benefit >= 6 and
                       negative_welfare + missing <= 1)
    harmful_lead = (eligible and harm >= 6 and
                    positive_welfare + missing <= 1)
    if beneficial_lead:
        classification = "selected_case_public_benefit_lead"
    elif harmful_lead:
        classification = "selected_case_public_harm_lead"
    elif missing > 1 or stable_controls < 3:
        classification = "incomplete_or_control_failed"
    else:
        classification = "no_prespecified_constituent_lead"
    return dict(rows=rows, split_pairs_complete=8 - missing,
                stable_control_pairs=stable_controls,
                public_benefit_pairs=benefit, public_harm_pairs=harm,
                negative_welfare_pairs=negative_welfare,
                positive_welfare_pairs=positive_welfare,
                missing_split_pairs=missing,
                beneficial_lead=beneficial_lead, harmful_lead=harmful_lead,
                classification=classification,
                caveat="Twelve opportunity-conditioned selected profiles on one model; sign and floor-change triage is not a population estimate or paper result. Every missing assignment and person-level loss must remain visible.")
