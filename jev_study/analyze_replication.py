"""Paired held-out analysis; run only once the frozen sample is complete."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jev_study.audit import audit
from jev_study.bill_choice import score


def analyze(root):
    summary = audit(root)
    if summary['not_run']:
        raise ValueError('Complete sample required; inspect missing responses separately')
    manifest = json.loads((root / 'manifest.json').read_text())
    snapshots = json.loads((root / 'sources.json').read_text())
    for path, expected in manifest['sources'].items():
        # Frozen manifests retain their original absolute paths. Match the
        # archived relative source names without requiring that checkout path.
        matches = [name for name in snapshots if Path(path).as_posix().endswith('/' + name)]
        assert len(matches) == 1, 'Ambiguous or missing archived source'
        relative = matches[0]
        assert hashlib.sha256(snapshots[relative].encode()).hexdigest() == expected
    pairs = defaultdict(dict)
    response_shapes = set()
    for case in manifest['protocol']['cases']:
        name = case['name']
        record = json.loads((root / 'calls' / f'{name}.json').read_text())
        response = json.loads(record['response_text'])
        session = json.loads((root / 'sessions' / f'{name}.json').read_text())
        try:
            metrics = score(case, response)
            metrics['probabilities_valid'] = True
            assert session['status'] == 'completed'
            for field in ('correct', 'chosen_policy_index', 'selected_probability'):
                assert metrics[field] == session['metrics'][field]
        except (ValueError, KeyError, TypeError):
            assert session['status'] == 'failed'
            # Retain failures; do not renormalize. Separately assess the choice
            # only if the returned label is an unambiguous allowed option.
            choice = response.get('answers', {}).get('bill', {}).get('choice')
            metrics = dict(probabilities_valid=False, correct=choice == case['expected'],
                           chosen_policy_index=case['label_to_policy_index'].get(choice, -1))
        pairs[case['base_seed']][case['arm']] = metrics
        response_shapes.add(tuple(sorted(response)))
    rows = [pairs[k] for k in sorted(pairs)]
    assert len(rows) == 120 and all(len(r) == 7 for r in rows)
    # Resampling units are complete constituent profiles, never individual calls.
    indices = np.random.default_rng(20260918).integers(0, len(rows), (10000, len(rows)))

    def interval(values):
        values = np.asarray(values, dtype=float)
        return dict(estimate=float(values.mean()),
                    bootstrap_95=list(map(float, np.quantile(values[indices].mean(axis=1), [.025, .975]))))

    for arm, arm_summary in summary['arms'].items():
        arm_summary['choice_correct_all_responses'] = sum(r[arm]['correct'] for r in rows)
        arm_summary['accuracy_interval'] = interval([r[arm]['correct'] for r in rows])
        valid = [r[arm] for r in rows if r[arm]['probabilities_valid']]
        arm_summary['probability_minus_accuracy'] = interval([
            r[arm]['selected_probability'] - int(r[arm]['correct']) for r in rows]) if len(valid) == len(rows) else None
        finite = [r['log_loss'] for r in valid if not r['infinite_log_loss']]
        arm_summary['mean_log_loss'] = sum(finite) / len(finite) if finite and len(finite) == len(valid) else None
        arm_summary['log_loss_is_infinite'] = len(finite) != len(valid)

    contrasts = {}
    repeat_changes = [r['plain']['chosen_policy_index'] != r['plain_repeat']['chosen_policy_index'] for r in rows]
    for arm in ('plain_repeat', 'reverse_order', 'relabel', 'nonbinding_endorsement', 'neutral', 'neutral_repeat'):
        changes = [r['plain']['chosen_policy_index'] != r[arm]['chosen_policy_index'] for r in rows]
        contrasts[arm] = dict(
            accuracy_difference=interval([int(r[arm]['correct']) - int(r['plain']['correct']) for r in rows]),
            policy_disagreement=interval(changes),
            disagreement_minus_identical_repeat=interval([int(a) - int(b) for a,b in zip(changes, repeat_changes)]))
    neutral_changes = [r['neutral']['chosen_policy_index'] != r['neutral_repeat']['chosen_policy_index'] for r in rows]
    summary.update(profile_count=len(rows), contrasts=contrasts,
                   neutral_repeat_disagreement=interval(neutral_changes),
                   response_top_level_fields=[list(x) for x in sorted(response_shapes)],
                   inference='Descriptive profile-bootstrap intervals, not multiplicity-adjusted significance tests. Repeat disagreement bounds interpretation of presentation interventions.')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.root), indent=2))
