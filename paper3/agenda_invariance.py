"""Offline game isomorphisms for prospective robustness controls.

No inference or changes to frozen experiments. Positive principal-specific
utility scaling preserves expected-utility rankings, not LLM behavior.
Policy relabeling preserves q because the existing rules name it explicitly.
"""
from __future__ import annotations

import copy
from paper3 import agenda_rights as game


def _permutation(mapping, labels, name):
    result = dict(zip(labels, labels)) if mapping is None else dict(mapping)
    if set(result) != set(labels) or set(result.values()) != set(labels):
        raise ValueError(name + " must be a complete bijection")
    return result


def transform_profile(profile, *, role_mapping=None, policy_mapping=None,
                      utility_scales=None, catalog_order=None):
    """Transform old labels to new labels; scale keys refer to original roles.

    Scale weighted losses, computed utilities and both priority weights together.
    Thus every displayed number remains consistent with the spatial definition.
    Catalog order is a permutation of the NEW policy labels; otherwise preserve
    the old positions. Actor order follows the same original semantic order.
    JSON sorting may change displayed key positions after relabeling: label and
    serialization sensitivity are not independently identified by this control.
    """
    roles = list(game.ROLES)
    policies = [p['policy_id'] for p in profile['catalog']]
    rm = _permutation(role_mapping, roles, 'role mapping')
    pm = _permutation(policy_mapping, policies, 'policy mapping')
    if pm['q'] != 'q' or profile['status_quo'] != 'q':
        raise ValueError('q must remain the named status quo')
    scales = {r: 1 for r in roles} if utility_scales is None else dict(utility_scales)
    if set(scales) != set(roles) or any(type(s) is not int or s <= 0 for s in scales.values()):
        raise ValueError('one positive integer scale per original principal is required')
    order = [pm[p] for p in policies] if catalog_order is None else list(catalog_order)
    if len(order) != len(policies) or set(order) != set(policies):
        raise ValueError('catalog order must list every new policy once')
    result = copy.deepcopy(profile)
    result['leader'], result['sponsor'] = rm[profile['leader']], rm[profile['sponsor']]
    result['actors'] = [rm[r] for r in profile['actors']]
    catalog = {pm[p['policy_id']]: dict(copy.deepcopy(p), policy_id=pm[p['policy_id']])
               for p in profile['catalog']}
    result['catalog'] = [catalog[p] for p in order]
    result['principals'] = {rm[r]: dict(copy.deepcopy(profile['principals'][r]),
        weights=[w * scales[r] for w in profile['principals'][r]['weights']]) for r in roles}
    for field in ('utilities', 'losses'):
        result[field] = {rm[r]: {pm[p]: v * scales[r] for p, v in profile[field][r].items()}
                         for r in roles}
    return result


def map_resolution_inputs(proposal, amendment, ballots, leader_choice, cards,
                          role_mapping, policy_mapping):
    """Map a fixed action history, not a new agent interaction or mediator."""
    return dict(proposal=policy_mapping[proposal], amendment=policy_mapping[amendment],
        ballots={role_mapping[r]: policy_mapping[p] for r, p in ballots.items()},
        leader_choice=policy_mapping[leader_choice],
        cards={role_mapping[r]: {policy_mapping[p]: vote for p, vote in card.items()}
               for r, card in cards.items()})
