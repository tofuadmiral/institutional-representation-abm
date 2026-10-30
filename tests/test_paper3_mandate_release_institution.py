"""Controller tests do not count as agent behavior or a scientific pilot."""

import pytest

from paper3 import mandate_release_institution as institution
from paper3.mandate_release_rival_opportunity import witness


def scripted_ask(project="Y1", coalition=(0, 1, 2, 3)):
    seen = []

    def ask(actor, stage, context):
        seen.append((actor, stage, context))
        if stage in ("draft", "final"):
            return dict(second_project=project, coalition=list(coalition), message="offer")
        if stage == "response":
            return dict(support=True, counter_project=project, message="support")
        if stage == "consent":
            return dict(consent=True)
        return dict(vote=False)

    return ask, seen


def test_shock_release_changes_executed_second_ballot_not_requested_ballot():
    game = witness()
    ask, seen = scripted_ask()
    locked = institution.episode(game, "irrevocable", True, 0, ask)
    release = institution.episode(game, "constituent_release", True, 0, ask)
    assert len(seen) == 58
    assert locked.active and release.active
    assert locked.requested_x == release.requested_x == (False,) * 7
    assert locked.executed_x == release.executed_x == (True,) * 4 + (False,) * 3
    assert locked.x_passed and release.x_passed
    assert locked.requested_y == release.requested_y == (False,) * 7
    assert locked.executed_y == (True,) * 4 + (False,) * 3
    assert release.executed_y == (True,) * 3 + (False,) * 4
    assert locked.y_passed and not release.y_passed
    assert locked.released == () and release.released == (3,)
    assert release.release_ballots == ((3, 6),)
    assert locked.district_utilities[3] == -12
    assert release.district_utilities[3] == -5
    assert tuple(map(sum, release.citizen_utilities)) == release.district_utilities


def test_no_shock_and_rival_project_controls_have_identical_enactment():
    game = witness()
    ask, _ = scripted_ask()
    locked = institution.episode(game, "irrevocable", False, 0, ask)
    release = institution.episode(game, "constituent_release", False, 0, ask)
    assert locked.executed_y == release.executed_y
    assert locked.district_utilities == release.district_utilities
    assert release.release_ballots == ()

    ask_y2, _ = scripted_ask("Y2", (0, 1, 2, 4))
    locked_y2 = institution.episode(game, "irrevocable", True, 0, ask_y2)
    released_y2 = institution.episode(game, "constituent_release", True, 0, ask_y2)
    assert locked_y2.executed_y == released_y2.executed_y
    assert locked_y2.district_utilities == released_y2.district_utilities
    assert released_y2.release_ballots == ()


def test_inactive_contract_never_forces_ballots_or_hides_its_failure():
    game = witness()

    def ask(actor, stage, context):
        if stage in ("draft", "final"):
            return dict(second_project="Y1", coalition=[0, 1, 2, 3], message="offer")
        if stage == "response":
            return dict(support=False, counter_project="Y2", message="decline")
        if stage == "consent":
            return dict(consent=actor != 3)
        return dict(vote=False)

    for arm in institution.ARMS:
        outcome = institution.episode(game, arm, True, 0, ask)
        assert not outcome.active
        assert not outcome.x_passed and not outcome.y_passed
        assert outcome.executed_x == outcome.requested_x
        assert outcome.executed_y == outcome.requested_y
        assert outcome.district_utilities == (0,) * 7


def test_pre_shock_context_has_both_possible_tables_but_not_realized_state():
    game = witness()
    ask, seen = scripted_ask()
    institution.episode(game, "constituent_release", True, 0, ask)
    assert len(seen) == 29
    for _, stage, context in seen:
        assert context["before"] == game.before
        assert context["possible_after_shock"] == game.after
        assert context["shock_probability"] == "1/4"
        if stage == "y_vote":
            assert context["shock_realized"] is True
            assert context["after"] == game.after
        else:
            assert "shock_realized" not in context
            assert "after" not in context


def test_exact_action_shapes_are_enforced_without_repair():
    with pytest.raises(ValueError):
        institution.parse_offer(dict(second_project="Y1", coalition=[0, 0, 1, 2],
                                     message="duplicate"))
    with pytest.raises(ValueError):
        institution.parse_response(dict(support=1, counter_project="Y2", message="wrong"))
    with pytest.raises(ValueError):
        institution.parse_boolean(dict(vote=True, reason="extra"), "vote")
