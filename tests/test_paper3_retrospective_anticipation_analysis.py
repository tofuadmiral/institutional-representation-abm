"""Fabricated economic outcomes only; not provider or hypothesis evidence."""
from dataclasses import replace
from fractions import Fraction
from functools import cache
from itertools import product

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_analysis as analysis
from paper3 import retrospective_electorates as design
from tests.test_paper3_retrospective_joint_outcome_bounds import episode
from tests.test_paper3_retrospective_score_ledger import fixture


@cache
def assignments():
    pairs = (design.generate(4011001), design.generate(4011002))
    return tuple(dict(id=f"fabricated-{i}-{s}-{arm}", seed=pair.seed,
        seed_base=4020000 + 64 * i, stratum=s, arm=arm, game=getattr(pair, s))
        for i, pair in enumerate(pairs) for s in analysis.STRATA for arm in institution.ARMS)


def observations(direction=0, *, second=True):
    saved = {}
    for a in assignments():
        regrets = [sum((r["normalized_district_regret"] for r in
            institution.menu_metrics(a["game"], 0, p)), Fraction(0)) / 7 for p in range(6)]
        lo, hi = min(range(6), key=regrets.__getitem__), max(range(6), key=regrets.__getitem__)
        p = 0
        if a["stratum"] == "conflict" and direction:
            p = (hi if direction > 0 else lo) if a["arm"] == "binding_majority" else (
                lo if direction > 0 else hi)
        terms = episode(a["game"], a["arm"], p, 0).terms
        saved[a["id"]] = terms if second else (terms[0], None)
    return saved


def run(saved=None, items=None, *, minimum=Fraction(1, 25), attenuation=Fraction(1, 2)):
    return analysis.analyze(assignments() if items is None else items,
        observations() if saved is None else saved, minimum_effect=minimum, aligned_fraction=attenuation)


@pytest.mark.parametrize("direction", (-1, 1))
@pytest.mark.parametrize("second", (False, True))
def test_two_sided_candidate_lead_before_handover_not_full_episode_or_publication(direction, second):
    report = run(observations(direction, second=second))
    assert report["candidate_screen"]["selected_case_lead"]
    assert report["candidate_screen"]["direction"] == ("increased_distortion" if direction > 0 else "decreased_distortion")
    assert report["first_terms_complete"] == 16 and report["episodes_complete"] == (16 if second else 0)
    primary = report["readouts"]["first_term"][analysis.METRIC]
    assert primary["interaction"]["support_bounds"][0] * direction > 0
    assert primary["aligned"]["support_bounds"] == (0, 0)
    assert not report["publication_evidence"] and not report["frozen_protocol"]


def test_null_preserved_and_secondary_metrics_cannot_rescue_primary():
    report = run()
    assert report["candidate_screen"]["status"] == "no_selected_case_lead"
    assert report["readouts"]["first_term"][analysis.METRIC]["interaction"]["support_bounds"] == (0, 0)
    assert set(report["readouts"]) == {"first_term", "two_term"}
    for item in report["assignments"]:
        for horizon in ("first_term", "two_term"):
            assert len(item[horizon]["district_regret_bounds"]) == 7
            assert all(len(row) == 9 for row in item[horizon]["citizen_regret_bounds"])


@pytest.mark.parametrize("arm", institution.ARMS)
def test_local_behavior_against_direct_formula_for_all128_ballot_profiles(arm):
    game = fixture(2)
    for votes in product((False, True), repeat=7):
        term = institution.resolve_term(game, arm, 0, institution.Offer(1, "fake"),
            tuple(institution.Response(False, 0, "fake") for _ in range(6)),
            institution.Offer(1, "fake"), votes)
        result = analysis.behavior(game, arm, (term, None))
        assert len(result["ballots"]) == 7 and len(result["offers"]) == 8
        for d, row in enumerate(result["ballots"]):
            principal, score = {}, {}
            for own in (False, True):
                enacted = 1 if sum(votes) - votes[d] + own >= 4 else 0
                values = [citizen[enacted] for citizen in game.utilities[0][d]]
                keep = arm.startswith("advisory") or (sum(v >= 0 for v in values) >= 5
                    if arm.endswith("majority") else sum(values) >= 0)
                principal[own], score[own] = sum(values), sum(values) + game.office_value * keep
            assert row["first_term_district_sums"] == principal
            assert row["office_augmented_conditional_scores"] == score
            p, s = principal[True] - principal[False], score[True] - score[False]
            conflict = p * s < 0
            assert row["local_tradeoff"] is conflict
            assert row["chose_office_over_first_term_sum"] is (conflict and votes[d] == (s > 0))
            assert row["chose_first_term_sum_over_office"] is (conflict and votes[d] == (p > 0))
            if not row["locally_pivotal"]:
                assert p == s == 0 and not row["local_tradeoff"]
        assert result["local_tradeoff_opportunities"] == (
            result["chose_office_over_first_term_sum"] + result["chose_first_term_sum_over_office"])
        assert not result["publication_evidence"]


