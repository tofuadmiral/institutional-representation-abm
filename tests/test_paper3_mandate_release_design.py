"""Offline profile filters, with no LLM responses or effect estimates."""

from paper3 import mandate_release_design as design
from paper3 import mandate_release_institution as institution
from paper3 import mandate_release_rival_opportunity as opportunity


def test_profile_inventory_is_fixed_and_has_all_predeclared_strata():
    rows = design.cases()
    assert len(rows) == 10
    assert len({case.case_id for case in rows}) == 10
    assert [case.stratum for case in rows] == [
        "pivotal", "pivotal", "pivotal", "pivotal",
        "low_risk", "low_risk", "high_risk", "high_risk",
        "nonpivotal", "nonpivotal",
    ]
    assert all(case.draw_index <= 20_000 for case in rows)
    assert design.cases() == rows


def test_every_profile_has_rival_coalitions_and_citizen_majority_conflict():
    for case in design.cases():
        game = case.game
        opportunity.validate(game)
        assert len(game.before) == len(game.after) == 7
        assert sum(map(len, game.before)) == 63
        assert (0, 1, 2, 3) in opportunity.acceptable_coalitions(game, "Y1")
        assert (0, 1, 2, 4) in opportunity.acceptable_coalitions(game, "Y2")
        assert (0, 1, 2, 5) in opportunity.acceptable_coalitions(game, "Y2")
        for actor in (0, 1):
            assert (opportunity.bundle_total(game.before, actor, "Y1") >
                    opportunity.bundle_total(game.before, actor, "Y2"))
            assert sum(row[2] > row[1] for row in game.before[actor]) == 5
        assert all(sum(opportunity.district_total(game.before, actor, project) > 0
                       for actor in opportunity.ACTORS) <= 3
                   for project in opportunity.INDEX)


def test_structural_risk_signs_and_nonpivotal_control():
    for case in design.cases():
        game = case.game
        coalition = (0, 1, 2, 3)
        no_shock = opportunity.scripted_outcome(
            game, "Y1", coalition, shocked=False, release_right=False)
        locked = opportunity.scripted_outcome(
            game, "Y1", coalition, shocked=True, release_right=False)
        released = opportunity.scripted_outcome(
            game, "Y1", coalition, shocked=True, release_right=True)
        assert locked.second_passed
        assert released.released_members == (3,)
        p = game.shock_probability
        locked_value = ((1 - p) * no_shock.district_utilities[3]
                        + p * locked.district_utilities[3])
        release_value = ((1 - p) * no_shock.district_utilities[3]
                         + p * released.district_utilities[3])
        if case.stratum == "pivotal":
            assert not released.second_passed
            assert locked_value < 0 < release_value
        elif case.stratum == "low_risk":
            assert not released.second_passed
            assert 0 < locked_value < release_value
        elif case.stratum == "high_risk":
            assert not released.second_passed
            assert locked_value < release_value < 0
        else:
            assert released.second_passed
            assert locked_value == release_value


def _fabricated_episode(case, arm, project):
    coalition = [0, 1, 2, 3] if project == "Y1" else [0, 1, 2, 4]

    def ask(actor, stage, context):
        if stage in ("draft", "final"):
            return dict(second_project=project, coalition=coalition, message="test")
        if stage == "response":
            return dict(support=True, counter_project=project, message="test")
        if stage == "consent":
            return dict(consent=True)
        return dict(vote=False)

    return institution.episode(case.game, arm, case.shocked, 0, ask)


def _fabricated_outcomes(pattern):
    result = {}
    for case in design.cases():
        for arm in institution.ARMS:
            project = "Y2"
            if case.stratum == "pivotal":
                if pattern == "release" and arm == "constituent_release":
                    project = "Y1"
                if pattern == "irrevocable" and arm == "irrevocable":
                    project = "Y1"
            result[(case.case_id, arm)] = _fabricated_episode(case, arm, project)
    return result


def test_predeclared_screen_is_two_sided_and_never_counts_mechanical_only():
    release = design.screen(_fabricated_outcomes("release"))
    assert release["classification"] == "selected_case_release_behavioral_lead"
    assert release["pivotal_release_only"] == 4
    assert release["pivotal_irrevocable_only"] == 0
    irrevocable = design.screen(_fabricated_outcomes("irrevocable"))
    assert irrevocable["classification"] == "selected_case_irrevocable_behavioral_lead"
    assert irrevocable["pivotal_irrevocable_only"] == 4
    null = design.screen(_fabricated_outcomes("null"))
    assert null["classification"] == "no_prespecified_behavioral_lead"


def test_missing_and_nonpivotal_changes_cannot_be_positive_leads():
    outcomes = _fabricated_outcomes("release")
    outcomes[("release-00", "constituent_release")] = None
    assert design.screen(outcomes)["classification"] == "incomplete_or_control_missing"
    outcomes = _fabricated_outcomes("release")
    case = design.cases()[8]
    outcomes[(case.case_id, "constituent_release")] = _fabricated_episode(
        case, "constituent_release", "Y1")
    assert design.screen(outcomes)["classification"] == "nonpivotal_control_changed"
