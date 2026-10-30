"""Offline engineering/counterfactual checks, not LLM experimental evidence."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from itertools import product

import pytest

from paper3 import retrospective_accountability as game


def fixture(aligned=False, office_value=30):
    values = (6,) * 5 + (-2,) * 4 if aligned else (-2,) * 5 + (8,) * 4
    district = tuple((0, value, 1) for value in values)
    # Term-two welfare remains part of the initial incumbent's score even
    # after removal. It contains no third-term tenure incentive.
    future = tuple((0, 2, -1) for _ in range(9))
    return game.Game("engineering-only", ((district,) * 7, (future,) * 7), (0, 3), office_value)


def scripted(policy=1, vote=True, mutate=False):
    seen = []

    def ask(actor, identity, term, stage, context, index):
        seen.append((actor, identity, term, stage, deepcopy(context), index))
        if mutate:
            context.clear()
        if stage in ("draft", "final"):
            return dict(policy=policy, message="offer")
        if stage == "response":
            return dict(support=True, counter_policy=policy, message="response")
        return dict(vote=vote)

    return ask, seen


def test_binding_removal_changes_actual_identity_not_policy_ballot():
    ask, seen = scripted()
    episode = game.episode(fixture(), "binding_majority", ask)
    first, second = episode.terms
    assert episode.calls == len(seen) == 30
    assert first.requested == first.executed == (True,) * 7
    assert second.requested == second.executed == (True,) * 7
    assert first.tenure_retained == (False,) * 7
    assert second.occupants == tuple(map(game.successor, game.ACTORS))
    assert all(identity == game.successor(actor) for actor, identity, term, *_ in seen if term == 1)
    assert all(identity == game.incumbent(actor) for actor, identity, term, *_ in seen if term == 0)
    assert episode.cumulative_district_utilities == (40,) * 7
    assert episode.initial_incumbent_scores == (40,) * 7
    assert episode.successor_scores == (18,) * 7


@pytest.mark.parametrize("arm", game.ARMS)
def test_terminal_term_has_no_new_retention_or_office_reward(arm):
    ask, _ = scripted()
    outcome = game.episode(fixture(), arm, ask)
    first, second = outcome.terms
    assert second.tenure_retained is None
    assert second.next_occupants == second.occupants
    expected_bonus = 0 if arm == "binding_majority" else 30
    assert outcome.initial_incumbent_scores == (40 + expected_bonus,) * 7
    assert first.tenure_retained == (expected_bonus > 0,) * 7


def test_same_assessments_across_authority_and_criterion():
    outcomes = {}
    contexts = {}
    for arm in game.ARMS:
        ask, seen = scripted()
        outcomes[arm] = game.episode(fixture(), arm, ask)
        contexts[arm] = seen
    original = outcomes["advisory_majority"].terms[0]
    for arm, outcome in outcomes.items():
        first = outcome.terms[0]
        assert first.assessments == original.assessments
        assert first.citizen_utilities == original.citizen_utilities
        for a, b in zip(contexts["advisory_majority"][:15], contexts[arm][:15], strict=True):
            left, right = dict(a[4]), dict(b[4])
            left.pop("arm")
            right.pop("arm")
            assert left == right
    assert not original.assessments[0].majority_passed
    assert original.assessments[0].sum_passed
    assert outcomes["binding_sum"].terms[1].occupants == tuple(map(game.incumbent, game.ACTORS))


def test_sealed_response_and_vote_contexts_do_not_leak_prior_actions():
    ask, seen = scripted(mutate=True)
    game.episode(fixture(), "binding_majority", ask)
    for term in (0, 1):
        responses = [row[4] for row in seen if row[2:4] == (term, "response")]
        ballots = [row[4] for row in seen if row[2:4] == (term, "vote")]
        assert len(responses) == 6 and all(row == responses[0] for row in responses)
        assert len(ballots) == 7 and all(row == ballots[0] for row in ballots)
        assert all("responses" not in row for row in responses)
        assert all("requested" not in row for row in ballots)
        assert len(ballots[0]["history"]) == term
    assert seen[15][4]["history"][0]["enacted"] == 1


def test_four_yes_threshold_exhaustively_never_forces_a_policy_vote():
    profile = fixture()
    offer = game.Offer(1, "")
    responses = (game.Response(True, 1, ""),) * 6
    for arm, votes in product(game.ARMS, product((False, True), repeat=7)):
        term = game.resolve_term(profile, arm, 0, offer, responses, offer, votes)
        assert term.executed == votes
        assert term.proposal_passed == (sum(votes) >= 4)
        assert term.enacted == int(sum(votes) >= 4)
        assert term.assessments[0].district_sum == (22 if sum(votes) >= 4 else 0)


def test_ties_neutral_citizens_and_status_quo_retain_incumbent():
    assert game.assess((0,) * 9).majority_passed
    assert game.assess((0,) * 9).sum_passed
    # Five nonnegative citizens count as a majority even with zero values.
    assert game.assess((0,) * 5 + (-1,) * 4).majority_passed
    assert not game.assess((0,) * 5 + (-1,) * 4).sum_passed
    ask, _ = scripted(vote=False)
    outcome = game.episode(fixture(), "binding_majority", ask)
    assert outcome.terms[0].enacted == 0
    assert outcome.terms[0].tenure_retained == (True,) * 7


def test_menu_regret_is_exact_bounded_and_not_office_utility():
    profile = fixture()
    for policy in (0, 1, 2):
        metrics = game.menu_metrics(profile, 0, policy)
        assert all(0 <= row["normalized_district_regret"] <= 1 for row in metrics)
        assert all(len(row["citizen_utilities"]) == len(row["citizen_menu_regret"]) == 9
                   for row in metrics)
    assert game.menu_metrics(profile, 0, 2)[0]["normalized_district_regret"] == Fraction(13, 22)
    assert game.menu_metrics(profile, 0, 1)[0]["normalized_district_regret"] == 0
    zero = tuple((0, 0) for _ in range(9))
    constant = game.Game("constant", ((zero,) * 7,) * 2, (0, 1), 100)
    assert all(row["normalized_district_regret"] == 0 for row in game.menu_metrics(constant, 0, 0))


def test_exact_conditional_incentive_conflict_and_nonpivotal_ties():
    peers = (True,) * 3 + (False,) * 3
    for arm in game.ARMS:
        values = game.conditional_ballot_scores(fixture(), arm, 0, 1, peers)
        assert values[False] == 30
        assert values[True] == (22 if arm == "binding_majority" else 52)
        assert game.conditional_ballot_scores(fixture(aligned=True), arm, 0, 1, peers) == {
            False: 30, True: 52}
        assert game.conditional_ballot_scores(fixture(office_value=0), arm, 0, 1, peers) == {
            False: 0, True: 22}
        nonpivotal = game.conditional_ballot_scores(fixture(), arm, 0, 1, (True,) * 6)
        assert nonpivotal[False] == nonpivotal[True]


def test_payoff_preserving_policy_and_citizen_relabeling():
    profile = fixture()
    changed = replace(profile, utilities=tuple(tuple(
        tuple((row[0], row[2], row[1]) for row in reversed(district))
        for district in table) for table in profile.utilities))
    for actor in game.ACTORS:
        for arm in game.ARMS:
            peers = (True,) * 3 + (False,) * 3
            assert game.conditional_ballot_scores(profile, arm, actor, 1, peers) == (
                game.conditional_ballot_scores(changed, arm, actor, 2, peers))
    assert game.menu_metrics(profile, 0, 1)[0]["normalized_district_regret"] == (
        game.menu_metrics(changed, 0, 2)[0]["normalized_district_regret"])


@pytest.mark.parametrize("action", [dict(policy=True, message=""), dict(policy=5, message=""),
                                      dict(policy=1, message="a" * 129),
                                      dict(policy=1, message="", reason="extra")])
def test_invalid_offers_are_not_repaired(action):
    with pytest.raises(ValueError):
        game.parse_offer(fixture(), action)


def test_invalid_ballots_profiles_and_missing_predecessor():
    for action in (dict(vote=1), dict(vote=True, reason="extra")):
        with pytest.raises(ValueError):
            game.parse_vote(action)
    for profile in (replace(fixture(), office_value=True), replace(fixture(), chairs=(0, 0)),
                    replace(fixture(), utilities=fixture().utilities[:1])):
        with pytest.raises(ValueError):
            game.validate(profile)
    offer = game.Offer(1, "")
    responses = (game.Response(True, 1, ""),) * 6
    with pytest.raises(ValueError, match="predecessor"):
        game.resolve_term(fixture(), "binding_sum", 1, offer, responses, offer, (True,) * 7)


def test_invalid_action_stops_without_a_substitute_or_hidden_second_term():
    seen = []

    def ask(actor, identity, term, stage, context, index):
        seen.append(index)
        if index == 1:
            return dict(support=1, counter_policy=1, message="invalid")
        return dict(policy=1, message="")

    with pytest.raises(ValueError, match="support boolean"):
        game.episode(fixture(), "binding_sum", ask)
    assert seen == [0, 1]


def test_mixed_removal_preserves_district_seats_and_chair_identity():
    profile = fixture()
    aligned = fixture(aligned=True)
    districts = tuple(aligned.utilities[0][actor] if actor % 2 else
                      profile.utilities[0][actor] for actor in game.ACTORS)
    profile = replace(profile, utilities=(districts, profile.utilities[1]), chairs=(1, 2))
    ask, seen = scripted()
    outcome = game.episode(profile, "binding_majority", ask)
    expected = tuple(game.incumbent(actor) if actor % 2 else game.successor(actor)
                     for actor in game.ACTORS)
    assert outcome.terms[0].tenure_retained == tuple(bool(actor % 2) for actor in game.ACTORS)
    assert outcome.terms[1].occupants == expected
    assert seen[15][0:4] == (2, game.successor(2), 1, "draft")
    assert all(identity == expected[actor] for actor, identity, term, *_ in seen if term == 1)
    assert outcome.initial_incumbent_scores == tuple(70 if actor % 2 else 40
                                                    for actor in game.ACTORS)
    assert outcome.successor_scores == tuple(None if actor % 2 else 18
                                            for actor in game.ACTORS)


def test_predecessor_cannot_forge_handover_ballots_or_payoffs():
    profile = fixture()
    ask, _ = scripted()
    first = game.episode(profile, "binding_majority", ask).terms[0]
    for previous in (replace(first, next_occupants=tuple(map(game.incumbent, game.ACTORS))),
                     replace(first, executed=(False,) * 7),
                     replace(first, citizen_utilities=((0,) * 9,) * 7)):
        with pytest.raises(ValueError, match="exact first-term replay"):
            game.resolve_term(profile, first.arm, 1, first.draft, first.responses,
                              first.final, first.requested, previous)
    changed = replace(profile, utilities=fixture(aligned=True).utilities)
    with pytest.raises(ValueError, match="exact first-term replay"):
        game.resolve_term(changed, first.arm, 1, first.draft, first.responses,
                          first.final, first.requested, first)
