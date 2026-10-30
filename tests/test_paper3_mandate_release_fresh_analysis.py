"""The frozen-intended screen is two-sided and not mechanical."""

import pytest

from paper3 import mandate_release_fresh_analysis as analysis
from paper3 import mandate_release_fresh_design as design
from paper3 import mandate_release_institution as institution


def fabricated(mode):
    outcomes = {}
    for case in design.cases():
        for arm in institution.ARMS:
            active = case.stratum == "pivotal" and (
                (mode == "release" and arm == "constituent_release")
                or (mode == "irrevocable" and arm == "irrevocable")
                or mode == "both"
            )
            offer = institution.parse_offer(dict(
                second_project="Y1", coalition=[0, 1, 2, 3] if active else [],
                message="fixture"))
            responses = tuple(dict(support=True, counter_project="Y1",
                                   message="fixture") for _ in range(6))
            for shocked in (False, True):
                outcomes[(case.case_id, arm, shocked)] = institution.resolve(
                    case.game, arm, shocked, 0, offer, responses, offer,
                    (True,) * 7, (False,) * 7, (False,) * 7)
    return outcomes


def test_two_sided_behavioral_screen_and_controls():
    assert analysis.screen(fabricated("release"))["classification"] == (
        "selected_case_release_behavioral_lead")
    assert analysis.screen(fabricated("irrevocable"))["classification"] == (
        "selected_case_irrevocable_behavioral_lead")
    assert analysis.screen(fabricated("both"))["classification"] == (
        "no_prespecified_behavioral_lead")


def test_mechanical_release_only_cannot_count_as_behavioral_lead():
    result = analysis.screen(fabricated("both"))
    assert any(row["shock"]["locked_y_passed"] !=
               row["shock"]["release_y_passed"] for row in result["rows"]
               if row["stratum"] == "pivotal")
    assert result["classification"] == "no_prespecified_behavioral_lead"


def test_nonpivotal_agreement_switch_blocks_lead_even_without_y1_pivot_change():
    outcomes = fabricated("release")
    case = next(case for case in design.cases() if case.stratum == "nonpivotal")
    final = institution.parse_offer(dict(
        second_project="Y2", coalition=[0, 1, 4, 5], message="fixture"))
    for shocked in (False, True):
        old = outcomes[(case.case_id, "constituent_release", shocked)]
        outcomes[(case.case_id, "constituent_release", shocked)] = institution.resolve(
            case.game, old.arm, shocked, old.proposer, old.draft,
            old.responses, final, old.consent, old.requested_x,
            old.requested_y)
    result = analysis.screen(outcomes)
    assert result["classification"] == "nonpivotal_control_changed"
    assert result["control_changed"] == 1
    assert result["rows"][8]["release_only"] is False
    assert result["rows"][8]["agreement_changed"] is True


def test_nonpivotal_inactive_offer_label_is_not_an_agreement_change():
    outcomes = fabricated("release")
    case = next(case for case in design.cases() if case.stratum == "nonpivotal")
    final = institution.parse_offer(dict(
        second_project="Y2", coalition=[], message="fixture"))
    for shocked in (False, True):
        old = outcomes[(case.case_id, "constituent_release", shocked)]
        outcomes[(case.case_id, "constituent_release", shocked)] = institution.resolve(
            case.game, old.arm, shocked, old.proposer, old.draft,
            old.responses, final, old.consent, old.requested_x,
            old.requested_y)
    result = analysis.screen(outcomes)
    assert result["classification"] == "selected_case_release_behavioral_lead"
    assert result["rows"][8]["agreement_changed"] is False


def test_menu_regret_retains_each_principal_and_citizen():
    result = analysis.screen(fabricated("release"))
    for row in result["rows"]:
        for arm in institution.ARMS:
            for state in row["arm_state_outcomes"][arm]:
                district = state["district_menu_regret"]
                citizen = state["citizen_menu_regret"]
                assert len(district) == len(citizen) == 7
                assert all(value >= 0 for value in district)
                assert all(len(group) == 9 and all(value >= 0 for value in group)
                           for group in citizen)
                assert state["total_district_menu_regret"] == sum(district)
                assert state["total_citizen_menu_regret"] == sum(
                    value for group in citizen for value in group)


def test_missing_game_is_retained_not_conditioned_away():
    outcomes = fabricated("release")
    case = design.cases()[0]
    outcomes.pop((case.case_id, "constituent_release", True))
    result = analysis.screen(outcomes)
    assert result["classification"] == "incomplete"
    assert result["missing_games"] == 1
    assert result["rows"][0]["complete"] is False
    assert result["rows"][0]["arm_state_outcomes"]["irrevocable"][0] is not None
    assert result["rows"][0]["arm_state_outcomes"]["constituent_release"][1] is None


def test_wrong_shock_state_and_divergent_prefix_rejected():
    outcomes = fabricated("both")
    case = design.cases()[0]
    wrong = outcomes[(case.case_id, "irrevocable", True)]
    outcomes[(case.case_id, "irrevocable", False)] = wrong
    with pytest.raises(ValueError, match="arm or state"):
        analysis.screen(outcomes)
