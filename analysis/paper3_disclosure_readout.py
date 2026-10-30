"""Supplementary descriptive readout, not new frozen primary endpoints.

Separate the leader's ex-ante utility loss from the original authority-by-timing
interaction in relative advantage. Retain all ties in competing choice heuristics.
No inference, no response editing, and no claim about private model motives.
"""
from fractions import Fraction

from paper3 import agenda_benchmarks as bench
from paper3 import agenda_rights as game
from paper3.agenda_disclosure_benchmarks import disclosure_benchmark
from paper3.agenda_objective_benchmarks import objective_benchmarks


def readout(profile, locked, outcomes):
    if set(locked) != {"early-D", "early-B", "late"} or any(
            set(outcomes.get(c, {})) != set(game.ARMS) for c in ("early", "late")):
        raise ValueError("complete profile required; never impute")
    theory = disclosure_benchmark(profile)
    objectives = objective_benchmarks(profile)
    ids = bench.policy_ids(profile)
    leader_u = profile["utilities"][profile["leader"]]
    myopic = {p: leader_u[bench.continuation(profile, p)] for p in ids}
    proposal_regret = {p: sum((Fraction(row[p] - min(row.values()),
                                        max(row.values()) - min(row.values()))
                               for row in profile["losses"].values()), Fraction(0)) / 7
                       for p in ids}
    alternatives = dict(
        immediate_own_best=[p for p in ids if leader_u[p] == max(leader_u.values())],
        ratification_only_own_best=[p for p in ids if myopic[p] == max(myopic.values())],
        proposal_mean_regret_best=[p for p in ids if proposal_regret[p] == min(proposal_regret.values())])
    own_sets = {**{f"early-{a}": theory["early_own_best_proposals"][a] for a in game.ARMS},
                "late": theory["late_own_best_proposals"]}
    group_sets = {**{f"early-{a}": objectives["arms"][a]["group_best_proposals"] for a in game.ARMS},
                  "late": theory["late_group_best_proposals"]}
    compatibility = {}
    for condition, p in locked.items():
        compatibility[condition] = dict(
            locked=p, scripted_own_best=p in own_sets[condition],
            scripted_group_best=p in group_sets[condition],
            alternatives={k: p in choices for k, choices in alternatives.items()},
            own_vs_ratification_only_disjoint=not set(own_sets[condition]).intersection(
                alternatives["ratification_only_own_best"]))
    # Equal probability over D and B. This is NOT the difference-in-differences
    # endpoint in relative leader advantage; that metric also includes others.
    losses = {}
    for role, u in profile["utilities"].items():
        loss = Fraction(sum(u[outcomes["early"][a]] - u[outcomes["late"][a]] for a in game.ARMS), 2)
        losses[role] = dict(raw_exact=str(loss), normalized_exact=str(loss / (max(u.values()) - min(u.values()))))
    fits = {c: {a: outcomes[c][a] == theory["continuation_outcomes"][a][
                            locked[f"early-{a}" if c == "early" else "late"]]
                for a in game.ARMS} for c in ("early", "late")}
    return dict(
        competing_proposal_sets=alternatives, compatibility=compatibility,
        observed_early_minus_late_expected_utility=losses,
        leader_expected_utility_loss_exact=losses[profile["leader"]]["raw_exact"],
        scripted_information_value_exact=theory["leader_value_of_information_exact"],
        leader_loss_matches_scripted_information_value=(Fraction(losses[profile["leader"]]["raw_exact"])
                                                       == Fraction(theory["leader_value_of_information_exact"])),
        enacted_matches_scripted_continuation_given_observed_lock=fits,
        scope="Supplementary post-discovery diagnostics. Compatibility is not motive identification; "
              "conditional continuation fit is not a unique ex-ante point prediction. "
              "Positive utility loss means advance information benefited that principal.")
