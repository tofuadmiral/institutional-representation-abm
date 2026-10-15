"""Approved two-fixture, two-seed mechanism diagnostic; not population confirmation."""
from functools import lru_cache

from paper3.agenda_benchmarks import generated_profile
from paper3.agenda_weak_preferences import certificate

PROFILE_SEEDS = (1006576, 1006006)


def inference_seed(index):
    if type(index) is not int or not 0 <= index < 4:
        raise ValueError('block index must be 0..3')
    # The initially suggested 29xxxx range overlapped the old validation.
    return 301000 + 1000 * (index // 2) + 100 * (index % 2)


def schedule(index):
    inference_seed(index)
    replicate = index // 2
    arms = 'DB' if replicate == 0 else 'BD'
    conditions = [('early', a) for a in arms]
    # Move the late condition without reversing the relative order of the early
    # arms (rotating all three conditions would defeat counterbalancing).
    conditions.insert(2 - index % 3, ('late', arms))
    return conditions


@lru_cache(maxsize=1)
def frame():
    seeds = list(PROFILE_SEEDS) * 2
    predictions = {str(s): certificate(generated_profile(s)) for s in PROFILE_SEEDS}
    assert predictions['1006576']['stratum'] == 'positive_separating'
    assert predictions['1006006']['stratum'] == 'zero_control'
    return dict(seeds=seeds, profiles=[generated_profile(s) for s in seeds], predictions=predictions,
        blocks=[dict(index=i, profile_seed=s, profile_index=i % 2, replicate=i // 2,
                     inference_seed=inference_seed(i)) for i, s in enumerate(seeds)],
        selection='Adaptive THEORY design after prior pilots: fixed 1006000..1006999 scan, '
                  'first/only positive separating weak-preference outcome-identified case and first zero control. '
                  'No LLM answers used in selection. All 1000 rows retained in feasibility artifacts.',
        inference_scope='Two selected base profiles, each with two inference seeds, NOT four independent profiles. '
                        'Late D/B share a prefix. Requested seeds do not ensure provider determinism. '
                        'Conditional sincere-voting/sponsor-response benchmark, not equilibrium or motive identification.',
        analysis='Per block: normalized early-information benefit with all-assigned finite-menu missing bounds; '
                 'original authority-by-timing contrasts in mean/worst regret, relative leader advantage and all '
                 'principal utilities. D/B/lottery set-valued own/group/myopic lock compatibility and normalized '
                 'benchmark planning regret, then tie-aware sponsor/selector/card departures, outcomes, passage, '
                 'status-quo losers, all principal metrics and usage/cost/failures. No complete-case-only headline.',
        directional_prediction='1006576: early D p2->p2, early B and both late branches ->q; '
                               'all information benefit is D-driven, 9 raw or 3/38 normalized. '
                               'Own-best B/lottery sets {q,p1,p3,p4,p5,p7}; group-best B {p2,p6}; '
                               'myopic p2. 1006006: p3 in all conditions, zero information benefit.',
        stopping='Fresh 8/8 gate, safety/cap stop, or all four blocks terminal; no replacement, restart or '
                 'automatic successor. All four complete with clean audits needed for unqualified paired readout. '
                 'Both seeds must reproduce distinctions for tiny-fixture seed stability. Even perfect fit '
                 'is not paper-ready; later independent family/label crossing needs separate approval.')
