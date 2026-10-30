"""Post-discovery spending triage for the frozen Qwen repeatability readout.

This module is deliberately outside the 212-file frozen source closure. Its
criterion was stated in Obsidian after two invalid opening actions and before
any repeatability episode completed. It is not a preregistered hypothesis test,
an institutional effect estimate, or a repair of failed cells.
"""
from __future__ import annotations

from paper3.constituent_b_repeatability_analysis import EXCHANGE_FAMILIES


PAIR = ("member_enforcement", "universal_clearance")
PAIR_KEY = "__".join(PAIR)


def evaluate(readout):
    """Return True/False/None for further-investment triage only.

    None denotes insufficient coverage; False means the demanding exploratory
    continuation criterion did not hold. Neither is a scientific null.
    """
    summary = readout["repeatability"]
    families = summary["exchange_families"]
    if set(families) != set(EXCHANGE_FAMILIES):
        raise ValueError("repeatability family inventory changed")
    profiles = {row["profile_id"]: row for row in readout["profiles"]}
    if len(profiles) != 7:
        raise ValueError("repeatability profile inventory changed")
    control = summary["aligned_control"]
    if len(control) != 1 or control[0]["profile_id"] not in profiles:
        raise ValueError("aligned control inventory changed")
    control_arms = control[0]["arms"]
    control_complete = all(value["status"] == "completed"
                           for value in control_arms.values())
    control_same_policy = (len({value["enacted_policy"] for value in
                                control_arms.values()}) == 1
                           if control_complete else None)
    details = {}
    signs = set()
    enough_coverage = control_complete
    for family in EXCHANGE_FAMILIES:
        item = families[family]
        rows = item["cells"]
        if [row["block"] for row in rows] != [0, 1, 2] or any(
                row["profile_id"] not in profiles for row in rows):
            raise ValueError("repeatability block inventory changed")
        matched = item["between_arms"][PAIR_KEY]
        if [row["block"] for row in matched] != [0, 1, 2]:
            raise ValueError("matched block order changed")
        complete = [row for row in matched if row["completed"]]
        if len(complete) < 2:
            enough_coverage = False
        pre_vote_leads = []
        for pair in complete:
            block = pair["block"]
            cell = rows[block]
            source = profiles[cell["profile_id"]]
            comparison = [row for row in source["pairwise"]
                          if row["arms"] == list(PAIR)]
            if len(comparison) != 1 or not comparison[0]["completed"]:
                raise ValueError("matched citizen comparison missing")
            comparison = comparison[0]
            overall = comparison["citizen_comparison"]["overall"]
            citizens_changed = overall["citizens_better"] > 0 or overall["citizens_worse"] > 0
            arms = cell["arms"]
            unforced_request_shift = (
                comparison["ballot_projects_match"] and
                comparison["requested_ballot_patterns_differ"] and
                all(arms[arm]["enforcement_changes"] == 0 for arm in PAIR))
            lead = citizens_changed and (pair["final_policy_changed"] or
                                         unforced_request_shift)
            pre_vote_leads.append(dict(block=block, lead=lead,
                                       final_policy_changed=pair["final_policy_changed"],
                                       unforced_request_shift=unforced_request_shift,
                                       citizens_changed=citizens_changed))
            delta = pair["total_citizen_utility_change"]
            if delta:
                signs.add(1 if delta > 0 else -1)
        within = [abs(row["total_citizen_utility_change"])
                  for arm in PAIR for row in item["within_arm"][arm]
                  if row["completed"]]
        max_within = max(within, default=None)
        min_between = min((abs(row["total_citizen_utility_change"])
                           for row in complete), default=None)
        details[family] = dict(completed_matched_blocks=[row["block"] for row in complete],
                               missing_matched_blocks=[row["block"] for row in matched
                                                       if not row["completed"]],
                               total_citizen_utility_deltas=[
                                   row["total_citizen_utility_change"] for row in complete],
                               pre_vote_leads=pre_vote_leads,
                               minimum_absolute_between=min_between,
                               maximum_absolute_within=max_within,
                               stronger_than_within=(min_between > max_within
                                                     if min_between is not None and
                                                     max_within is not None else None))
    if not enough_coverage:
        value = None
    else:
        all_deltas = [delta for family in EXCHANGE_FAMILIES
                      for delta in details[family]["total_citizen_utility_deltas"]]
        value = bool(control_same_policy and len(signs) == 1 and
                     all(delta != 0 for delta in all_deltas) and
                     all(details[family]["stronger_than_within"] and
                         all(row["lead"] for row in details[family]["pre_vote_leads"])
                         for family in EXCHANGE_FAMILIES))
    return dict(triage=value, coverage_sufficient=enough_coverage,
                aligned_control_complete=control_complete,
                aligned_control_same_policy=control_same_policy,
                welfare_signs=sorted(signs), families=details,
                caveat="After-discovery spending triage, written after two invalid openings and before any completed repeatability episode. True is not publication evidence; False is not a scientific null; None means missing coverage. All frozen feasibility failures and person-level bounds remain authoritative.")
