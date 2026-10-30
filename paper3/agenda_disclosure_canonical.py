"""Prospective disclosure instrument with identical post-lock current-rule text.

Earlier instruments are immutable. Only the pre-lock rule information differs:
known D/B versus an honest fair lottery. Both regimes append the same-format
authority_in_force event after lock and use game.messages thereafter. Legitimate
participant histories remain different. No inference or filesystem effects.
"""
from __future__ import annotations

import copy

from paper3 import agenda_rights as game
from paper3 import agenda_disclosure as previous


def prefix(profile, arm, ask):
    """arm=None means unknown fair lottery; ask(messages, path_position)."""
    if arm not in (None, *game.ARMS):
        raise ValueError('unknown authority rule')
    events, actions = [], []
    catalog = [p['policy_id'] for p in profile['catalog']]

    def act(actor, stage):
        messages = (previous.messages_late(profile, actor, stage, events, None)
                    if arm is None else game.messages(profile, arm, actor, stage, events))
        value = game.validate_action(ask(messages, len(actions)), stage, catalog)
        actions.append(dict(actor=actor, stage=stage, action=value,
                            overlong_message=len(value.get('message', '')) > 400))
        return value

    try:
        opening = act(profile['leader'], 'opening')
        events.append(dict(stage='opening', actor=profile['leader'], action=opening))
        # All responses see the same public history, never one another's replies.
        responses = {r: act(r, 'responses') for r in game.ROLES}
        events.append(dict(stage='responses', actions=responses))
        locked = act(profile['leader'], 'locked_proposal')
        events.append(dict(stage='locked_proposal', actor=profile['leader'], action=locked))
        assert len(actions) == 9
        return dict(status='completed', events=events, actions=actions,
                    opening=opening['policy_id'], locked=locked['policy_id'])
    except (ValueError, KeyError) as exc:
        return dict(status='failed', error=str(exc), events=events, actions=actions)


def continuation(profile, arm, ask, start):
    if arm not in game.ARMS or start['status'] != 'completed':
        raise ValueError('completed prefix and known authority required')
    events = copy.deepcopy(start['events']) + [dict(stage='authority_in_force', rule=arm)]
    actions = copy.deepcopy(start['actions'])
    catalog = [p['policy_id'] for p in profile['catalog']]

    def act(actor, stage, candidates=None):
        value = game.validate_action(
            ask(game.messages(profile, arm, actor, stage, events, candidates), len(actions)),
            stage, candidates if candidates is not None else catalog)
        actions.append(dict(actor=actor, stage=stage, action=value,
                            overlong_message=len(value.get('message', '')) > 400))
        return value

    try:
        amendment = act(profile['sponsor'], 'amendment')
        events.append(dict(stage='amendment', actor=profile['sponsor'], action=amendment))
        p, a = start['locked'], amendment['policy_id']
        candidates = list(dict.fromkeys([p, a]))
        ballots = {r: act(r, 'pairwise', candidates)['policy_id'] for r in game.ROLES}
        events.append(dict(stage='pairwise', ballots=ballots))
        choice = act(profile['leader'], 'leader_selection', candidates)
        events.append(dict(stage='leader_selection', actor=profile['leader'], action=choice))
        cards = {r: act(r, 'ratification', candidates)['votes'] for r in game.ROLES}
        events.append(dict(stage='ratification', cards=cards))
        outcome = game.resolve(profile, arm, p, a, ballots, choice['policy_id'], cards)
        assert len(actions) == 25
        return dict(status='completed', events=events, actions=actions, resolution=outcome,
            metrics={stage: game.metrics(profile, policy) for stage, policy in
                     (('opening', start['opening']), ('locked_proposal', p), ('enacted', outcome['outcome']))})
    except (ValueError, KeyError) as exc:
        return dict(status='failed', error=str(exc), events=events, actions=actions)


def run_early(profile, arm, ask):
    start = prefix(profile, arm, ask)
    if start['status'] != 'completed':
        return start
    return continuation(profile, arm, ask, start)


def run_late(profile, ask, order):
    if sorted(order) != sorted(game.ARMS):
        raise ValueError('branch order must contain D and B once')
    start = prefix(profile, None, ask)
    out = dict(prefix_events=start['events'], prefix_actions=start['actions'], branch_order=list(order))
    if start['status'] != 'completed':
        return dict(out, status='failed', error=start['error'], branches={
            a: dict(status='failed', error='prefix failed: '+start['error']) for a in order})
    # Each continuation owns a deep copy. The shared prefix is never mutated.
    branches = {arm: continuation(profile, arm, ask, start) for arm in order}
    done = [b['status'] == 'completed' for b in branches.values()]
    return dict(out, status='completed' if all(done) else 'partial' if any(done) else 'failed',
                locked_proposal=start['locked'], branches=branches,
                prefix_metrics={s: game.metrics(profile, start[k])
                                for s, k in (('opening', 'opening'), ('locked_proposal', 'locked'))})
