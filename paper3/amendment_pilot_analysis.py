"""Prespecified, finite selected-case amendment pilot readout.

The denominator is the assigned four profile/seed blocks per stratum, not
calls, citizens, or only complete episodes. Incomplete blocks cannot silently
be excluded. No causal population or equilibrium inference is made here.
"""
from __future__ import annotations

from paper3 import amendment_institution as institution
from paper3 import amendment_pilot_design as design


def readout(records):
    """Records are keyed by assignment ID and include every assigned episode."""
    scheduled = design.assignments()
    if set(records) != {row["id"] for row in scheduled}:
        raise ValueError("all assignment IDs required")
    grouped = {}
    for row in scheduled:
        saved = records[row["id"]]
        if saved["status"] not in ("completed", "failed", "not_started", "instrument_error"):
            raise ValueError("unknown episode status")
        key = (row["stratum"], row["game_id"], row["seed_block"])
        group = grouped.setdefault(key, {})
        group[row["arm"]] = dict(assignment=row["id"], status=saved["status"],
                                 outcome=saved.get("outcome") if saved["status"] == "completed"
                                 else None)
    pairs = []
    for (stratum, game_id, block), arms in sorted(grouped.items()):
        if set(arms) != set(institution.ARMS):
            raise ValueError("incomplete arm schedule")
        complete = all(arms[arm]["status"] == "completed" for arm in institution.ARMS)
        actions = None
        if complete:
            closed = arms["closed_agenda"]["outcome"]
            opened = arms["open_amendment"]["outcome"]
            veto = arms["citizen_veto"]["outcome"]
            actions = dict(
                closed_amendment=closed["amendment_policy"],
                open_amendment=opened["amendment_policy"],
                closed_final=closed["final_policy"],
                open_final=opened["final_policy"],
                veto_final=veto["final_policy"],
                open_amendment_yes=sum(opened["amendment_ballots"]),
                enacted_by_arm={arm: arms[arm]["outcome"]["enacted_policy"]
                                for arm in institution.ARMS},
                # Seven separate principal outcomes, not a flattened mean.
                district_utility_by_arm={arm: arms[arm]["outcome"]["enacted_district_utility"]
                                         for arm in institution.ARMS},
                district_regret_by_arm={arm: arms[arm]["outcome"]["unconstrained_menu_regret"]
                                        for arm in institution.ARMS},
                citizen_utility_by_arm={arm: arms[arm]["outcome"]["enacted_citizen_utility"]
                                        for arm in institution.ARMS},
            )
        representative = next(row for row in scheduled if row["stratum"] == stratum
                              and row["game_id"] == game_id
                              and row["seed_block"] == block)
        amendment_pair_known = (arms["closed_agenda"]["outcome"] is not None and
                                arms["open_amendment"]["outcome"] is not None)
        amendment_switch = (arms["open_amendment"]["outcome"]["amendment_policy"] == "C"
                            and arms["closed_agenda"]["outcome"]["amendment_policy"] != "C"
                            if amendment_pair_known else None)
        pairs.append(dict(stratum=stratum, game_id=game_id, seed_block=block,
                          favorite=representative["favorite"],
                          outsider_ideal=representative["outsider_ideal"],
                          complete=complete, arms=arms, actions=actions,
                          amendment_pair_known=amendment_pair_known,
                          amendment_switch=amendment_switch))
    bounds = {}
    for stratum in ("mandate_aligned", "mandate_divergent"):
        stratum_rows = [row for row in pairs if row["stratum"] == stratum]
        known = sum(row["amendment_pair_known"] for row in stratum_rows)
        success = sum(row["amendment_switch"] is True for row in stratum_rows)
        bounds[stratum] = dict(assigned=4, paired_observed=known, observed_switches=success,
                               switch_rate_lower=success / 4,
                               switch_rate_upper=(success + 4 - known) / 4)
    return dict(assignments=[dict(**row, status=records[row["id"]]["status"])
                             for row in scheduled],
                complete_episodes=sum(records[row["id"]]["status"] == "completed"
                                      for row in scheduled),
                complete_blocks=sum(row["complete"] for row in pairs),
                blocks=pairs,
                missingness_bounds=dict(open_closed_switch_by_stratum=bounds,
                                        failed_episode_district_utility=[-90, 90],
                                        failed_episode_total_citizen_utility=[-630, 630],
                                        failed_episode_enacted_policy_set=["X", "Y", "C", "q"]),
                triage=triage(pairs))


def triage(pairs):
    if len(pairs) != 8:
        raise ValueError("eight fixed blocks required")
    missing = [dict(stratum=row["stratum"], game_id=row["game_id"],
                    seed_block=row["seed_block"])
               for row in pairs if not row["complete"]]
    if missing:
        return dict(classification="not_identified_incomplete", missing_blocks=missing,
                    action_lead=False)
    aligned = [row for row in pairs if row["stratum"] == "mandate_aligned"]
    divergent = [row for row in pairs if row["stratum"] == "mandate_divergent"]
    if len(aligned) != 4 or len(divergent) != 4:
        raise ValueError("stratum block counts")
    # The only lead is an *agent-chosen* switch to viable C under open rights,
    # plus actual contingent support. Enactment by priority alone never passes.
    aligned_switch = sum(row["actions"]["open_amendment"] == "C"
                         and row["actions"]["closed_amendment"] != "C"
                         for row in aligned)
    aligned_supported = sum(row["actions"]["open_amendment"] == "C"
                            and row["actions"]["open_amendment_yes"] >= 4
                            for row in aligned)
    divergent_switch = sum(row["actions"]["open_amendment"] == "C"
                           and row["actions"]["closed_amendment"] != "C"
                           for row in divergent)
    closed_favorite = sum(row["actions"]["closed_final"] == row["favorite"]
                          for row in pairs)
    action_lead = (aligned_switch >= 3 and aligned_supported >= 3
                   and divergent_switch <= 1 and closed_favorite >= 6)
    return dict(classification="selected_action_lead" if action_lead else
                "no_prespecified_action_lead", missing_blocks=[],
                action_lead=action_lead,
                aligned_switch=aligned_switch,
                aligned_supported=aligned_supported,
                divergent_switch=divergent_switch,
                closed_noncompromise_final=closed_favorite,
                caveat="Four selected profiles and two request-seed blocks; not population evidence.")
