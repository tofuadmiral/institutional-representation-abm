"""Offline disclosure benchmark with a fixed proposal before a rule lottery.

Conditional on agenda_benchmarks' scripted sponsor/sincere continuation and an
expected-utility objective. Not an equilibrium or evidence about LLM beliefs.
"""
from __future__ import annotations

from fractions import Fraction
from paper3 import agenda_benchmarks as bench
from paper3 import agenda_rights as game


def disclosure_benchmark(profile, probability_binding=Fraction(1, 2)):
    if type(probability_binding) not in (int, Fraction):
        raise ValueError('use an exact Fraction or integer probability')
    probability = Fraction(probability_binding)
    if not 0 <= probability <= 1:
        raise ValueError('probability must be between zero and one')
    weights = {'D': 1-probability, 'B': probability}
    ids = bench.policy_ids(profile)
    branches = {a:{p:bench.sponsor_response(profile,a,p)['resolution']['outcome']
                   for p in ids} for a in game.ARMS}
    own = {a:{p:profile['utilities'][profile['leader']][outcome]
              for p,outcome in outcomes.items()} for a,outcomes in branches.items()}
    group = {a:{p:sum((Fraction(row[outcome]-min(row.values()),
                               max(row.values())-min(row.values()))
                      for row in profile['losses'].values()),Fraction(0))/7
                for p,outcome in outcomes.items()} for a,outcomes in branches.items()}
    expected_own = {p:sum((weights[a]*own[a][p] for a in game.ARMS),Fraction(0)) for p in ids}
    expected_group = {p:sum((weights[a]*group[a][p] for a in game.ARMS),Fraction(0)) for p in ids}
    best_before = max(expected_own.values())
    informed = sum((weights[a]*max(own[a].values()) for a in game.ARMS),Fraction(0))
    leader_utilities = profile['utilities'][profile['leader']].values()
    utility_range = max(leader_utilities)-min(leader_utilities)
    return dict(probability_binding_exact=str(probability),
        continuation_outcomes=branches,
        early_own_best_proposals={a:[p for p in ids if own[a][p]==max(own[a].values())] for a in game.ARMS},
        late_own_best_proposals=[p for p in ids if expected_own[p]==best_before],
        late_group_best_proposals=[p for p in ids if expected_group[p]==min(expected_group.values())],
        late_expected_own_utility_exact={p:str(v) for p,v in expected_own.items()},
        late_expected_mean_regret_exact={p:str(v) for p,v in expected_group.items()},
        full_information_own_utility_exact=str(informed),
        best_lottery_own_utility_exact=str(best_before),
        leader_value_of_information_exact=str(informed-best_before),
        leader_value_of_information_normalized_exact=str((informed-best_before)/utility_range),
        assumptions='One locked proposal chosen before the public rule lottery; maximize expected own utility '
            'under fixed scripted sponsor response, sincere voting and declared tie conventions. All proposal '
            'ties retained. Not an equilibrium, actual interacting counterfactual, natural mediation or LLM finding.')
