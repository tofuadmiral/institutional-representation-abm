"""The pure branch controller shares decisions, not just an input profile."""

from paper3 import mandate_release_branching as branching
from paper3 import mandate_release_rival_opportunity as opportunity


def test_same_prefix_branches_to_two_realizations():
    calls = []

    def ask(actor, stage, context, shocked):
        calls.append((actor, stage, shocked))
        if stage in ("draft", "final"):
            return dict(second_project="Y1", coalition=[0, 1, 2, 3],
                        message="fixture")
        if stage == "response":
            return dict(support=True, counter_project="Y1", message="fixture")
        if stage == "consent":
            return dict(consent=True)
        if stage == "x_vote":
            return dict(vote=False)
        return dict(vote=False)

    no_shock, shock = branching.episode_pair(
        opportunity.witness(), "constituent_release", 0, ask)
    assert len(calls) == 36
    assert sum(state is None for _, _, state in calls) == 22
    assert sum(state is False for _, _, state in calls) == 7
    assert sum(state is True for _, _, state in calls) == 7
    assert no_shock.draft == shock.draft
    assert no_shock.responses == shock.responses
    assert no_shock.final == shock.final
    assert no_shock.consent == shock.consent
    assert no_shock.requested_x == shock.requested_x
    assert no_shock.x_passed == shock.x_passed
    assert not no_shock.released and shock.released == (3,)
    assert no_shock.y_passed and not shock.y_passed


def test_announced_institutions_do_not_share_prefix():
    calls = []

    def ask(actor, stage, context, shocked):
        calls.append((context["arm"], actor, stage, shocked))
        if stage in ("draft", "final"):
            return dict(second_project="Y1", coalition=[], message="none")
        if stage == "response":
            return dict(support=False, counter_project="Y2", message="none")
        if stage == "consent":
            return dict(consent=False)
        return dict(vote=False)

    game = opportunity.witness()
    for arm in ("irrevocable", "constituent_release"):
        branching.episode_pair(game, arm, 0, ask)
    assert len(calls) == 72
    assert {arm for arm, _, _, _ in calls} == {
        "irrevocable", "constituent_release"
    }
    assert sum(state is None for _, _, _, state in calls) == 44
