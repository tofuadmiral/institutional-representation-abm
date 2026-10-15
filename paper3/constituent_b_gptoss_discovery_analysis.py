"""Seven-profile constituent B discovery readout with explicit missingness.

Two seeded realizations of constructed archetypes are the profile units; 30
calls per episode and paired requested seeds do not make 630 independent trials.
"""
from __future__ import annotations

from itertools import combinations

from paper3 import coalition_contracts as game
from paper3 import constituent_contract_bridge as bridge


PAIRS = tuple(combinations(game.ARMS, 2))


def _menu(prepared):
    return [bridge.evaluate_passed(prepared, list(passed))
            for passed in game.all_outcomes()]


def _bound(prepared, left, right, menu):
    """Finite, deliberately broad bounds over unobserved enactments."""
    options_left = [left] if left is not None else menu
    options_right = [right] if right is not None else menu
    deltas, harmed, districts = [], [], {f"r{i}": [] for i in game.ACTORS}
    for a in options_left:
        for b in options_right:
            changes = {citizen_id: b["citizens"][citizen_id]["relative_utility"]
                       - a["citizens"][citizen_id]["relative_utility"]
                       for citizen_id in a["citizens"]}
            if set(changes) != set(b["citizens"]):
                raise ValueError("citizen menu changed")
            deltas.append(sum(changes.values()))
            harmed.append(sum(value < 0 for value in changes.values()))
            for district_id, values in districts.items():
                values.append(b["districts"][district_id]["total_relative_utility"]
                              - a["districts"][district_id]["total_relative_utility"])
    return dict(total_utility_change=[min(deltas), max(deltas)],
                citizens_harmed=[min(harmed), max(harmed)],
                district_utility_change={key: [min(values), max(values)]
                                         for key, values in districts.items()},
                possible_outcome_pairs=len(options_left) * len(options_right))


def _requested_ballots(events):
    votes = [event for event in events if event["type"] in ("first_vote", "second_vote")]
    if len(votes) != 2:
        raise ValueError("completed episode must have two votes")
    return [dict(project=vote["project"], requested=vote["requested"],
                 executed=vote["executed"], changed_ballots=vote["changed_ballots"])
            for vote in votes]


def fixed_continuation_ballot_checks(prepared, arm, events):
    """Flip one requested ballot with others and later requests held fixed.

    This is a local, ex-post counterfactual, not a feasible unilateral policy
    optimum, causal agent treatment effect, equilibrium, or motive inference.
    In the first round, a different result can alter whether the second-round
    promise is due; the unchanged second requests are re-resolved accordingly.
    """
    profile = prepared["contract_profile"]
    actual = game.readout(profile, arm, events)
    vote_indices = {event["type"]: index for index, event in enumerate(events)
                    if event["type"] in ("first_vote", "second_vote")}
    if set(vote_indices) != {"first_vote", "second_vote"}:
        raise ValueError("complete vote history required")
    first_index, second_index = vote_indices["first_vote"], vote_indices["second_vote"]
    if first_index >= second_index:
        raise ValueError("vote order changed")
    # Independently reproduce the mechanical records before counterfactuals.
    first = events[first_index]
    second = events[second_index]
    if (game.resolve_vote(events[:first_index], arm, first["requested"], "first_vote") != first
            or game.resolve_vote(events[:second_index], arm, second["requested"],
                                 "second_vote") != second):
        raise ValueError("saved vote does not match announced institution")
    checks = []
    for stage, index in (("first_vote", first_index), ("second_vote", second_index)):
        vote = events[index]
        for actor in game.ACTORS:
            alternative_requests = list(vote["requested"])
            alternative_requests[actor] = not alternative_requests[actor]
            alternative_vote = game.resolve_vote(events[:index], arm,
                                                 alternative_requests, stage)
            if stage == "first_vote":
                alternative_second = game.resolve_vote(
                    [*events[:first_index], alternative_vote], arm,
                    second["requested"], "second_vote")
                alternative_votes = (alternative_vote, alternative_second)
            else:
                alternative_votes = (first, alternative_vote)
            alternative_passed = [event["project"] for event in alternative_votes
                                  if event["passed"]]
            delta = (game.utility_vector(profile, alternative_passed)[actor]
                     - actual["utility"][actor])
            checks.append(dict(stage=stage, actor=actor,
                               requested=vote["requested"][actor],
                               executed=vote["executed"][actor],
                               request_was_overridden=actor in vote["changed_ballots"],
                               alternative_passed=alternative_passed,
                               alternative_own_district_utility_change=delta,
                               local_missed_gain=max(delta, 0)))
    return checks


