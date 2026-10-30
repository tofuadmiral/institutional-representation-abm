"""Terminal-only presentation of frozen validation endpoints, not new inference.

Consumes the exact replay's report. All assigned profiles remain in each stratum
denominator, including unstarted and failed cases. Bounds are identification
ranges over missing finite-menu outcomes, not confidence intervals.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import json
from pathlib import Path


def interval(values):
    lo, hi = map(Fraction, values)
    if lo > hi:
        raise ValueError('reversed interval')
    return str(lo) if lo == hi else f'[{lo}, {hi}]'


def render(report, protocol):
    if report['integrity_errors']:
        raise ValueError('integrity audit failed; do not render a scientific result')
    frame = protocol['frame']
    seeds = frame['seeds']
    rows = report['profiles']
    if len(set(seeds)) != len(seeds) or [r['seed'] for r in rows] != seeds:
        raise ValueError('assigned profile inventory/order mismatch')
    if sum(r['complete'] for r in rows) != report['complete_profiles']:
        raise ValueError('completion count mismatch')
    groups = {'positive': frame['selection']['positive'], 'zero_control': frame['selection']['zero_control']}
    if sorted(sum(groups.values(), [])) != sorted(seeds):
        raise ValueError('stratum inventory mismatch')
    for row in rows:
        if row['stratum'] not in groups or row['seed'] not in groups[row['stratum']]:
            raise ValueError('stratum assignment mismatch')
        cells_complete = all(set(row['outcomes'].get(c, {})) == set('DB') for c in ('early', 'late'))
        if cells_complete != row['complete']:
            raise ValueError('completion/outcome mismatch')
    lines = [
        '# Held-out disclosure validation: terminal descriptive readout', '',
        f"Complete profiles: {report['complete_profiles']}/{len(seeds)}. "
        f"Recorded API attempts: {report['calls']} (not independent experimental units).",
        f"Batch accounting: ${report['accounted_usd']}; cumulative additional accounting: "
        f"${report['cumulative_additional_usd']}. Accounting includes unresolved reservations where applicable.", '',
        'One profile is one paired experimental unit. Late D/B share a pre-disclosure prefix. '
        'These theory-selected cases do not support a population reliability estimate or p-value.', '',
        '## All assigned outcomes', '',
        'Missing means unobserved, not enactment of status quo q.', '',
        '| Seed | Stratum | Complete | Early D | Early B | Late D | Late B |',
        '|---|---|---|---|---|---|---|',
    ]
    for r in rows:
        cells = [r['outcomes'].get(c, {}).get(a, 'missing') for c in ('early', 'late') for a in 'DB']
        lines.append('| '+ ' | '.join([str(r['seed']), r['stratum'], 'yes' if r['complete'] else 'no', *cells])+' |')
    lines += ['', '## Expected leader information benefit', '',
        'Benefit = [U(early D)+U(early B)-U(late D)-U(late B)] / (2 × leader utility range). '
        'Positive means advance information helped the leader’s principal. '
        'This is not the interaction in relative leader advantage and need not help other principals.', '',
        '| Seed | Scripted benchmark | Observed benefit / missing-cell bounds | Signed discrepancy / bounds |',
        '|---|---|---|---|']
    for r in rows:
        benchmark = Fraction(frame['predictions'][str(r['seed'])]['theory']['leader_value_of_information_normalized_exact'])
        bounds = list(map(Fraction, r['information_benefit_bounds_exact']))
        lines.append(f"| {r['seed']} | {benchmark} | {interval(bounds)} | {interval([v-benchmark for v in bounds])} |")
    lines += ['', '### Stratum summaries including every assigned profile', '',
        '| Stratum | Complete / assigned | Mean information benefit / bounds |', '|---|---|---|']
    for group, assigned in groups.items():
        if not assigned:
            raise ValueError('empty stratum')
        entries = [r for r in rows if r['stratum'] == group]
        means = [sum((Fraction(r['information_benefit_bounds_exact'][i]) for r in entries), Fraction(0))/len(assigned)
                 for i in (0, 1)]
        lines.append(f"| {group} | {sum(r['complete'] for r in entries)} / {len(assigned)} | {interval(means)} |")
    lines += ['', '## Original authority × timing contrasts', '',
        'Interaction = (late B − late D) − (early B − early D). '
        'Bracketed ranges retain missing cells; they are not confidence intervals.', '',
        '| Seed | Mean normalized regret interaction / bounds | Relative leader advantage interaction / bounds |',
        '|---|---|---|']
    for r in rows:
        def display(name):
            lo, hi = r['interaction_bounds'][name]
            return f'{lo:.6f}' if lo == hi else f'[{lo:.6f}, {hi:.6f}]'
        lines.append(f"| {r['seed']} | {display('mean_regret')} | {display('leader_advantage')} |")
    lines += ['', '## Interpretation limits', '',
        'Integrity success is not hypothesis success. Inspect the underlying audit JSON for all seven '
        'principal utility changes, proposal compatibility and conditional continuation fit. '
        'Do not replace an incomplete-frame result with a complete-case-only headline. '
        'Benchmark-compatible actions do not identify internal motives or equilibrium play. '
        'The late continuation retains lottery framing after its draw announcement; timing-only '
        'interpretation therefore needs wording robustness. Model, label and sampling-seed '
        'robustness remain separate requirements. No publication-readiness decision is automated.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    if not (args.root/'sessions/terminal.json').is_file():
        raise ValueError('run is still live or interrupted; no interim scientific report')
    from analysis.paper3_disclosure_validation_audit import audit
    protocol = json.loads((args.root/'manifest.json').read_text())['protocol']
    print(render(audit(args.root), protocol))


if __name__ == '__main__':
    main()
