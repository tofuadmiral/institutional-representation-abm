"""Post-hoc choice diagnostics; never a revision of frozen endpoints.

Relax sponsor payoff ties while keeping the original benchmark's sincere
ratification/pairwise voting and leader selector. Interval dominance is relative
to those assumptions, not an equilibrium, motive, or empirical counterfactual.
All assigned profiles are retained; incomplete episodes are not imputed.
"""
from __future__ import annotations
import argparse
import copy
from fractions import Fraction
import json
from pathlib import Path

from paper3 import agenda_benchmarks as bench
from paper3 import agenda_rights as game


def sponsor_options(profile, arm, proposal):
    resolutions = {a: bench.finish(profile, arm, proposal, a)
                   for a in bench.policy_ids(profile)}
    u = profile['utilities'][profile['sponsor']]
    best = max(u[r['outcome']] for r in resolutions.values())
    return {a: r for a, r in resolutions.items() if u[r['outcome']] == best}


def proposal_bounds(profile, condition):
    if condition not in ('D', 'B', 'late'):
        raise ValueError('unknown disclosure condition')
    arms = ('D', 'B') if condition == 'late' else (condition,)
    u = profile['utilities'][profile['leader']]
    bounds = {}
    for p in bench.policy_ids(profile):
        per_arm = [[u[r['outcome']] for r in sponsor_options(profile, arm, p).values()]
                   for arm in arms]
        bounds[p] = [sum((Fraction(fn(v), len(arms)) for v in per_arm), Fraction(0))
                     for fn in (min, max)]
    return bounds


def lock_report(profile, condition, policy):
    bounds = proposal_bounds(profile, condition)
    return dict(locked=policy, leader_payoff_bounds_exact=list(map(str, bounds[policy])),
                robust_dominators={p: dict(bounds_exact=list(map(str, interval)),
                                          minimum_gain_exact=str(interval[0]-bounds[policy][1]))
                                   for p, interval in bounds.items()
                                   if interval[0] > bounds[policy][1]})


def episode_report(profile, arm, episode):
    if episode.get('status') != 'completed':
        raise ValueError('completed episode required; do not impute')
    e = {event['stage']: event for event in episode['events']}
    p, a = [e[s]['action']['policy_id'] for s in ('locked_proposal', 'amendment')]
    ballots = e['pairwise']['ballots']
    choice = e['leader_selection']['action']['policy_id']
    cards = e['ratification']['cards']
    result = game.resolve(profile, arm, p, a, ballots, choice, cards)
    if result != episode['resolution']:
        raise ValueError('saved resolution mismatch')
    options = sponsor_options(profile, arm, p)
    u = profile['utilities']
    pairwise_departures = []
    for actor, vote in ballots.items():
        if u[actor][bench.continuation(profile, vote)] < max(
                u[actor][bench.continuation(profile, q)] for q in {p, a}):
            pairwise_departures.append(actor)
    leader_departure = u[profile['leader']][bench.continuation(profile, choice)] < max(
        u[profile['leader']][bench.continuation(profile, q)] for q in {p, a})
    card_departures = []
    for actor, card in cards.items():
        for policy, vote in card.items():
            value = u[actor][policy]
            if value == 0 or vote == (value > 0):
                continue  # Utility-zero choices are indifferent, not wrong.
            flipped = copy.deepcopy(cards)
            flipped[actor][policy] = not vote
            other = game.resolve(profile, arm, p, a, ballots, choice, flipped)
            card_departures.append(dict(actor=actor, policy=policy, vote=vote, utility=value,
                selected=policy == result['selected'],
                fixed_history_flip_outcome=other['outcome'],
                fixed_history_flip_gain=u[actor][other['outcome']]-u[actor][result['outcome']]))
    return dict(locked=p, amendment=a, outcome=result['outcome'],
        sponsor_payoff_maximizing=a in options,
        all_sponsor_best_amendments=list(options),
        all_sponsor_best_outcomes=sorted({r['outcome'] for r in options.values()}),
        point_benchmark_outcome=bench.sponsor_response(profile, arm, p)['resolution']['outcome'],
        same_pair_scripted_outcome=bench.finish(profile, arm, p, a)['outcome'],
        pairwise_strict_preference_departures=pairwise_departures,
        leader_strict_preference_departure=leader_departure,
        leader_choice_binding=arm == 'D', card_departures=card_departures)


def diagnose(root):
    from analysis.paper3_disclosure_validation_audit import audit
    root = Path(root)
    if not (root/'sessions/terminal.json').is_file():
        raise ValueError('terminal run required')
    original = audit(root)
    if original['integrity_errors']:
        raise ValueError('frozen integrity audit failed')
    frame = json.loads((root/'manifest.json').read_text())['protocol']['frame']
    profiles = []
    for i, profile in enumerate(frame['profiles']):
        locks, episodes = {}, {}
        for path in sorted((root/f'profile-{i}/sessions').glob('*.json')):
            if path.stem == 'terminal':
                continue
            session = json.loads(path.read_text())
            if session['condition'] == 'late':
                if session.get('locked_proposal'):
                    locks['late'] = lock_report(profile, 'late', session['locked_proposal'])
                branches = session['branches']
            else:
                for action in session.get('actions', []):
                    if action['stage'] == 'locked_proposal':
                        arm = session['arm']
                        locks['early-'+arm] = lock_report(profile, arm, action['action']['policy_id'])
                branches = {session['arm']: session}
            for arm, episode in branches.items():
                if episode.get('status') == 'completed':
                    episodes[session['condition']+'-'+arm] = episode_report(profile, arm, episode)
        profiles.append(dict(seed=frame['seeds'][i], complete=original['profiles'][i]['complete'],
                             locks=locks, completed_episodes=episodes))
    return dict(post_hoc=True, frozen_integrity_errors=original['integrity_errors'], profiles=profiles,
        scope=__doc__ + ' Public actions only; no private reasoning used as evidence of motives. '
        'Single-card flips hold every other recorded action fixed and are not fresh trajectories. '
        'Primary frozen outcomes and stratum definitions are unchanged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    print(json.dumps(diagnose(parser.parse_args().root), indent=2))