def readout(profiles, records):
    """Retain complete and incomplete cells; never silently drop a profile."""
    expected = {(item["prepared"]["contract_profile"]["id"], arm)
                for item in profiles for arm in game.ARMS}
    if set(records) != expected or len(profiles) != 7:
        raise ValueError("seven-profile by three-arm assignment inventory required")
    output = []
    complete_episodes = 0
    for item in profiles:
        prepared = item["prepared"]
        profile_id = prepared["contract_profile"]["id"]
        menu = _menu(prepared)
        arms, comparisons = {}, []
        for arm in game.ARMS:
            saved = records[(profile_id, arm)]
            status = saved.get("status")
            if status not in ("completed", "failed", "not_started", "instrument_error"):
                raise ValueError("unknown episode status")
            if status == "completed":
                expected_outcome = game.readout(prepared["contract_profile"], arm,
                                                saved["events"])
                expected_citizens = bridge.evaluate_passed(prepared,
                                                            expected_outcome["passed"])
                if (saved["outcome"] != expected_outcome or
                        saved["citizen_outcome"] != expected_citizens or
                        saved["calls"] != 30):
                    raise ValueError("saved completed episode disagrees with game")
                arms[arm] = dict(status=status, draft_terms=expected_outcome["draft_terms"],
                                 final_terms=expected_outcome["final_terms"],
                                 contract_activated=expected_outcome["contract_activated"],
                                 passed=expected_outcome["passed"],
                                 district_utility=expected_outcome["utility"],
                                 unconstrained_district_outcome_regret=
                                 expected_outcome["regret"],
                                 citizen_outcome=expected_citizens,
                                 ballots=_requested_ballots(saved["events"]),
                                 fixed_continuation_ballot_checks=
                                 fixed_continuation_ballot_checks(
                                     prepared, arm, saved["events"]),
                                 enforcement_changes=expected_outcome["enforcement_changes"])
                complete_episodes += 1
            else:
                arms[arm] = dict(status=status, error=saved.get("error"))
        for left_arm, right_arm in PAIRS:
            left, right = arms[left_arm], arms[right_arm]
            left_outcome = (bridge.evaluate_passed(prepared, left["passed"])
                            if left["status"] == "completed" else None)
            right_outcome = (bridge.evaluate_passed(prepared, right["passed"])
                             if right["status"] == "completed" else None)
            comparison = dict(arms=[left_arm, right_arm],
                              completed=left_outcome is not None and right_outcome is not None,
                              finite_bounds=_bound(prepared, left_outcome, right_outcome, menu))
            if comparison["completed"]:
                comparison.update(
                    before_vote_draft_changed=left["draft_terms"] != right["draft_terms"],
                    before_vote_final_changed=left["final_terms"] != right["final_terms"],
                    ballot_projects_match=all(
                        a["project"] == b["project"]
                        for a, b in zip(left["ballots"], right["ballots"], strict=True)),
                    requested_ballot_patterns_differ=any(
                        a["requested"] != b["requested"]
                        for a, b in zip(left["ballots"], right["ballots"], strict=True)),
                    citizen_comparison=bridge.compare_passed(prepared, left["passed"],
                                                             right["passed"]))
            comparisons.append(comparison)
        output.append(dict(profile_id=profile_id, family=item["family"],
                           arms=arms, pairwise=comparisons,
                           equal_person_first_choices=item["citizen_first_choices"]))
    return dict(profiles=output, assigned_episodes=len(expected),
                completed_episodes=complete_episodes,
                assigned_profile_pairs=len(profiles) * len(PAIRS),
                completed_profile_pairs=sum(x["completed"] for item in output
                                            for x in item["pairwise"]),
                limitation="Seven distinct utility structures from two seeded realizations of theory-constructed archetypes; requested seeds are paired across arms but not guaranteed matched stochastic draws. No population or model-family inference. Global outcome regret is not behavioral disobedience; fixed-continuation ballot checks are ex-post local diagnostics, not strategic/motive proof. Mechanical enforcement is separate from pre-vote behavior.")
