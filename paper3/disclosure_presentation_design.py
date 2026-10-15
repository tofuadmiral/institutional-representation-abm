"""Approved same-batch presentation diagnostic: one game, four paired seeds.

The single balanced form-order draw was made before inference, not selected for
a favorable outcome. Form changes include policy IDs and sorted-key positions.
Four seed pairs on one selected game cannot establish population reliability.
"""
from functools import lru_cache
import random
from paper3 import disclosure_identification_design as original
from paper3.disclosure_relabel_design import POLICY_MAPPING, INVERSE_MAPPING
from paper3.agenda_invariance import transform_profile
from paper3.agenda_benchmarks import generated_profile
from paper3.agenda_weak_preferences import certificate

PROFILE_SEED = 1006576
ORDER_RANDOMIZATION_SEED = 7119844896683085794
WAVE_SIZE = 4
PAIR_COUNT = 4
FORMS = ('original', 'mapped')


def first_forms():
    forms = ['original', 'original', 'mapped', 'mapped']
    random.Random(ORDER_RANDOMIZATION_SEED).shuffle(forms)
    return forms


def assignment(index):
    if type(index) is not int or not 0 <= index < 8:
        raise ValueError('block index must be 0..7')
    wave, pair = divmod(index, WAVE_SIZE)
    first = first_forms()[pair]
    form = first if wave == 0 else next(f for f in FORMS if f != first)
    return dict(index=index, pair=pair, wave=wave, form=form,
                profile_seed=PROFILE_SEED, inference_seed=311000+1000*pair)


def inference_seed(index):
    return assignment(index)['inference_seed']


def schedule(index):
    # Same four condition schedules as the original experiment, paired across
    # forms. Each form sees two early D-before-B and two B-before-D schedules.
    return original.schedule(assignment(index)['pair'])


def inverse_mapping(index):
    return INVERSE_MAPPING if assignment(index)['form'] == 'mapped' else {p:p for p in POLICY_MAPPING}


@lru_cache(maxsize=1)
def frame():
    source = generated_profile(PROFILE_SEED)
    forms = dict(original=source, mapped=transform_profile(source, policy_mapping=POLICY_MAPPING))
    predictions = {f:certificate(p) for f,p in forms.items()}
    assert all(p['identified'] and p['stratum']=='positive_separating' for p in predictions.values())
    assert all(p['predictions']['normalized_information_value_exact']=='3/38' for p in predictions.values())
    blocks = [assignment(i) for i in range(8)]
    return dict(seeds=[PROFILE_SEED]*8, profiles=[forms[b['form']] for b in blocks],
        blocks=blocks, predictions=predictions, policy_mapping=POLICY_MAPPING,
        randomization=dict(seed=ORDER_RANDOMIZATION_SEED, first_forms=first_forms(),
            procedure='One random 64-bit seed drawn once before model calls; Random(seed).shuffle on two original and two mapped labels. '
                      'Two waves; wave 2 begins only after all admitted wave-1 workers finish. Reverse each pair in wave 2.'),
        selection='Previously selected separating game 1006576 only. No new game search, control profiles or permutations.',
        inference_scope='One selected game, four requested seed pairs, two presentation forms in the same batch. '
                        'Randomized balanced form order reduces calendar-order confounding, but does not freeze provider weights. '
                        'Requested seeds are not guaranteed common random draws. Labels and sorted-key positions change together. '
                        'Descriptive diagnostic, not a powered population test, equivalence test or publication result.',
        analysis='Primary: mapped-minus-original normalized early-information benefit for every assigned seed pair, '
                 'then all-pair mean finite-menu bounds. Report all eight blocks, not complete cases only. '
                 'Per form retain own/group/myopic lock sets, exact conditional planning regret, '
                 'benchmark outcome/sponsor fit, pairwise/leader/card departures, all-principal metrics, '
                 'authority-by-timing interactions, usage, charges/reservations and missingness. '
                 'Count complete benchmark-reproducing blocks per form; report distinct observed benefits within each form. '
                 'Original failure is evidence against stable original-form reproduction, not automatically a mapping effect. '
                 'A consistent paired sign is descriptive only; no p-value or general fragility claim.',
        benchmark_reproduction='A complete block must have all three own-compatible locks, B/lottery locks outside '
                 'group/myopic sets, original-label outcomes early-D=p2 and other cells=q, benefit exactly 3/38. '
                 'All four blocks of a form are required to say it reproduced at all four sampled seeds. '
                 'Separate integrity and completion from these scientific descriptors.',
        stopping='Fresh gate 8/8 required once. 736 intended calls, at most 1472 attempts with one billing-certified '
                 'identical transport reissue per decision. Shared $2 cap including pending/uncertified reservations. '
                 'Stop on gate failure, safety/cost stop or all eight blocks terminal. No content repairs, seed '
                 'extensions, replacements, interrupted restart, model switch or automatic successor.')
