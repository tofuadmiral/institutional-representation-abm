from fractions import Fraction

from paper3 import mandate_release_gonogo_analysis as analysis
from paper3 import mandate_release_gonogo_design as design
from paper3 import mandate_release_branching as branching
from paper3 import mandate_release_institution as institution


def fabricated(*, effect=False, active=True):
    outcomes = {}
    for case in design.cases():
        for arm in institution.ARMS:
            use_y1 = bool(effect and case.stratum == "pivotal"
                          and arm == "constituent_release")
            project = "Y1" if use_y1 else "Y2"
            coalition = design.Y1_SUPPORT if use_y1 else design.Y2_SUPPORT[case.family]

            def ask(actor, stage, context, shocked):
                if stage in ("draft", "final"):
                    return dict(second_project=project,
                                coalition=list(coalition) if active else [], message="test")
                if stage == "response":
                    return dict(support=True, counter_project=project, message="test")
                if stage == "consent":
                    return dict(consent=True)
                return dict(vote=False)

            pair = branching.episode_pair(case.game, arm, 0, ask)
            for shock, episode in zip((False, True), pair, strict=True):
                outcomes[(case.case_id, arm, shock)] = episode
    return outcomes


def test_behavioral_screen_requires_actual_pre_shock_change_and_citizen_effect():
    report = analysis.screen(fabricated(effect=True))
    assert report["verdict"] == "go_independent_validation_only"
    assert report["pivotal_mean_activation_delta_bounds"] == ["1", "1"]
    assert report["pivotal_citizen_effect_cases"] == 3
    assert report["stable_active_controls_lower_bound"] == 3


def test_no_agreements_and_mechanical_only_changes_do_not_pass():
    assert analysis.screen(fabricated(active=False))["verdict"] == "no_go_agreements_rare"
    assert analysis.screen(fabricated())["verdict"] == "no_go_no_consistent_behavioral_lead"


def test_missing_pair_is_bounded_and_can_never_be_dropped_for_a_go():
    outcomes = fabricated(effect=True)
    missing_case = design.cases()[0]
    for arm in institution.ARMS:
        for shock in (False, True):
            del outcomes[(missing_case.case_id, arm, shock)]
    report = analysis.screen(outcomes)
    assert report["pivotal_mean_activation_delta_bounds"] == ["1/3", "1"]
    assert report["verdict"] == "inconclusive_coverage_stop"
    assert len(report["cases"]) == 6
    bounds = report["cases"][0]["expected_citizen_delta_bounds"]
    assert len(bounds) == 7 and all(len(district) == 9 for district in bounds)
    assert any(Fraction(lo) < Fraction(hi) for district in bounds for lo, hi in district)
