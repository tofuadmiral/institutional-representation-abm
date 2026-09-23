"""Descriptive stage readouts; fixed-output replays are not causal mediation.

No calls, prompt edits, imputation, or rescoring of earlier frozen protocols.
"""
from __future__ import annotations
from paper3 import agenda_rights as game


def policy_change(profile, before, after):
    first, second = game.metrics(profile, before), game.metrics(profile, after)
    changes = {r: second['utilities'][r] - first['utilities'][r] for r in game.ROLES}
    return dict(before=before, after=after,
        mean_regret_change=second['mean_regret'] - first['mean_regret'],
        leader_advantage_change=second['leader_advantage'] - first['leader_advantage'],
        principal_utility_changes=changes,
        principals_gaining=sum(x > 0 for x in changes.values()),
        principals_losing=sum(x < 0 for x in changes.values()))


def fixed_output_replay(episode):
    """Switch only the selector on a completed recorded action history.

    Conditional cards can be off path. Neither switched outcome represents a
    newly interacting institution; do not interpret the contrast as mediation.
    """
    if episode['status'] != 'completed':
        raise ValueError('completed history required')
    events = {e['stage']: e for e in episode['events']}
    profile = episode['profile']
    p = events['locked_proposal']['action']['policy_id']
    a = events['amendment']['action']['policy_id']
    outcomes = {arm: game.resolve(profile, arm, p, a,
        events['pairwise']['ballots'], events['leader_selection']['action']['policy_id'],
        events['ratification']['cards']) for arm in game.ARMS}
    if outcomes[episode['arm']] != episode['resolution']:
        raise ValueError('observed outcome disagrees with recorded actions')
    return dict(resolutions=outcomes,
        selector_only_B_minus_D=policy_change(profile,
            outcomes['D']['outcome'], outcomes['B']['outcome']))


def paired_readout(episodes):
    """One shared-profile episode pair, never 50 independent observations.

    The frozen experiment audit must establish request provenance and seed
    pairing separately; this descriptive helper does not certify either.
    """
    if set(episodes) != set(game.ARMS):
        raise ValueError('both assigned arms must be represented')
    d, b = episodes['D'], episodes['B']
    if d['arm'] != 'D' or b['arm'] != 'B' or d['profile'] != b['profile']:
        raise ValueError('mismatched arm labels or profiles')
    report = dict(profile=d['profile']['name'],
        status_by_arm={arm: s['status'] for arm, s in episodes.items()},
        complete_pair=all(s['status'] == 'completed' for s in episodes.values()),
        interpretation='One paired episode: descriptive only; no mediation or population inference.')
    if not report['complete_pair']:
        return dict(report, reason='Incomplete pair: outcomes and contrasts not imputed.')
    profile = d['profile']
    replays = {arm: fixed_output_replay(s) for arm, s in episodes.items()}
    staged = {}
    for stage in ('opening', 'locked_proposal', 'amendment'):
        policies = {arm: next(e['action']['policy_id'] for e in s['events']
            if e['stage'] == stage) for arm, s in episodes.items()}
        staged[stage] = dict(policy_by_arm=policies,
            B_minus_D=policy_change(profile, policies['D'], policies['B']))
    return dict(report, stages=staged,
        enacted_B_minus_D=policy_change(profile, d['resolution']['outcome'], b['resolution']['outcome']),
        same_history_selector_replays=replays,
        primary_endpoints=dict(
            locked_leader_advantage_B_minus_D=staged['locked_proposal']['B_minus_D']['leader_advantage_change'],
            enacted_mean_regret_B_minus_D=game.metrics(profile,b['resolution']['outcome'])['mean_regret']
                - game.metrics(profile,d['resolution']['outcome'])['mean_regret']),
        caveat='A pre-selection policy difference can reflect stochastic variation or prompt sensitivity; '
            'replicated rule contrasts and incentive-sensitive controls are needed to support anticipation. '
            'Within-history selector replays hold post-treatment choices fixed and are not causal mediation.')
