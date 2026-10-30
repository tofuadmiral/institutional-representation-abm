"""Descriptive fidelity of recorded final votes, not inferred motives.

Changing one submitted vote holds others fixed; this is an exact local
arithmetic check, not an alternative interaction trajectory or mediation claim.
"""
from __future__ import annotations
import copy
from paper3 import agenda_rights as game


def final_vote_fidelity(profile, arm, events):
    stages = {e['stage']:e for e in events}
    proposal = stages['locked_proposal']['action']['policy_id']
    amendment = stages['amendment']['action']['policy_id']
    ballots = stages['pairwise']['ballots']
    choice = stages['leader_selection']['action']['policy_id']
    cards = stages['ratification']['cards']
    result = game.resolve(profile, arm, proposal, amendment, ballots, choice, cards)
    selected, outcome = result['selected'],result['outcome']
    rows = {}
    for actor in game.ROLES:
        utility = profile['utilities'][actor]
        other_cards = copy.deepcopy(cards)
        other_cards[actor][selected] = not other_cards[actor][selected]
        alternative = game.resolve(profile, arm, proposal, amendment, ballots, choice, other_cards)
        gain = utility[alternative['outcome']] - utility[outcome]
        rows[actor] = dict(selected_policy=selected, selected_vote=cards[actor][selected],
            selected_vote_sign_consistent=cards[actor][selected] == (utility[selected] > 0) if utility[selected] != 0 else None,
            outcome_utility=utility[outcome], principal_worse_than_status_quo=utility[outcome] < 0,
            outcome_if_own_selected_vote_flipped=alternative['outcome'],
            pivotal=alternative['outcome'] != outcome,
            unilateral_vote_flip_gain=gain, strictly_harmful_own_vote=gain > 0,
            unselected_card_consistency={p:vote == (utility[p] > 0) if utility[p] != 0 else None
                for p,vote in cards[actor].items() if p != selected})
    return dict(resolution=result, actors=rows,
        harmed_principals=sum(r['principal_worse_than_status_quo'] for r in rows.values()),
        strictly_harmful_own_votes=sum(r['strictly_harmful_own_vote'] for r in rows.values()),
        scope='fixed-history final-vote deviation only; no motives, off-path replay validity or equilibrium inferred')
