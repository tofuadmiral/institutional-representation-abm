"""Prospective descriptive screen for the unrun election candidate.

This screen is for mechanism discovery on four selected synthetic profiles.
It is not a population estimator, a significance test, or publication proof.
"""
from __future__ import annotations

from paper3 import electoral_accountability as game
from paper3 import electoral_accountability_design as design


def _finite_bounds(profile, focal):
    policy_total = sum(c["p"] for citizens in profile["districts"].values()
                       for c in citizens)
    focal_total = sum(c["p"] for c in profile["districts"][f"r{focal}"])
    bonus = profile["office_bonus"]
    return dict(total_citizen_utility=[min(0, policy_total), max(0, policy_total)],
                focal_policy_utility=[min(0, focal_total), max(0, focal_total)],
                focal_representative_payoff=[min(0, focal_total),
                                             max(0, focal_total) + bonus],
                replacements=[0, 7])


def readout(records):
    """Read all predeclared cells; never drop a missing/failed episode."""
    expected = {(row["profile_id"], row["arm"])
                for row in design.candidate_assignments()}
    if set(records) != expected:
        raise ValueError("all sixteen candidate cells required")
    rows = []
    for item in design.inventory():
        profile_id, focal = item["id"], item["focal"]
        cells = {}
        for arm in game.ARMS:
            saved = records[(profile_id, arm)]
            status = saved["status"]
            if status == "completed":
                events, outcome = saved["events"], saved["outcome"]
                early_consents = events[0]["consents"]
                consent = events[1]["consents"][focal]
                request = outcome["requested_ballots"][focal]
                executed = outcome["executed_ballots"][focal]
                cells[arm] = dict(status=status,
                    focal_consent=consent, focal_requested_yes=request,
                    focal_executed_yes=executed,
                    early_consents=early_consents,
                    early_signer_count=sum(early_consents.values()),
                    focal_pivotal_in_contract=sum(early_consents.values()) == 3,
                    focal_action=("consent_request_no" if consent and not request
                                  else "refuse_request_no" if not consent and not request
                                  else "request_yes"),
                    focal_retained=outcome["retained"][f"r{focal}"],
                    focal_policy_utility=outcome["district_outcomes"][f"r{focal}"],
                    focal_representative_payoff=outcome["representative_payoffs"][f"r{focal}"],
                    contract_active=outcome["contract_active"],
                    controller_changed_ballots=outcome["controller_changed_ballots"],
                    enacted_policy=outcome["enacted_policy"],
                    total_citizen_utility=outcome["total_citizen_utility"],
                    harmed_citizens=sum(value < 0 for value in
                                        outcome["citizen_outcomes"].values()),
                    replacements=outcome["replacements"],
                    outcome=outcome, events=events)
            else:
                cells[arm] = dict(status=status, error=saved.get("error"),
                    finite_missingness_bounds=_finite_bounds(item["profile"], focal),
                    prefix=saved.get("prefix"))
        rows.append(dict(profile_id=profile_id, focal=focal,
                         focal_sum=item["focal_sum"],
                         focal_approval=item["focal_approval"],
                         office_bonus=item["office_bonus"], cells=cells))
    return dict(profiles=rows, assignments=len(records),
                completed_episodes=sum(saved["status"] == "completed"
                                       for saved in records.values()),
                caveat="Two theory-constructed conflict profiles and two controls; "
                       "63 synthetic deterministic citizen ballots per complete episode. "
                       "No population prevalence, human-voter, or second-model inference.")


def discovery_screen(report):
    rows = report["profiles"]
    if len(rows) != 4:
        raise ValueError("four selected profiles required")
    coverage = report["assignments"] == 16 and report["completed_episodes"] == 16
    conflicts = rows[:2]
    contrasts = []
    for row in conflicts:
        requested = row["cells"]["binding_requested_record"]
        executed = row["cells"]["binding_executed_record"]
        matched = (requested["status"] == executed["status"] == "completed" and
                   requested["early_consents"] == executed["early_consents"] and
                   requested["early_signer_count"] ==
                   executed["early_signer_count"] == 3)
        contrasts.append(dict(profile_id=row["profile_id"],
            matched_pivotal_opportunity=matched,
            before_enforcement_divergence=(
                matched and
                (requested["focal_consent"], requested["focal_requested_yes"]) !=
                (executed["focal_consent"], executed["focal_requested_yes"])),
            predicted_choice_pattern=(
                matched and
                requested["focal_action"] == "consent_request_no" and
                executed["focal_action"] == "refuse_request_no"),
            full_pathway=(
                matched and
                requested["focal_action"] == "consent_request_no" and
                requested["contract_active"] and
                requested["focal_executed_yes"] and
                requested["enacted_policy"] == "P" and
                requested["focal_retained"] and
                executed["focal_action"] == "refuse_request_no" and
                executed["enacted_policy"] == "q" and
                executed["focal_retained"])))
    aligned, no_office = rows[2:]
    controls = dict(aligned_both_enact_p=all(
        aligned["cells"][arm]["status"] == "completed" and
        aligned["cells"][arm]["enacted_policy"] == "P"
        for arm in ("binding_requested_record", "binding_executed_record")),
        no_office_both_enact_p=all(
        no_office["cells"][arm]["status"] == "completed" and
        no_office["cells"][arm]["enacted_policy"] == "P"
        for arm in ("binding_requested_record", "binding_executed_record")),
        promise_focal_choice_invariant=all(
            row["cells"]["promise_requested_record"]["status"] == "completed" and
            row["cells"]["promise_executed_record"]["status"] == "completed" and
            (row["cells"]["promise_requested_record"]["focal_consent"],
             row["cells"]["promise_requested_record"]["focal_requested_yes"]) ==
            (row["cells"]["promise_executed_record"]["focal_consent"],
             row["cells"]["promise_executed_record"]["focal_requested_yes"])
            for row in conflicts),
        all_promise_arms_unforced=all(
        row["cells"][arm]["status"] == "completed" and
        row["cells"][arm]["controller_changed_ballots"] == 0
        for row in rows for arm in ("promise_requested_record",
                                "promise_executed_record")))
    if not coverage:
        pathway = "incomplete_not_classified"
    elif not all(row["matched_pivotal_opportunity"] for row in contrasts):
        pathway = "coalition_opportunity_not_matched"
    elif not all(controls.values()):
        pathway = "ambiguous_controls"
    elif all(row["full_pathway"] for row in contrasts):
        pathway = "selected_case_mechanism_lead"
    elif all(row["before_enforcement_divergence"] for row in contrasts):
        pathway = "choice_divergence_without_full_pathway"
    else:
        pathway = "no_repeated_choice_divergence"
    return dict(coverage=coverage, conflicts=contrasts, controls=controls,
                pathway=pathway,
                caveat="Only pre-enforcement consent/requested-vote divergence on "
                       "matched three-signature early coalitions can support "
                       "an attribution mechanism lead. Unmatched early coalitions "
                       "are ambiguous. Controller-changed ballots, "
                       "enactment and election tallies are separately reported. "
                       "A positive selected-case screen requires untouched games "
                       "and another model before a paper claim. The nonbinding "
                       "record-label comparison is a falsification control: "
                       "different focal choices there make an attribution-only "
                       "reading ambiguous.")
