"""Exact candidate games and scripted/arithmetic baselines only, no models."""
from dataclasses import replace
from fractions import Fraction

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_baselines as baseline
from paper3 import retrospective_anticipation_design as design


@pytest.mark.parametrize("index", (0, 1))
def test_fixed_fresh_pair_has_no_forced_first_term_interaction_despite_tenure_changes(index):
    report = baseline.check_pair(design.pairs()[index])
    assert report["scripted_interaction"] == 0 and report["first_term_choices_unforced"]
    assert report["mechanical_retention_vectors_differ"]
    assert report["zero_bonus_conditional_incentive_difference"] == 0
    assert len(report["baseline_assignments"]) == 8
    assert report["actual_model_calls"] == 0 and not report["publication_evidence"]


@pytest.mark.parametrize("index", (0, 1))
@pytest.mark.parametrize("stratum", ("aligned", "conflict"))
def test_script_requested_votes_and_proposals_follow_direct_current_sum_not_office(index, stratum):
    game = getattr(design.pairs()[index], stratum)
    scripts = [baseline.mandate_only(game, arm) for arm in institution.ARMS]
    assert all(s["requested_choices"] == scripts[0]["requested_choices"] for s in scripts)
    for script in scripts:
        for slot in script["requested_choices"]:
            t, actor = slot["term"], slot["actor"]
            sums = [sum(row[p] for row in game.utilities[t][actor]) for p in range(6)]
            if slot["stage"] in ("draft", "final"):
                assert sums[slot["action"]["policy"]] == max(sums)
            elif slot["stage"] == "vote":
                final = script["episode"].terms[t].final.policy
                assert slot["action"]["vote"] is (sums[final] > sums[0])
        assert all(term.requested == term.executed for term in script["episode"].terms)


def test_same_tables_zero_bonus_is_arithmetic_placebo_not_new_generated_easy_cases():
    pair = design.pairs()[0]
    for stratum in ("aligned", "conflict"):
        game = getattr(pair, stratum)
        zero = replace(game, office_value=0)
        assert zero.utilities == game.utilities and zero.chairs == game.chairs
        for p in range(6):
            for d in range(7):
                values = []
                for arm in institution.ARMS:
                    scores = institution.conditional_ballot_scores(zero, arm, d, p,
                        (True,) * 3 + (False,) * 3)
                    values.append(scores[True] - scores[False])
                assert len(set(values)) == 1
    assert baseline.check_pair(pair)["scripted_interaction"] == Fraction(0)
