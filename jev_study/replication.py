"""Prespecified held-out paired study; no response-dependent task selection."""
import copy
import random
from jev_study.bill_choice import make_cases


def signature(case):
    return (tuple(case['desired']), tuple(case['priority']),
            tuple(sorted(tuple(p) for p in case['policies'].values())))


def make_replication():
    seen = {signature(c) for c in make_cases()}
    cases = []
    accepted = 0
    for seed in range(92000, 100000):
        group = make_cases([seed])
        sig = signature(group[0])
        if sig in seen:
            continue
        seen.add(sig)
        accepted += 1
        repeat = copy.deepcopy(group[0])
        repeat.update(name=f'{seed}-plain_repeat', arm='plain_repeat')
        group.append(repeat)
        # Isomorphic nonpolitical control. Same rule, labels, ordering and
        # desired binary configuration, but no bill/constituent vocabulary.
        neutral = copy.deepcopy(group[0])
        neutral.update(name=f'{seed}-neutral', arm='neutral')
        state = neutral['request']['state']
        state['setting'] = 'Synthetic device-configuration task, not a forecast of real users.'
        state['user_priorities'] = [f'set switch {i + 1} to {neutral["desired"][i]}'
                                    for i in neutral['priority']]
        del state['constituent_priorities']
        state['authority'] = 'The user alone defines the requirements. Recommendations by other actors are nonbinding and supply no facts about configuration consequences.'
        question = neutral['request']['questions']['bill']
        question['instructions'] = 'Which option best satisfies this user\'s requirements? Select from the stated configurations, including retaining the current configuration.'
        mapping = {'bill_a': 'option_a', 'bill_b': 'option_b',
                   'bill_c': 'option_c', 'status_quo': 'current_configuration'}
        question['criteria'] = {mapping[k]: '; '.join(f'set switch {i + 1} to {v}' for i, v in enumerate(p))
                                for k, p in neutral['policies'].items()}
        neutral['expected'] = mapping[neutral['expected']]
        for field in ('policies', 'preference_keys', 'label_to_policy_index'):
            neutral[field] = {mapping[k]: v for k, v in neutral[field].items()}
        neutral_repeat = copy.deepcopy(neutral)
        neutral_repeat.update(name=f'{seed}-neutral_repeat', arm='neutral_repeat')
        group.extend([neutral, neutral_repeat])
        cases.extend(group)
        if accepted == 120:
            break
    random.Random(20260918).shuffle(cases)
    return cases


SPEC = dict(
    name='jev-heldout-mandate-replication-v1',
    primary='120 deduplicated held-out semantic profiles; fidelity by arm; paired physical-policy disagreement for reverse/relabel/endorsement versus identical plain repeats',
    secondary='Brier score and fixed selected-probability >=0.90 error/coverage; neutral-device comparison with its own repeats',
    gates='Run exactly 840 prespecified calls; no prompt changes, early efficacy stopping, fitted calibration, or response-dependent expansion. Transport errors stop for reconciliation.',
    analysis='Report paired accuracy differences and profile-cluster bootstrap 95% intervals (10000 draws, seed 20260918). Exploratory seven-arm design, no unadjusted significance claims. Primary presentation evidence must be interpreted against identical-request disagreement.',
    limitations='Not real voter prediction; simple explicit lexicographic mandates. Neutral control changes vocabulary, consequence length, and label semantics jointly: not an isolated causal estimate of politics. No population calibration claim beyond this task distribution.'
)
