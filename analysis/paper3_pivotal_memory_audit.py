"""Read-only descriptive audit of synthetic, consequential state-record probes."""
import argparse
import collections
import json
from pathlib import Path


def audit(root):
    manifest = json.loads((root / "manifest.json").read_text())
    groups = collections.defaultdict(list)
    paired = collections.defaultdict(dict)
    for case in manifest['protocol']['cases']:
        path = root / 'sessions' / (case['name'] + '.json')
        if not path.exists():
            continue
        r = json.loads(path.read_text())
        expected = case['expected']
        reply = r.get('reply', {})
        valid = r['status'] == 'completed'
        row = dict(case=case['base_case'], profile=case['profile_seed'], valid=valid,
            action_error=not valid or reply['vote'] != expected['vote'],
            state_error=not valid or reply['obligation_due'] != expected['obligation_due'],
            identity_error=not valid or reply['principal_id'] != expected['principal_id'],
            utility_error=not valid or reply['current_project_utility'] != expected['current_project_utility'],
            harmful_unbound_yes=valid and not expected['obligation_due'] and expected['current_project_utility'] < 0 and reply['vote'],
            due_no=valid and expected['obligation_due'] and not reply['vote'],
            marginal_payoff=expected['current_project_utility'] * int(reply['vote']) if valid else None)
        groups[case['view']].append(row)
        paired[case['base_case']][case['view']] = row
    summary = {}
    for view, rows in groups.items():
        summary[view] = dict(n=len(rows), **{k: sum(r[k] for r in rows) for k in (
            'valid', 'action_error', 'state_error', 'identity_error', 'utility_error', 'harmful_unbound_yes', 'due_no')})
    contrasts = {}
    for comparator in ('transcript', 'event_index'):
        rows = [r for r in paired.values() if 'registry' in r and comparator in r]
        contrasts[comparator] = dict(pairs=len(rows),
            registry_repairs=sum(r[comparator]['action_error'] and not r['registry']['action_error'] for r in rows),
            registry_corrupts=sum(not r[comparator]['action_error'] and r['registry']['action_error'] for r in rows))
    return dict(views=summary, paired_action_contrasts=contrasts, cases=dict(paired),
                warning='Two profiles; dependent state/actor cases. Invalid outputs have no imputed payoff.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    print(json.dumps(audit(parser.parse_args().root), indent=2))
