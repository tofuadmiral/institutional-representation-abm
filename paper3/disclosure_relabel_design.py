"""One approved policy-label robustness form; two games, two paired seeds.

This is a sequential-batch presentation check, not independent population evidence.
Policy IDs and consequently some sorted-key positions change. Semantic catalog
row order, roles, preferences, menus and institutional opportunities do not.
"""
from functools import lru_cache
from paper3 import disclosure_identification_design as original
from paper3.agenda_invariance import transform_profile
from paper3.agenda_weak_preferences import certificate

POLICY_MAPPING = dict(q='q', p1='p4', p2='p7', p3='p1', p4='p6',
                      p5='p2', p6='p3', p7='p5')
INVERSE_MAPPING = {new: old for old, new in POLICY_MAPPING.items()}
inference_seed = original.inference_seed
schedule = original.schedule


@lru_cache(maxsize=1)
def frame():
    source = original.frame()
    profiles = [transform_profile(p, policy_mapping=POLICY_MAPPING) for p in source['profiles']]
    predictions = {str(seed): certificate(profile)
                   for seed, profile in zip(source['seeds'], profiles)}
    for seed in original.PROFILE_SEEDS:
        before = source['predictions'][str(seed)]
        after = predictions[str(seed)]
        assert after['identified'] and after['stratum'] == before['stratum']
        a, b = before['predictions'], after['predictions']
        assert a['normalized_information_value_exact'] == b['normalized_information_value_exact']
        for field in ('own_best', 'group_best'):
            for condition, choices in a[field].items():
                assert {POLICY_MAPPING[p] for p in choices} == set(b[field][condition])
        assert {POLICY_MAPPING[p] for p in a['ratification_only_best']} == set(b['ratification_only_best'])
        for condition, values in a['own_payoffs_exact'].items():
            assert {POLICY_MAPPING[p]: v for p, v in values.items()} == b['own_payoffs_exact'][condition]
        for arm, values in before['sponsor_best_outcomes'].items():
            assert {POLICY_MAPPING[p]: sorted(POLICY_MAPPING[o] for o in outcomes)
                    for p, outcomes in values.items()} == after['sponsor_best_outcomes'][arm]
    return dict(seeds=source['seeds'], profiles=profiles, predictions=predictions,
        blocks=source['blocks'], policy_mapping=POLICY_MAPPING, inverse_mapping=INVERSE_MAPPING,
        selection='Same two previously selected games; one fixed nonidentity p1..p7 permutation, q fixed. '
                  'No extra profiles, permutations, prompt repairs or model selection after answers.',
        inference_scope='Two base games, two paired requested seeds; sequential batch relative to original form. '
                        'Seeds do not ensure provider determinism. Labels and sorted-key positions may both change. '
                        'No contemporaneous randomized label effect, hidden-motive, equilibrium or population claim.',
        analysis=source['analysis'] + ' Report outcomes and lock sets in new and original policy labels. '
                 'Fixed success gate: all four blocks complete with clean audits, own-compatible locks, '
                 'positive early-B/lottery locks outside specified group/myopic sets, '
                 'positive early D maps to p2 and all other outcomes q, controls map to p3 throughout, '
                 'information benefits exactly 3/38 and zero in both paired repeats. '
                 'Wrong actions, incomplete runs and fragility are retained, never replaced.',
        stopping='364 intended calls; one identical certified transport reissue at most per decision (728 attempts). '
                 'Inherit the completed original 8/8 gate only with identical native request/provider settings. '
                 'No fresh gate inference in this allocation; changed settings require a new user decision. '
                 'Stop at all four blocks terminal or safety/cost stop. No restart or automatic successor.',
        directional_prediction='Mapped positive early D p7; all other positive outcomes q. '
                               'Control p1 in every cell. Same 3/38 versus zero benefits; entirely D-driven.')

