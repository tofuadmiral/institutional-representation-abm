"""No-model feasibility inventory for outsider amendment/veto opportunities.

The ballots below are positive-utility votes against status quo, *not*
equilibrium play: with amendment priority, contingent strategic votes can
depend on the alternative. The inventory must not be called a prediction.
"""
from __future__ import annotations

from paper3 import amendment_institution as institution
from paper3 import direct_ratification as base


def inventory(item):
    institution.validate_item(item)
    totals = base.district_totals(item["profile"])
    policies = base.POLICIES
    sincere = {policy: [totals[f"r{actor}"][policy] > 0
                        for actor in base.ACTORS]
               for policy in policies}
    rows = []
    for amendment in policies:
        for final in policies:
            for arm in institution.ARMS:
                result = institution.enact(item, arm, amendment, final,
                                           sincere[amendment], sincere[final])
                outcome = result["enacted_policy"]
                # Separate conditional comparison: assume the final policy
                # is the certain fallback when casting the amendment ballot.
                # This is a scenario, not a Nash equilibrium or a prediction.
                pairwise_ballots = [totals[f"r{actor}"][amendment] >
                                    totals[f"r{actor}"][final]
                                    for actor in base.ACTORS]
                pairwise = institution.enact(item, arm, amendment, final,
                                              pairwise_ballots, sincere[final])
                rows.append(dict(arm=arm, amendment=amendment, final=final,
                                 enacted=outcome,
                                 conditional_fallback_enacted=pairwise["enacted_policy"],
                                 amendment_over_final_count=sum(pairwise_ballots),
                                 proposer_utility=(0 if outcome == "q" else
                                                   totals[f'r{item["profile"]["proposer"]}'][outcome]),
                                 outsider_utility=(0 if outcome == "q" else
                                                   totals[f'r{item["outsider"]}'][outcome])))
    # Keep the entire tie set; do not pick a desired optimum from it.
    upper_bound = {}
    for arm in institution.ARMS:
        arm_rows = [row for row in rows if row["arm"] == arm]
        value = max(row["proposer_utility"] for row in arm_rows)
        upper_bound[arm] = dict(proposer_utility=value,
                                amendment_final_pairs=[[row["amendment"], row["final"]]
                                                       for row in arm_rows
                                                       if row["proposer_utility"] == value])
    return dict(profile_id=item["profile"]["id"],
                stratum=item["stratum"], favorite=item["favorite"],
                proposer=item["profile"]["proposer"], outsider=item["outsider"],
                district_totals=totals,
                positive_utility_ballots=sincere,
                outsider_citizen_yes_counts={policy: base.poll(item["profile"], policy)
                                             ["yes_counts"][f'r{item["outsider"]}']
                                             for policy in policies},
                rows=rows,
                # This is a joint-action *upper bound*, not the proposer's
                # unilateral optimum: the outsider chooses the amendment.
                set_valued_feasible_proposer_upper_bound=upper_bound)
