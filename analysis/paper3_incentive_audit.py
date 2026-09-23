"""Analytic menu audit, not a new agent experiment or equilibrium estimator.

The outside-option benchmark holds the selected agenda fixed and assumes
unbound agents vote for positive-utility projects. It is not observed LLM play.
Perfect agreement delivery is a comparison outcome, not guaranteed behavior.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.commitment_memory import PACKAGES, PROJECTS, package_check


def audit_utilities(utilities):
    utilities = {str(k): v for k, v in utilities.items()}
    if set(utilities) != {str(i) for i in range(7)}:
        raise ValueError("requires seven distinct principals")
    if any(set(row) != set(PROJECTS) or any(type(v) is not int for v in row.values())
           for row in utilities.values()):
        raise ValueError("requires complete integer utilities")
    coalitions = [members for size in range(4, 8) for members in itertools.combinations(range(7), size)]
    results = []
    for package, projects in enumerate(PACKAGES):
        support = {p: [i for i in range(7) if utilities[str(i)][p] > 0] for p in projects}
        passed = [p for p in projects if len(support[p]) >= 4]
        outside = [sum(utilities[str(i)][p] for p in passed) for i in range(7)]
        both = [sum(utilities[str(i)][p] for p in projects) for i in range(7)]
        incremental = [b - o for b, o in zip(both, outside)]
        improving = [members for members in coalitions if all(incremental[i] >= 0 for i in members)
                     and any(incremental[i] > 0 for i in members)]
        zero_positive = [members for members in coalitions if all(both[i] > 0 for i in members)]
        zero_positive_with_loser = [members for members in zero_positive
                                   if any(incremental[i] < 0 for i in members)]
        results.append(dict(package=package, projects=list(projects), positive_support=support,
            independent_passed=passed, independent_payoffs=outside, perfect_delivery_payoffs=both,
            incremental_payoffs=incremental,
            strict_beneficiaries=[i for i in range(7) if incremental[i] > 0],
            losers=[i for i in range(7) if incremental[i] < 0],
            improving_coalitions=[list(m) for m in improving],
            positive_vs_zero_coalition_count=len(zero_positive),
            positive_vs_zero_with_outside_option_loser_count=len(zero_positive_with_loser),
            outsiders_harmed_by_each_improving_coalition=[
                dict(members=list(m), harmed_nonmembers=[i for i in range(7)
                    if i not in m and incremental[i] < 0]) for m in improving]))
    return dict(packages=results, assumptions=[
        "selected agenda fixed; both projects reach votes without ratification under the existing engine",
        "benchmark uses positive-utility unbound votes; zero-utility projects receive no vote by convention",
        "actual LLM decisions, beliefs, bargaining deviations and general equilibria are not estimated",
        "perfect delivery passes both projects; not a claim that promises are enforceable",
        "coalition consent is compared with benchmark material utility, not a fully specified utility for promise keeping"])


def audit_episode(episode):
    if episode.get("status") != "completed":
        raise ValueError("requires a completed episode for observed comparisons")
    result = audit_utilities(episode["profile"]["utilities"])
    final = next(e for e in episode["events"] if e["type"] == "final_offer")
    package_check(final)
    signatures = next(e for e in episode["events"] if e["type"] == "ratification")
    if signatures["offer_id"] != final["offer_id"]:
        raise ValueError("ratification does not reference final offer")
    if len(signatures["signatures"]) != 7 or any(type(x) is not bool for x in signatures["signatures"]):
        raise ValueError("invalid signature vector")
    selected = result["packages"][final["package"]]
    signers = [i for i, signed in enumerate(signatures["signatures"]) if signed]
    result["observed_offer"] = dict(package=final["package"], first=final["first"], signers=signers,
        signers_losing_relative_to_benchmark_if_fully_delivered=[
            dict(actor=i, independent_payoff=selected["independent_payoffs"][i],
                 full_delivery_payoff=selected["perfect_delivery_payoffs"][i],
                 difference=selected["incremental_payoffs"][i])
            for i in signers if selected["incremental_payoffs"][i] < 0],
        actual_realized_payoffs=[episode["realized_utility"][str(i)]
            if str(i) in episode["realized_utility"] else episode["realized_utility"][i] for i in range(7)])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("episode", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_episode(json.loads(args.episode.read_text())), indent=2))