def test_missing_behavior_not_imputed_to_zero_or_to_nonpivotal_votes():
    result = analysis.behavior(fixture(2), "binding_majority", (None, None))
    assert not result["observed"] and result["ballots"] == (None,) * 7
    assert result["local_tradeoff_opportunities"] is None
    assert result["chose_office_over_first_term_sum"] is None


def test_large_collective_regret_does_not_imply_individual_ballot_tradeoff():
    game = fixture(2)
    term = institution.resolve_term(game, "binding_majority", 0, institution.Offer(1, "fake"),
        tuple(institution.Response(False, 0, "fake") for _ in range(6)),
        institution.Offer(1, "fake"), (True,) * 7)
    readout = analysis.behavior(game, "binding_majority", (term, None))
    assert readout["local_tradeoff_opportunities"] == 0
    assert readout["chose_office_over_first_term_sum"] == 0
    assert all(not row["locally_pivotal"] for row in readout["ballots"])
    assert sum(r["normalized_district_regret"] for r in
        institution.menu_metrics(game, 0, term.enacted)) > 0


@pytest.mark.parametrize("missing", range(16))
def test_every_missing_first_term_stays_explicit_no_complete_case_gate(missing):
    saved = observations(1)
    key = assignments()[missing]["id"]
    saved[key] = (None, None)
    report = run(saved)
    assert report["assigned"] == 16 and report["first_terms_complete"] == 15
    assert report["candidate_screen"]["status"] == "incomplete_first_term"
    assert not report["candidate_screen"]["selected_case_lead"]
    assert any(row["id"] == key and not row["first_term"]["complete"] for row in report["assignments"])
    assert report["readouts"]["first_term"][analysis.METRIC]["interaction"]["assigned"] == 16


def test_linear_weights_against_independent_direct_first_term_formula():
    saved = observations(1)
    report = run(saved)
    value = Fraction(0)
    for a in assignments():
        d = a["game"].utilities[0]
        p = saved[a["id"]][0].enacted
        menus = [tuple(sum(row[q] for row in district) for q in range(6)) for district in d]
        regret = sum((Fraction(max(menu) - menu[p], max(menu) - min(menu))
            if max(menu) != min(menu) else Fraction(0) for menu in menus), Fraction(0)) / 7
        sign = 1 if a["stratum"] == "conflict" else -1
        value += sign * analysis.WEIGHTS[a["arm"]] * regret / 2
    assert report["readouts"]["first_term"][analysis.METRIC]["interaction"]["support_bounds"] == (value, value)


def test_same_direction_and_threshold_are_not_optional_posthoc_rescue():
    saved = observations(1)
    reversed_frame = observations(-1)
    frame = assignments()[0]["seed"]
    saved.update({a["id"]: reversed_frame[a["id"]] for a in assignments() if a["seed"] == frame})
    assert not run(saved)["candidate_screen"]["same_direction"]
    report = run(observations(1), minimum=Fraction(1))
    assert not report["candidate_screen"]["magnitude_met"]
    assert not report["candidate_screen"]["selected_case_lead"]


@pytest.mark.parametrize("mutation", ("filter", "duplicate", "missing_arm", "game", "base", "frame_bool", "continuation"))
def test_prospective_inventory_and_matched_structure_cannot_be_changed(mutation):
    items = list(assignments())
    saved = observations()
    if mutation == "filter":
        saved.pop(items[0]["id"])
    elif mutation == "duplicate":
        items[0] = items[1]
    else:
        items[0] = dict(items[0])
        if mutation == "missing_arm":
            items[0]["arm"] = items[1]["arm"]
        elif mutation == "game":
            items[0]["game"] = items[4]["game"]
        elif mutation == "base":
            items[0]["seed_base"] += 1
        elif mutation == "frame_bool":
            items[0]["seed"] = True
        else:
            items[0]["game"] = replace(items[0]["game"], office_value=25)
    with pytest.raises(ValueError):
        run(saved, tuple(items))


@pytest.mark.parametrize("minimum,attenuation", ((.04, Fraction(1, 2)),
    (True, Fraction(1, 2)), (Fraction(0), Fraction(1, 2)),
    (Fraction(1, 25), 0.5), (Fraction(1, 25), Fraction(2))))
def test_screen_thresholds_require_explicit_exact_valid_prospective_values(minimum, attenuation):
    with pytest.raises(ValueError, match="thresholds"):
        run(minimum=minimum, attenuation=attenuation)
