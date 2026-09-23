"""Set-valued proposal benchmarks under explicitly scripted continuations.

These are not equilibria or tests of an LLM's hidden beliefs/objectives. Sponsor
tie-breaking and sincere continuation behavior remain those of agenda_benchmarks.
"""
from __future__ import annotations
from fractions import Fraction
from paper3 import agenda_benchmarks as bench
from paper3 import agenda_rights as game


def objective_benchmarks(profile):
    result={}
    for arm in game.ARMS:
        branches={p:bench.sponsor_response(profile,arm,p) for p in bench.policy_ids(profile)}
        own={p:profile['utilities'][profile['leader']][b['resolution']['outcome']]
            for p,b in branches.items()}
        group={p:sum((Fraction(row[b['resolution']['outcome']]-min(row.values()),
                max(row.values())-min(row.values())) for row in profile['losses'].values()),Fraction(0))/7
            for p,b in branches.items()}
        result[arm]=dict(
            own_best_proposals=[p for p in own if own[p]==max(own.values())],
            group_best_proposals=[p for p in group if group[p]==min(group.values())],
            continuation_own_utilities=own,
            continuation_mean_regret_exact={p:str(v) for p,v in group.items()},
            continuation_outcomes={p:b['resolution']['outcome'] for p,b in branches.items()},
            sponsor_amendments={p:b['amendment'] for p,b in branches.items()})
    return dict(arms=result,
        own_optimal_sets_disjoint=not(set(result['D']['own_best_proposals'])&set(result['B']['own_best_proposals'])),
        own_vs_group_disjoint={arm:not(set(r['own_best_proposals'])&set(r['group_best_proposals']))
            for arm,r in result.items()},
        assumptions='Fixed sponsor-response heuristic and sincere continuation behavior; retain all primary-objective '
            'ties at the proposal stage. Group objective minimizes equal-weight mean normalized regret of the '
            'scripted terminal policy, not the proposal itself. Not an equilibrium, actual counterfactual, or motive inference.')
