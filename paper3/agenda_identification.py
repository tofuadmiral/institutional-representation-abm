"""Offline identification certificates, not an inference protocol or LLM evidence.

Enumerate all sponsor-best amendments under sincere downstream behavior. Distinct
amendments with the same enacted outcome are not outcome ambiguity. The optional
strict screen removes payoff indifference between distinct continuation outcomes
and non-status-quo zero-utility ratification choices. It does not establish an
equilibrium, rule out strategic voting, or validate a model of human politics.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
from itertools import combinations
import json
from pathlib import Path

from paper3 import agenda_benchmarks as bench
from paper3 import agenda_rights as game


def certificate(profile):
    ids = bench.policy_ids(profile)
    u = profile['utilities']
    continuations = sorted({bench.continuation(profile, p) for p in ids})
    weak_pairs = {r: [[p, a] for p, a in combinations(continuations, 2)
                      if u[r][p] == u[r][a]] for r in game.ROLES}
    zero_cards = {r: [p for p in ids if p != profile['status_quo'] and u[r][p] == 0]
                  for r in game.ROLES}
    options = {}
    for arm in game.ARMS:
        options[arm] = {}
        for proposal in ids:
            outcomes = {a: bench.finish(profile, arm, proposal, a)['outcome'] for a in ids}
            best = max(u[profile['sponsor']][o] for o in outcomes.values())
            amendments = [a for a, o in outcomes.items() if u[profile['sponsor']][o] == best]
            options[arm][proposal] = dict(amendments=amendments,
                outcomes=sorted({outcomes[a] for a in amendments}))
    unique = all(len(v['outcomes']) == 1 for row in options.values() for v in row.values())
    result = dict(name=profile['name'],
        profile_sha256=hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest(),
        continuation_outcomes=continuations, indifferent_continuation_pairs=weak_pairs,
        zero_utility_non_q_cards=zero_cards, sponsor_best=options,
        unique_sponsor_best_outcomes=unique,
        strict_downstream_preferences=not any(weak_pairs.values()) and not any(zero_cards.values()),
        stratum=None)
    if not unique:
        return result  # A single point value is not identified by these assumptions.
    own, group = {}, {}
    for arm, row in options.items():
        own[arm] = {p: Fraction(u[profile['leader']][v['outcomes'][0]]) for p, v in row.items()}
        group[arm] = {p: sum((Fraction(max(ur.values()) - ur[v['outcomes'][0]],
                                      max(ur.values()) - min(ur.values()))
                              for ur in u.values()), Fraction(0)) / len(u) for p, v in row.items()}
    own['late'] = {p: (own['D'][p] + own['B'][p]) / 2 for p in ids}
    group['late'] = {p: (group['D'][p] + group['B'][p]) / 2 for p in ids}
    own_best = {c: [p for p, v in row.items() if v == max(row.values())] for c, row in own.items()}
    group_best = {c: [p for p, v in row.items() if v == min(row.values())] for c, row in group.items()}
    viable = {p: u[profile['leader']][bench.continuation(profile, p)] for p in ids}
    myopic = [p for p, v in viable.items() if v == max(viable.values())]
    leader_range = max(u[profile['leader']].values()) - min(u[profile['leader']].values())
    value = ((max(own['D'].values()) + max(own['B'].values())) / 2 - max(own['late'].values())) / leader_range
    separated = not set(own_best['B']).intersection(group_best['B']) and not set(own_best['B']).intersection(myopic)
    stratum = None
    if result['strict_downstream_preferences']:
        if value >= Fraction(1, 20) and separated:
            stratum = 'positive_separating'
        elif value == 0 and all(len(own_best[a]) < len(ids) for a in game.ARMS):
            stratum = 'zero_control'
    result.update(own_payoffs_exact={c: {p: str(v) for p, v in row.items()} for c, row in own.items()},
        own_best=own_best, group_best=group_best, ratification_only_best=myopic,
        normalized_information_value_exact=str(value),
        early_B_separates_myopic_and_group=separated, stratum=stratum)
    return result


def scan(start, count):
    if type(start) is not int or type(count) is not int or start < 0 or count <= 0:
        raise ValueError('nonnegative integer start and positive integer count required')
    rows = [dict(seed=s, **certificate(bench.generated_profile(s))) for s in range(start, start + count)]
    return dict(scope=__doc__, start=start, count=count, rows=rows,
        counts=dict(Counter(r['stratum'] or 'not_eligible' for r in rows)),
        strict_count=sum(r['strict_downstream_preferences'] for r in rows),
        unique_outcome_count=sum(r['unique_sponsor_best_outcomes'] for r in rows),
        first_two_witnesses={c: [r['seed'] for r in rows if r['stratum'] == c][:2]
                            for c in ('positive_separating', 'zero_control')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--count', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = scan(args.start, args.count)
    report['source_sha256'] = {str(Path(p).relative_to(Path(__file__).resolve().parents[1])):
        hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (__file__, bench.__file__, game.__file__)}
    with args.output.open('x') as f:  # Refuse replacement of a previous scan.
        json.dump(report, f, indent=2)
        f.write('\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, indent=2))
