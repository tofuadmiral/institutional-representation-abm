"""Prospective finite benchmark frame; no model outputs used in selection."""
from functools import lru_cache
from fractions import Fraction

from paper3 import agenda_benchmarks as bench
from paper3 import agenda_disclosure as late
from paper3.agenda_disclosure_benchmarks import disclosure_benchmark
from paper3.agenda_objective_benchmarks import objective_benchmarks


def predictions(profile):
    theory = disclosure_benchmark(profile)
    objectives = objective_benchmarks(profile)
    ids = bench.policy_ids(profile)
    u = profile['utilities'][profile['leader']]
    viable = {p: u[bench.continuation(profile, p)] for p in ids}
    regret = {p: sum((Fraction(row[p]-min(row.values()), max(row.values())-min(row.values()))
                     for row in profile['losses'].values()), Fraction(0)) / 7 for p in ids}
    alternatives = dict(
        immediate_own_best=[p for p in ids if u[p] == max(u.values())],
        ratification_only_own_best=[p for p in ids if viable[p] == max(viable.values())],
        proposal_regret_best=[p for p in ids if regret[p] == min(regret.values())])
    return dict(theory=theory, objectives=objectives, alternatives=alternatives,
                early_B_separates_myopic=not set(theory['early_own_best_proposals']['B']).intersection(
                    alternatives['ratification_only_own_best']),
                early_B_separates_group=objectives['own_vs_group_disjoint']['B'])


@lru_cache(maxsize=1)
def frame():
    selection = late.select_profiles(start=1005000, per_stratum=6)
    # Interleave strata so exhaustion/transport attrition is not concentrated in
    # one stratum just because all positive cases were submitted first.
    seeds = [s for pair in zip(selection['positive'], selection['zero_control']) for s in pair]
    return dict(selection=selection, seeds=seeds,
                profiles=[bench.generated_profile(s) for s in seeds],
                predictions={str(s): predictions(bench.generated_profile(s)) for s in seeds},
                inference_scope='12 fixed theory-stratified benchmark profiles, not a population sample. '
                'One sampling seed/profile, correlated branches. Held-out validation, not a powered generalization study.',
                precision='Even 6/6 successes give a two-sided 95% exact-binomial lower bound of '
                '0.025**(1/6)=0.541 (under independent Bernoulli assumptions). Those assumptions are not '
                'guaranteed here. Do not claim high population reliability or add profiles until significance.',
                analysis='Preserve the original relative-leader-advantage and mean-regret timing interactions. '
                'Prospective additional primary: normalized ex-ante leader information benefit and signed/absolute '
                'discrepancy from scripted value. Report each profile and each stratum; no population p-value. '
                'Secondary: all principal utilities, worst regret, tie-retaining own/group/myopic compatibility, '
                'enacted continuation fit, errors, tokens and costs. Missing cells get finite-menu bounds; '
                'no complete-case-only headline. Zero scripted value does not imply zero group interaction.',
                stopping='Fixed 12 profiles, no replacements or sample extension. Any failed/unfinished profile '
                'blocks an unqualified complete-frame validation claim. Compare alternatives only in prespecified '
                'disjoint-set cases. All six positive early-B cases separate myopic choice; only one positive case '
                'separates continuation-aware group choice, so this does not establish a general motive distinction. '
                'Model/label/seed robustness and portable replay remain publication requirements.')


def schedule(index):
    block = index // 2
    early = [('early', a) for a in ('DB' if block % 2 == 0 else 'BD')]
    order = early + [('late', 'DB' if block % 2 == 0 else 'BD')]
    rotation = block % 3
    return order[rotation:] + order[:rotation]
