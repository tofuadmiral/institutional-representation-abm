"""Theory-only sensitivity to indifferent downstream choices.

Retain sincere strict preferences; allow either action when indifferent. Reject
profiles where indifferent final voters can change ratification. Enumerate the
remaining selector outcomes, then sponsor-optimal outcomes across all fixed
resolutions of downstream indifference. No tie probabilities are invented. This
is a conditional benchmark, not an equilibrium or a prediction of agent beliefs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from paper3 import agenda_benchmarks as bench
from paper3 import agenda_identification as strict
from paper3 import agenda_rights as game


def ratification_outcomes(profile, policy):
    q = profile['status_quo']
    if policy == q:
        return {q}
    values = [u[policy] for u in profile['utilities'].values()]
    minimum, maximum = sum(v > 0 for v in values), sum(v >= 0 for v in values)
    return ({policy} if maximum >= 4 else set()) | ({q} if minimum < 4 else set())


def selector_outcomes(profile, arm, proposal, amendment):
    if arm not in game.ARMS:
        raise ValueError('unknown authority rule')
    continuations = [ratification_outcomes(profile, p) for p in (proposal, amendment)]
    if any(len(s) != 1 for s in continuations):
        raise ValueError('ratification ambiguity; do not assume a tie probability')
    p, a = [next(iter(s)) for s in continuations]
    u = profile['utilities']
    if arm == 'D':
        delta = u[profile['leader']][a] - u[profile['leader']][p]
        return {a} if delta > 0 else {p} if delta < 0 else {p, a}
    deltas = [row[a] - row[p] for row in u.values()]
    minimum, maximum = sum(v > 0 for v in deltas), sum(v >= 0 for v in deltas)
    return ({a} if maximum >= 4 else set()) | ({p} if minimum < 4 else set())


def best_outcomes(possible, utilities):
    """Union of sponsor-best outcomes across independent fixed tie resolutions.

An outcome can maximize payoff in some resolution exactly when its payoff is at
least every alternative amendment's minimum. Tied best amendments are retained.
The result is not an expected payoff under uncertainty about others' choices.
"""
    threshold = max(min(utilities[o] for o in outcomes) for outcomes in possible.values())
    return {o for outcomes in possible.values() for o in outcomes if utilities[o] >= threshold}


def certificate(profile):
    ids = bench.policy_ids(profile)
    ambiguous = [p for p in ids if len(ratification_outcomes(profile, p)) != 1]
    result = dict(seed_name=profile['name'], ratification_ambiguous=ambiguous,
                  identified=False, stratum=None)
    if ambiguous:
        return result
    possible = {arm: {p: {a: selector_outcomes(profile, arm, p, a) for a in ids}
                       for p in ids} for arm in game.ARMS}
    sponsor = profile['utilities'][profile['sponsor']]
    outcomes = {arm: {p: sorted(best_outcomes(choices, sponsor)) for p, choices in row.items()}
                for arm, row in possible.items()}
    result.update(sponsor_best_outcomes=outcomes,
        identified=all(len(s) == 1 for row in outcomes.values() for s in row.values()))
    if not result['identified']:
        return result
    point = strict.certificate(profile)
    assert point['unique_sponsor_best_outcomes']
    assert all(point['sponsor_best'][arm][p]['outcomes'] == s
               for arm, row in outcomes.items() for p, s in row.items())
    value = Fraction(point['normalized_information_value_exact'])
    if value >= Fraction(1, 20) and point['early_B_separates_myopic_and_group']:
        result['stratum'] = 'positive_separating'
    elif value == 0 and all(len(point['own_best'][a]) < len(ids) for a in game.ARMS):
        result['stratum'] = 'zero_control'
    result['predictions'] = point
    return result


def scan(start, count):
    if type(start) is not int or type(count) is not int or start < 0 or count <= 0:
        raise ValueError('nonnegative integer start and positive integer count required')
    rows = [dict(seed=s, **certificate(bench.generated_profile(s))) for s in range(start, start + count)]
    return dict(scope=__doc__, start=start, count=count, rows=rows,
        counts=dict(Counter(r['stratum'] or 'not_eligible' for r in rows)),
        identified_count=sum(r['identified'] for r in rows),
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
        hashlib.sha256(Path(p).read_bytes()).hexdigest()
        for p in (__file__, strict.__file__, bench.__file__, game.__file__)}
    with args.output.open('x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, indent=2))
