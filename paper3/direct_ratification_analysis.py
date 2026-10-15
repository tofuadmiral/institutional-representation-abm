"""Finite person-level readout for the prospective ratification discovery pilot."""
from __future__ import annotations

from paper3 import direct_ratification as game


def bounds(profile):
    """Exact finite-policy bounds for missing proposals/outcomes, not imputations."""
    game.validate(profile)
    possibilities = ["q", *game.POLICIES]
    citizen_rows = {citizen["id"]: citizen["utility"]
                    for district in profile["districts"].values()
                    for citizen in district}
    citizen = {cid: dict(min_utility=min([0, *row.values()]),
                         max_utility=max([0, *row.values()]))
               for cid, row in citizen_rows.items()}
    district = {district_id: dict(
        min_utility=min([0, *[sum(c["utility"][p] for c in citizens)
                              for p in game.POLICIES]]),
        max_utility=max([0, *[sum(c["utility"][p] for c in citizens)
                              for p in game.POLICIES]]))
        for district_id, citizens in profile["districts"].items()}
    total = [0] + [sum(c["utility"][p]
                       for citizens in profile["districts"].values()
                       for c in citizens)
                   for p in game.POLICIES]
    return dict(possible_policies=possibilities, citizens=citizen,
                districts=district,
                total_citizen_utility=dict(min=min(total), max=max(total)))


def readout(profile_rows, records):
    """Keep all assigned arms, outcomes, failed prefixes and finite bounds."""
    profiles = {row["profile"]["id"]: row for row in profile_rows}
    output = []
    for profile_id, item in profiles.items():
        profile = item["profile"]
        finite = bounds(profile)
        arms = {}
        for arm in game.ARMS:
            saved = records[(profile_id, arm)]
            status = saved["status"]
            if status == "completed":
                arms[arm] = dict(status=status, outcome=saved["outcome"],
                                 events=saved["events"], calls=saved["calls"])
            else:
                arms[arm] = dict(status=status, error=saved.get("error"),
                                 finite_missingness_bounds=finite)
        left, right = (arms[arm] for arm in game.ARMS)
        if left["status"] == right["status"] == "completed":
            l, r = left["outcome"], right["outcome"]
            contrast = dict(completed=True,
                            final_policy_changed=l["final_policy"] != r["final_policy"],
                            advisory_final_policy=l["final_policy"],
                            binding_final_policy=r["final_policy"],
                            advisory_final_policy_ratifiable=l["referendum"]["approved"],
                            binding_final_policy_ratifiable=r["referendum"]["approved"],
                            final_proposal_citizen_utility_change=
                            r["final_proposal_total_citizen_utility"] -
                            l["final_proposal_total_citizen_utility"],
                            enacted_citizen_utility_change=
                            r["enacted_total_citizen_utility"] -
                            l["enacted_total_citizen_utility"],
                            requested_ballots_changed=
                            l["requested_ballots"] != r["requested_ballots"],
                            mechanical_only=(l["final_policy"] == r["final_policy"] and
                                             l["requested_ballots"] == r["requested_ballots"] and
                                             l["enacted_policy"] != r["enacted_policy"]))
        else:
            contrast = dict(completed=False, finite_missingness_bounds=finite)
        output.append(dict(profile_id=profile_id, family=item["family"],
                           block=item["block"], arms=arms, contrast=contrast))
    return dict(profiles=output, assignments=len(records),
                completed_episodes=sum(record["status"] == "completed"
                                       for record in records.values()),
                completed_pairs=sum(row["contrast"]["completed"] for row in output),
                limitation="Four theory-selected cases, two repeated seeds each; outsider-harm role rotations share a table. Calls, representatives and citizens are not independent payoff settings. No causal effect from mechanical veto alone.")


def discovery_triage(readout):
    """Prospective spending screen, not statistical or publication evidence.

    Require all eight matched pairs; every outsider-harm block must shift from
    the agenda holder's own optimum X/Y under advisory polling to C under
    binding ratification, and both controls must retain the same final
    proposal across arms. Enacted-only changes never satisfy this screen.
    """
    rows = readout["profiles"]
    if len(rows) != 8:
        raise ValueError("eight paired profile blocks required")
    coverage = all(row["contrast"]["completed"] for row in rows)
    harm = []
    controls = []
    for row in rows:
        contrast = row["contrast"]
        if row["family"] == "outsider_harm_A_agenda":
            harm.append(bool(contrast["completed"] and
                             contrast["advisory_final_policy"] == "X" and
                             contrast["binding_final_policy"] == "C"))
        elif row["family"] == "outsider_harm_B_agenda":
            harm.append(bool(contrast["completed"] and
                             contrast["advisory_final_policy"] == "Y" and
                             contrast["binding_final_policy"] == "C"))
        else:
            controls.append(bool(contrast["completed"] and
                                 not contrast["final_policy_changed"]))
    if len(harm) != 4 or len(controls) != 4:
        raise ValueError("family inventory")
    return dict(coverage=coverage, harm_role_block_shifts=harm,
                control_block_stability=controls,
                triage=coverage and all(harm) and all(controls),
                caveat="A demanding prewritten spending screen on one conflict payoff table with two agenda types and repeated request-seed blocks. True is not confirmatory evidence; False is not a population null.")
