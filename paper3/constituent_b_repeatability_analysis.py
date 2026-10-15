"""Reuse exact citizen-level scoring and expose all within-table seed blocks."""
from itertools import combinations

from paper3 import coalition_contracts as game
from paper3.constituent_b_gptoss_discovery_analysis import readout as _readout


EXCHANGE_FAMILIES = ("exchange_majority_conflict_outsider_harm",
                     "exchange_majority_aligned_outsider_harm")
CONTRASTS = (("public_promise", "member_enforcement"),
             ("member_enforcement", "universal_clearance"))


def _cell(arm):
    if arm["status"] != "completed":
        return dict(status=arm["status"])
    projects = arm["final_terms"]["projects"]
    outcome = arm["citizen_outcome"]["overall"]
    return dict(status="completed", final_policy=projects["A"] + "+" + projects["B"],
                enacted_policy=arm["citizen_outcome"]["policy_id"],
                total_citizen_utility=outcome["total_relative_utility"],
                citizens_worse=outcome["citizens_worse_than_q"],
                contract_activated=arm["contract_activated"],
                enforcement_changes=arm["enforcement_changes"])


def _compare(left, right):
    if left["status"] != "completed" or right["status"] != "completed":
        return dict(completed=False)
    return dict(completed=True,
                final_policy_changed=left["final_policy"] != right["final_policy"],
                enacted_policy_changed=left["enacted_policy"] != right["enacted_policy"],
                total_citizen_utility_change=(right["total_citizen_utility"] -
                                              left["total_citizen_utility"]),
                citizens_worse_change=right["citizens_worse"] - left["citizens_worse"])


def readout(profiles, records):
    result = _readout(profiles, records)
    metadata = {p["prepared"]["contract_profile"]["id"]: p for p in profiles}
    rows = []
    for profile in result["profiles"]:
        source = metadata[profile["profile_id"]]
        rows.append(dict(profile_id=profile["profile_id"], family=source["family"],
                         block=source["repeatability_block"],
                         arms={arm: _cell(profile["arms"][arm]) for arm in game.ARMS}))
    comparison = {}
    for family in EXCHANGE_FAMILIES:
        family_rows = sorted((row for row in rows if row["family"] == family),
                             key=lambda row: row["block"])
        if [row["block"] for row in family_rows] != [0, 1, 2]:
            raise ValueError("repeatability block inventory changed")
        comparison[family] = dict(
            cells=family_rows,
            within_arm={arm: [dict(blocks=[a["block"], b["block"]],
                                   **_compare(a["arms"][arm], b["arms"][arm]))
                              for a, b in combinations(family_rows, 2)]
                        for arm in game.ARMS},
            between_arms={f"{left}__{right}": [
                dict(block=row["block"],
                     **_compare(row["arms"][left], row["arms"][right]))
                for row in family_rows]
                          for left, right in CONTRASTS})
    controls = [row for row in rows if row["family"] == "aligned_control"]
    if len(controls) != 1 or controls[0]["block"] is not None:
        raise ValueError("aligned repeatability control inventory changed")
    result["repeatability"] = dict(exchange_families=comparison,
                                   aligned_control=controls)
    result["limitation"] = (
        "Two fresh exchange utility structures each repeated at three distinct "
        "request-seed blocks, plus one aligned control. The six exchange profile "
        "IDs are not six independent payoff tables. Calls and citizens within "
        "an episode are not independent; requested seeds may not be honored "
        "deterministically by the provider. This checks within-arm outcome "
        "variability versus matched-arm variation, not population prevalence, "
        "institutional causality or publication readiness. Preserve technical "
        "failures and all person-level missingness bounds."
    )
    return result
