"""Prospective descriptive screen for the frozen constituent B discovery.

This is NOT a population estimate or a publication test. A discovery lead
requires pre-enforcement behavior with citizen consequences under the same
institutional contrast in both exchange families. Draft-only differences,
controller-forced ballots and technically incomplete allocations cannot pass.
The screen was defined before any same-profile institutional pair completed.
"""
from __future__ import annotations

from paper3 import coalition_contracts as game
from paper3 import constituent_contract_bridge as bridge
from analysis import paper3_constituent_b_prevote as prevote


CONTRASTS = (("public_promise", "member_enforcement"),
             ("member_enforcement", "universal_clearance"))
EXCHANGE_FAMILIES = ("exchange_majority_conflict_outsider_harm",
                     "exchange_majority_aligned_outsider_harm")


def _event(events, event_type):
    found = [row for row in events if row["type"] == event_type]
    if len(found) != 1:
        raise ValueError("expected exactly one " + event_type)
    return found[0]


def _terms(action):
    return (action["projects"]["A"], action["projects"]["B"],
            action["first"], tuple(sorted(action["coalition"])))


def _would_activate(arm, coalition, approvals):
    if arm not in game.ARMS or len(approvals) != 7:
        raise ValueError("invalid contract counterfactual")
    active = bool(coalition) and all(approvals[actor] for actor in coalition)
    return active and (arm != "universal_clearance" or all(approvals))


def episode(prepared, arm, saved):
    """Keep incomplete status; verify every completed episode independently."""
    status = saved["status"]
    if status not in ("completed", "failed", "not_started", "instrument_error"):
        raise ValueError("unknown episode status")
    if status != "completed":
        return dict(status=status, error=saved.get("error"))
    events = saved["events"]
    outcome = game.readout(prepared["contract_profile"], arm, events)
    citizens = bridge.evaluate_passed(prepared, outcome["passed"])
    if saved["outcome"] != outcome or saved["citizen_outcome"] != citizens or saved["calls"] != 30:
        raise ValueError("completed episode differs from saved outcome")
    draft = _event(events, "draft")["action"]
    final = _event(events, "final")["action"]
    consent = _event(events, "consent")["approvals"]
    votes = [_event(events, stage) for stage in ("first_vote", "second_vote")]
    return dict(status=status, arm=arm, draft_action=draft, final_action=final,
                draft_proposal=prevote.score_offer(prepared, draft),
                final_proposal=prevote.score_offer(prepared, final),
                consent=consent, votes=votes, outcome=outcome,
                citizen_outcome=citizens)


def contrast(prepared, left, right):
    """Compare two completed arms of one fixed constituent profile."""
    if left["status"] != "completed" or right["status"] != "completed":
        return dict(completed=False, left_status=left["status"],
                    right_status=right["status"], discovery_lead=False)
    draft = prevote.compare_offers(prepared, left["draft_action"], right["draft_action"])
    final = prevote.compare_offers(prepared, left["final_action"], right["final_action"])
    same_final_terms = _terms(left["final_action"]) == _terms(right["final_action"])
    consent_changed_same_terms = same_final_terms and left["consent"] != right["consent"]
    coalition = left["final_action"]["coalition"]
    consent_pivotal_under_fixed_rule = consent_changed_same_terms and any(
        _would_activate(arm, coalition, left["consent"]) !=
        _would_activate(arm, coalition, right["consent"])
        for arm in (left["arm"], right["arm"]))
    same_vote_projects = [x["project"] for x in left["votes"]] == [
        x["project"] for x in right["votes"]]
    requested_changed_same_projects = same_vote_projects and any(
        a["requested"] != b["requested"]
        for a, b in zip(left["votes"], right["votes"], strict=True))
    enacted = bridge.compare_passed(prepared, left["outcome"]["passed"],
                                    right["outcome"]["passed"])
    enacted_citizens_changed = (enacted["overall"]["citizens_better"] > 0 or
                                enacted["overall"]["citizens_worse"] > 0)
    final_citizens_changed = (final["citizens_gain"] > 0 or final["citizens_lose"] > 0)
    no_forced_ballots = (left["outcome"]["enforcement_changes"] == 0 and
                         right["outcome"]["enforcement_changes"] == 0)
    # A different coalition/order alone is behavior, but cannot pass the
    # citizen-consequence screen if it merely changes controller enforcement.
    lead = ((final["full_delivery_policy_changed"] and final_citizens_changed) or
            (consent_pivotal_under_fixed_rule and enacted_citizens_changed) or
            (requested_changed_same_projects and no_forced_ballots and
             enacted_citizens_changed))
    return dict(completed=True, draft=draft, final=final,
                same_final_terms=same_final_terms,
                consent_changed_same_terms=consent_changed_same_terms,
                consent_pivotal_under_fixed_rule=consent_pivotal_under_fixed_rule,
                same_vote_projects=same_vote_projects,
                requested_changed_same_projects=requested_changed_same_projects,
                no_forced_ballots=no_forced_ballots,
                left_enforcement_changes=left["outcome"]["enforcement_changes"],
                right_enforcement_changes=right["outcome"]["enforcement_changes"],
                enacted_citizen_comparison=enacted, discovery_lead=lead)


def report(profile_rows, assignments, saved_by_id):
    """Retain all 21 cells; evaluate only complete profile-matched contrasts."""
    prepared = {row["prepared"]["contract_profile"]["id"]: row
                for row in profile_rows}
    if (len(prepared) != 7 or len(assignments) != 21 or len(saved_by_id) != 21 or
            {row["id"] for row in assignments} != set(saved_by_id)):
        raise ValueError("full seven-profile by three-arm inventory required")
    cells = {}
    for assignment in assignments:
        key = (assignment["profile_id"], assignment["arm"])
        if (key in cells or assignment["profile_id"] not in prepared or
                assignment["arm"] not in game.ARMS or assignment["id"] not in saved_by_id):
            raise ValueError("assignment inventory mismatch")
        cells[key] = episode(prepared[assignment["profile_id"]]["prepared"],
                             assignment["arm"], saved_by_id[assignment["id"]])
    if len(cells) != 21 or any((profile_id, arm) not in cells
                               for profile_id in prepared for arm in game.ARMS):
        raise ValueError("profile-arm cross incomplete")
    rows = []
    for profile_id, row in prepared.items():
        arms = {arm: cells[(profile_id, arm)] for arm in game.ARMS}
        comparisons = {f"{a}__{b}": contrast(row["prepared"], arms[a], arms[b])
                       for a, b in CONTRASTS}
        rows.append(dict(profile_id=profile_id, family=row["family"],
                         arms=arms, contrasts=comparisons))
    all_complete = all(cell["status"] == "completed" for cell in cells.values())
    by_contrast = {}
    for a, b in CONTRASTS:
        name = f"{a}__{b}"
        by_contrast[name] = {
            family: [row["profile_id"] for row in rows
                     if row["family"] == family and
                     row["contrasts"][name]["discovery_lead"]]
            for family in EXCHANGE_FAMILIES}
    candidate = (any(all(by_contrast[name][family] for family in EXCHANGE_FAMILIES)
                     for name in by_contrast) if all_complete else None)
    return dict(assigned_episodes=21,
                complete_episodes=sum(cell["status"] == "completed"
                                      for cell in cells.values()),
                feasibility_complete=all_complete,
                candidate_screen=candidate,
                signal_profiles_by_same_contrast=by_contrast,
                profiles=rows,
                caveat="Discovery screen on seven constructed profiles. A true value is a lead to validate, not a causal population or paper result. None means technically incomplete, not a scientific null.")
