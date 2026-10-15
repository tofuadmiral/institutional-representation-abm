"""Supplemental proposal-versus-enactment readout for Qwen repeatability.

Written while the frozen allocation was live, after its two invalid openings
and before its terminal audit. This is descriptive and outside the frozen
protocol. Call it only on the frozen runner's audited readout. A full-delivery
proposal is hypothetical; it must never be reported as an enacted outcome.
"""
from __future__ import annotations

from itertools import combinations

from analysis.paper3_constituent_b_prevote import compare_offers, score_offer
from paper3 import coalition_contracts as game
from paper3.constituent_b_repeatability_analysis import EXCHANGE_FAMILIES


CONTRASTS = (("public_promise", "member_enforcement"),
             ("member_enforcement", "universal_clearance"))


def evaluate(source_profiles, audited_readout):
    """Keep every assigned arm and separate proposed from enacted welfare."""
    sources = {row["prepared"]["contract_profile"]["id"]: row
               for row in source_profiles}
    profiles = audited_readout["profiles"]
    if len(sources) != 7 or len(profiles) != 7 or len(sources) != len(source_profiles):
        raise ValueError("seven unique source and audited profiles required in inventory")
    if {row["profile_id"] for row in profiles} != set(sources):
        raise ValueError("audited profile inventory differs from source")
    for family in EXCHANGE_FAMILIES:
        repeated = sorted((row for row in source_profiles if row["family"] == family),
                          key=lambda row: row["repeatability_block"])
        if [row["repeatability_block"] for row in repeated] != [0, 1, 2]:
            raise ValueError("repeatability block inventory changed")
        prepared = [row["prepared"] for row in repeated]
        if any(item["contract_profile"]["utilities"] !=
               prepared[0]["contract_profile"]["utilities"] or
               item["electorate_profile"] != prepared[0]["electorate_profile"]
               for item in prepared[1:]):
            raise ValueError("within-family payoff or electorate changed")
    rows = []
    for profile in profiles:
        source = sources[profile["profile_id"]]
        prepared = source["prepared"]
        if set(profile["arms"]) != set(game.ARMS):
            raise ValueError("arm inventory differs from frozen institution")
        arms = {}
        for arm in game.ARMS:
            cell = profile["arms"][arm]
            if cell["status"] != "completed":
                arms[arm] = dict(status=cell["status"])
                continue
            draft = score_offer(prepared, cell["draft_terms"])
            final = score_offer(prepared, cell["final_terms"])
            enacted = cell["citizen_outcome"]
            arms[arm] = dict(
                status="completed", draft_full_delivery=draft,
                final_full_delivery=final,
                enacted_policy=enacted["policy_id"],
                enacted_total_citizen_relative_utility=
                enacted["overall"]["total_relative_utility"],
                enacted_citizens_worse_than_status_quo=
                enacted["overall"]["citizens_worse_than_q"],
            )
        contrasts = {}
        for left, right in CONTRASTS:
            key = left + "__" + right
            if arms[left]["status"] != "completed" or arms[right]["status"] != "completed":
                contrasts[key] = dict(completed=False)
                continue
            proposal = compare_offers(prepared, profile["arms"][left]["final_terms"],
                                      profile["arms"][right]["final_terms"])
            contrasts[key] = dict(
                completed=True,
                final_proposal=proposal,
                enacted_total_citizen_utility_change=(
                    arms[right]["enacted_total_citizen_relative_utility"] -
                    arms[left]["enacted_total_citizen_relative_utility"]),
                enacted_policy_changed=(arms[left]["enacted_policy"] !=
                                        arms[right]["enacted_policy"]),
            )
        rows.append(dict(profile_id=profile["profile_id"], family=source["family"],
                         block=source["repeatability_block"], arms=arms,
                         contrasts=contrasts))
    families = {}
    for family in EXCHANGE_FAMILIES:
        cells = sorted((row for row in rows if row["family"] == family),
                       key=lambda row: row["block"])
        if [row["block"] for row in cells] != [0, 1, 2]:
            raise ValueError("repeatability block inventory changed")
        within = {}
        for arm in game.ARMS:
            within[arm] = []
            for left, right in combinations(cells, 2):
                a, b = left["arms"][arm], right["arms"][arm]
                if a["status"] != "completed" or b["status"] != "completed":
                    within[arm].append(dict(blocks=[left["block"], right["block"]],
                                            completed=False))
                    continue
                within[arm].append(dict(
                    blocks=[left["block"], right["block"]], completed=True,
                    final_proposal_total_citizen_utility_change=(
                        b["final_full_delivery"]["total_citizen_relative_utility"] -
                        a["final_full_delivery"]["total_citizen_relative_utility"]),
                    final_proposal_policy_changed=(
                        a["final_full_delivery"]["full_delivery_policy"] !=
                        b["final_full_delivery"]["full_delivery_policy"]),
                ))
        families[family] = dict(within_arm_final_proposals=within)
    return dict(profiles=rows, exchange_families=families,
                limitation="Supplemental analysis added during the live run, not a frozen "
                           "or confirmatory criterion. Proposal metrics assume both offered "
                           "projects are delivered; enacted metrics use actual ballots. "
                           "Differences in either are descriptive on two constructed tables, "
                           "not a causal attribution to a contract mechanism.")
