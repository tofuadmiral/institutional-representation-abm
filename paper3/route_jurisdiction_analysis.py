"""All-assignment readout for a prospective route-jurisdiction discovery pilot.

No inference, files or model calls. A four-profile discovery readout is not a
population estimate. Missing episodes are retained with finite bounds rather
than silently removed from the denominator.
"""
from __future__ import annotations

from paper3 import route_jurisdiction as game


def readout(profiles, records):
    """records maps (profile_name, arm) to an episode result or None."""
    names = [p["name"] for p in profiles]
    if len(names) != len(set(names)):
        raise ValueError("duplicate profile")
    expected = {(name, arm) for name in names for arm in game.ARMS}
    if set(records) != expected:
        raise ValueError("every assigned episode, including missing ones, is required")
    pairs, assignments = [], []
    observed_regret_sum = 0.0
    observed_changed = 0
    completed_pairs = 0
    for p in profiles:
        outcomes = {}
        for arm in game.ARMS:
            result = records[(p["name"], arm)]
            if result is None:
                result = dict(status="not_started")
            if result.get("status") not in ("completed", "failed", "not_started"):
                raise ValueError("invalid episode status")
            assignment = dict(profile=p["name"], family=p.get("family"), arm=arm,
                              status=result["status"])
            if result["status"] == "completed":
                offer = result["offer"]
                resolution = result["resolution"]
                actions = result["actions"]
                expected_stages = (["recommendation"] * len(p["actors"]) + ["offer"]
                                   + ["ballot"] * len(p["actors"]) + ["review"])
                if [a.get("stage") for a in actions] != expected_stages:
                    raise ValueError("episode action trace incomplete")
                replay = {other: game.resolve(p, other, offer, result["ballots"], result["review"])
                          for other in game.ARMS}
                if (resolution != game.resolve(p, arm, offer, result["ballots"], result["review"])
                        or result["fixed_action_replay"] != replay
                        or result["offer_metrics"] != game.metrics(p, offer["policy_id"])
                        or result["outcome_metrics"] != game.metrics(p, resolution["outcome"])):
                    raise ValueError("episode readout does not replay")
                assignment.update(actions=actions, recommendations=result["recommendations"],
                                  offer=offer, ballots=result["ballots"], review=result["review"],
                                  resolution=resolution, fixed_action_replay=replay,
                                  offer_utilities=result["offer_metrics"]["utilities"],
                                  outcome_utilities=result["outcome_metrics"]["utilities"],
                                  outcome_own_best_regret=result["outcome_metrics"]["own_best_regret"],
                                  outcome_mean_regret=result["outcome_metrics"]["mean_regret"],
                                  outcome_total_utility=result["outcome_metrics"]["total_utility"],
                                  outcome_worst_utility=result["outcome_metrics"]["worst_utility"],
                                  outsider_harms=[a for a in result["outcome_metrics"]["harmed_vs_status_quo"]
                                                  if a not in (p["proposer"], p["reviewer"])])
                outcomes[arm] = result
            else:
                assignment["error"] = result.get("error")
            assignments.append(assignment)
        pair = dict(profile=p["name"], family=p.get("family"),
                    narrow_status=records[(p["name"], "narrow")]["status"]
                    if records[(p["name"], "narrow")] is not None else "not_started",
                    comprehensive_status=records[(p["name"], "comprehensive")]["status"]
                    if records[(p["name"], "comprehensive")] is not None else "not_started")
        if len(outcomes) == 2:
            completed_pairs += 1
            n, c = outcomes["narrow"], outcomes["comprehensive"]
            changed_policy = n["offer"]["policy_id"] != c["offer"]["policy_id"]
            changed_route = n["offer"]["route"] != c["offer"]["route"]
            observed_changed += changed_policy or changed_route
            regret_diff = c["outcome_metrics"]["mean_regret"] - n["outcome_metrics"]["mean_regret"]
            observed_regret_sum += regret_diff
            pair.update(status="paired", narrow_offer=n["offer"], comprehensive_offer=c["offer"],
                        pre_vote_policy_changed=changed_policy, pre_vote_route_changed=changed_route,
                        reviewer_offer_utility_delta=(c["offer_metrics"]["utilities"][p["reviewer"]]
                                                      - n["offer_metrics"]["utilities"][p["reviewer"]]),
                        proposer_offer_utility_delta=(c["offer_metrics"]["utilities"][p["proposer"]]
                                                      - n["offer_metrics"]["utilities"][p["proposer"]]),
                        mean_regret_delta=regret_diff,
                        narrow_fixed_action_replay=n["fixed_action_replay"],
                        comprehensive_fixed_action_replay=c["fixed_action_replay"])
        else:
            pair["status"] = "incomplete"
        pairs.append(pair)
    total = len(profiles)
    if total == 0:
        raise ValueError("at least one profile required")
    missing = total - completed_pairs
    return dict(assignments=assignments, pairs=pairs, total_pairs=total,
                completed_pairs=completed_pairs, missing_pairs=missing,
                pre_vote_any_change_rate_bounds=[observed_changed / total,
                                                 (observed_changed + missing) / total],
                mean_regret_delta_bounds=[(observed_regret_sum - missing) / total,
                                          (observed_regret_sum + missing) / total],
                caveat="Constructed discovery profiles only; replayed blocking is mechanical, not behavioral."
                " No p-value or population generalization from this readout.")
