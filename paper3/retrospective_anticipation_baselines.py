"""Offline rule/choice separation baselines, not LLM or equilibrium evidence.

Identical first-term choices cannot produce a fidelity interaction through
post-processing/removal alone. A deliberately myopic SUM-only script tests that
claim on the exact candidate games. Its behavior is not rational full-horizon
bargaining, a predictive oracle or a substitute for experimental assignments.
"""
from dataclasses import replace
from fractions import Fraction

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_analysis as analysis
from paper3 import retrospective_electorates as design


def mandate_only(game, arm):
    """Current-term SUM offers, majority of sincere positive-gain ballots.

Each chair drafts/finalizes its own highest-SUM option (lower-ID tie break).
Nonchairs counter with their own highest-SUM option and support a draft with
positive current SUM gain over rejection; ballots follow that same criterion.
This ignores office bonus, announced assessment and future strategic effects.
It need not maximize any collective objective or solve the two-term game.
"""
    requested = []
    def ask(actor, identity, term, stage, context, index):
        sums = tuple(sum(row[p] for row in game.utilities[term][actor])
                     for p in range(len(game.utilities[term][actor][0])))
        preferred = min(range(len(sums)), key=lambda p: (-sums[p], p))
        if stage in ("draft", "final"):
            action = dict(policy=preferred, message="deterministic current-SUM baseline")
        elif stage == "response":
            action = dict(support=sums[context["draft"]["policy"]] > sums[0],
                          counter_policy=preferred, message="deterministic current-SUM baseline")
        else:
            action = dict(vote=sums[context["final"]["policy"]] > sums[0])
        requested.append(dict(index=index, actor=actor, term=term, stage=stage, action=action))
        return action
    result = institution.episode(game, arm, ask)
    return dict(episode=result, requested_choices=tuple(requested), actual_model_calls=0,
        publication_evidence=False,
        limitations="Myopic sincere SUM baseline, not a two-term solution, calibrated agent or efficacy claim.")


def check_pair(pair):
    """Prove no forced fidelity interaction; retain mechanical tenure differences.

Also verify the conditional own-ballot office incentive disappears when bonus=0
on the SAME citizen tables, not regenerated easier electorates. This is algebra,
NOT behavioral placebo evidence, and adds no model arm or call authorization.
"""
    institution.validate(pair.aligned)
    institution.validate(pair.conflict)
    institution.require(design.district_sums(pair.aligned.utilities[0]) ==
                        design.district_sums(pair.conflict.utilities[0]), "matched first-term SUM profiles")
    rows = []
    for stratum in analysis.STRATA:
        game = getattr(pair, stratum)
        scripts = [(arm, mandate_only(game, arm)) for arm in institution.ARMS]
        first_choices = scripts[0][1]["requested_choices"][:15]
        enacted = scripts[0][1]["episode"].terms[0].enacted
        for arm, result in scripts:
            institution.require(result["requested_choices"][:15] == first_choices and
                result["episode"].terms[0].enacted == enacted,
                "assessment/removal mechanically changed an authored first-term decision")
            term = result["episode"].terms[0]
            for actor, vote in enumerate(term.requested):
                institution.require(vote == term.executed[actor], "ballot override in baseline")
            rows.append(dict(stratum=stratum, arm=arm, enacted_first=enacted,
                first_term_mean_district_regret=sum((r["normalized_district_regret"] for r in
                    institution.menu_metrics(game, 0, enacted)), Fraction(0)) / 7,
                retained=term.tenure_retained, original_incumbent_scores=result["episode"].initial_incumbent_scores))
        zero = replace(game, office_value=0)
        policy_differences = []
        for policy in range(len(game.utilities[0][0][0])):
            for actor in institution.ACTORS:
                expected = sum(row[policy] - row[0] for row in game.utilities[0][actor])
                deltas = []
                for arm in institution.ARMS:
                    scores = institution.conditional_ballot_scores(zero, arm, actor, policy,
                        (True,) * 3 + (False,) * 3)
                    deltas.append(scores[True] - scores[False])
                institution.require(all(delta == expected for delta in deltas),
                                    "zero-office conditional payoff differs across institutions")
                policy_differences.append(dict(policy=policy, actor=actor, delta=expected))
        # Keep the deterministic outcome zero separate from unknown LLM behavior.
        institution.require(len(policy_differences) == 7 * len(game.utilities[0][0][0]), "all conditional menus")
    interaction = sum((analysis.WEIGHTS[r["arm"]] * (1 if r["stratum"] == "conflict" else -1) *
        r["first_term_mean_district_regret"] for r in rows), Fraction(0))
    institution.require(interaction == 0, "forced first-term fidelity interaction")
    return dict(seed=pair.seed, baseline_assignments=tuple(rows), scripted_interaction=interaction,
        first_term_choices_unforced=True, zero_bonus_conditional_incentive_difference=0,
        mechanical_retention_vectors_differ=len({r["retained"] for r in rows}) > 1,
        actual_model_calls=0, publication_evidence=False,
        limitation="Baseline/algebra checks only. Zero-bonus behavioral robustness remains an unrun "
                    "publication check; labels and future strategic responses are not identified here.")
