"""Prospective, unfrozen selected-case sponsorship discovery schedule.

Six independently drawn opportunity-conditioned profiles × two visibility
procedures. This is a mechanism-discovery pilot design, not a confirmatory
population test, active allocation, or permission to send model requests.
"""
from __future__ import annotations

import random

from paper3 import agenda_sponsorship_institution as institution
from paper3 import agenda_sponsorship_opportunity as opportunity
from paper3 import direct_ratification as base


CALLS_PER_EPISODE = 20
SEED_BASE = 1260000
ORDER_SEED = 2026100217
PROFILE_SPECS = (
    ("split", "y_high", "flexible_first", 2026100200),
    ("split", "y_high", "flexible_last", 2026100201),
    ("split", "c_high", "flexible_first", 2026100202),
    ("split", "c_high", "flexible_last", 2026100203),
    ("aligned_y", "c_high", "flexible_last", 2026100204),
    ("aligned_c", "y_high", "flexible_first", 2026100205),
)


def profiles():
    rows = []
    for index, (structure, welfare, order_stratum, seed) in enumerate(PROFILE_SPECS):
        roles = tuple((index + offset) % 7 for offset in range(7))
        labels = tuple(base.POLICIES[(index + offset) % 3]
                       for offset in range(3))
        item = opportunity.draw(structure, welfare, seed,
                                role_permutation=roles,
                                label_permutation=labels)
        rows.append(opportunity.with_order(item, order_stratum, seed + 307))
    if len({row["profile"]["id"] for row in rows}) != len(rows):
        raise ValueError("duplicate discovery profile")
    return rows


def assignments():
    rows = [dict(profile_id=item["profile"]["id"],
                 structure=item["structure"], welfare=item["welfare"],
                 order_stratum=item["order_stratum"], arm=arm,
                 intended_calls=CALLS_PER_EPISODE)
            for item in profiles() for arm in institution.ARMS]
    random.Random(ORDER_SEED).shuffle(rows)
    scheduled = [dict(id=f"sponsorship-pilot-{index:02d}",
                      seed_base=SEED_BASE + 32 * index, **row)
                 for index, row in enumerate(rows)]
    seeds = [assignment["seed_base"] + i for assignment in scheduled
             for i in range(CALLS_PER_EPISODE)]
    if len(scheduled) != 12 or len(set(seeds)) != 240:
        raise ValueError("discovery assignment inventory")
    return scheduled


def _qualification(outcome, compromises):
    if outcome is None:
        return None
    if not isinstance(outcome, dict) or "qualified_motion" not in outcome:
        raise ValueError("invalid episode outcome")
    value = outcome["qualified_motion"]
    if (type(value) is not list or len(value) > 1 or
            (value and value[0] not in compromises)):
        raise ValueError("invalid qualified motion")
    return bool(value)


def screen(outcomes):
    """Selected-case triage; missing pairs never become favorable results."""
    if type(outcomes) is not dict:
        raise ValueError("outcome map")
    profiles_by_id = {item["profile"]["id"]: item for item in profiles()}
    if not set(outcomes) <= {(pid, arm) for pid in profiles_by_id
                             for arm in institution.ARMS}:
        raise ValueError("unknown outcome assignment")
    rows = []
    for pid, item in profiles_by_id.items():
        sealed = _qualification(outcomes.get((pid, "sealed")),
                                item["compromises"])
        public = _qualification(outcomes.get((pid, "public_sequential")),
                                item["compromises"])
        rows.append(dict(profile_id=pid, structure=item["structure"],
                         welfare=item["welfare"],
                         order_stratum=item["order_stratum"],
                         sealed_qualified=sealed,
                         public_qualified=public,
                         paired_complete=sealed is not None and public is not None,
                         public_only=(public is True and sealed is False)
                         if sealed is not None and public is not None else None,
                         sealed_only=(sealed is True and public is False)
                         if sealed is not None and public is not None else None))
    late = [row for row in rows if row["structure"] == "split" and
            row["order_stratum"] == "flexible_last"]
    early = [row for row in rows if row["structure"] == "split" and
             row["order_stratum"] == "flexible_first"]
    controls = [row for row in rows if row["structure"] != "split"]
    complete_split = all(row["paired_complete"] for row in late + early)
    adequate_controls = sum(row["paired_complete"] and
                            row["sealed_qualified"] and
                            row["public_qualified"] for row in controls) >= 1
    no_reverse = all(row["sealed_only"] is False for row in late + early)
    order_sensitive = (complete_split and adequate_controls and no_reverse and
                       all(row["public_only"] is True for row in late) and
                       all(row["public_only"] is False for row in early))
    general = (complete_split and adequate_controls and no_reverse and
               all(row["public_only"] is True for row in late + early))
    if order_sensitive:
        classification = "selected_case_order_sensitive_lead"
    elif general:
        classification = "selected_case_general_sequential_lead"
    elif not complete_split or not adequate_controls:
        classification = "incomplete_or_control_failed"
    else:
        classification = "no_prespecified_action_lead"
    return dict(rows=rows, complete_split_pairs=sum(row["paired_complete"]
                                                     for row in late + early),
                complete_control_pairs=sum(row["paired_complete"]
                                           for row in controls),
                order_sensitive_lead=order_sensitive,
                general_sequential_lead=general,
                classification=classification,
                caveat="Six opportunity-conditioned profile draws on one model are mechanism triage, not a population or publication result. Outcomes and all missing assignments must remain visible.")
