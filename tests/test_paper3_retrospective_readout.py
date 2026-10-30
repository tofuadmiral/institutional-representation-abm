from dataclasses import replace
from fractions import Fraction
from itertools import product

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design
from paper3 import retrospective_readout as readout


def term(game, arm, policy=0):
    offer = institution.Offer(policy, "")
    return institution.resolve_term(game, arm, 0, offer,
                                    (institution.Response(True, policy, ""),) * 6,
                                    offer, (True,) * 7)


def assignments(pairs):
    return {(pair.seed, stratum, arm): term(getattr(pair, stratum), arm)
            for pair in pairs for stratum in readout.STRATA for arm in institution.ARMS}


def test_retains_every_citizen_district_and_authored_action():
    profile = design.generate(93100).conflict
    value = term(profile, "binding_majority", 1)
    result = readout.first_term(profile, value.arm, value)
    assert result["term"]["requested"] == result["term"]["executed"] == (True,) * 7
    assert len(result["district_metrics"]) == 7
    assert all(len(row["citizen_menu_regret"]) == 9 for row in result["district_metrics"])
    assert result["total_welfare"] == sum(sum(row[1] for row in district)
                                          for district in profile.utilities[0])
    assert result["regret_bounds"] == (result["mean_regret"],) * 2
    assert all(1 <= rank <= 6 for row in result["citizen_menu_ranks"] for rank in row)
    with pytest.raises(ValueError, match="replay mismatch"):
        readout.first_term(profile, value.arm, replace(value, enacted=0))


def test_missingness_bounds_cover_every_possible_policy_not_status_quo_imputation():
    profile = design.generate(93101).conflict
    missing = readout.first_term(profile, "binding_sum", None)
    assert missing["mean_regret"] is None
    possibilities = [readout.first_term(profile, "binding_sum", term(profile, "binding_sum", p))
                     for p in range(6)]
    assert missing["regret_bounds"] == (min(r["mean_regret"] for r in possibilities),
                                       max(r["mean_regret"] for r in possibilities))
    for result in possibilities:
        for actor in institution.ACTORS:
            for citizen in range(9):
                low, high = missing["citizen_utility_bounds"][actor][citizen]
                assert low <= result["term"]["citizen_utilities"][actor][citizen] <= high


def test_complete_mechanical_removal_or_unchanged_policies_is_not_a_lead():
    pairs = (design.generate(93102), design.generate(93103))
    observations = assignments(pairs)
    result = readout.screen(pairs, observations, completed_episodes=set(observations), qualified=True)
    assert result["verdict"] == "no_selected_case_lead"
    assert result["mean_contrast_bounds"] == (Fraction(0), Fraction(0))
    assert not result["publication_evidence"]


def test_paired_contrast_weights_and_missing_bounds_independently():
    pairs = (design.generate(93104), design.generate(93105))
    observations = assignments(pairs)
    # This is a fabricated observation pattern, never a model pilot outcome.
    for pair in pairs:
        observations[(pair.seed, "conflict", "binding_majority")] = (
            term(pair.conflict, "binding_majority", 1))
    result = readout.screen(pairs, observations, completed_episodes=set(observations), qualified=True)
    expected = sum((readout.first_term(pair.conflict, "binding_majority",
                                     term(pair.conflict, "binding_majority", 1))["mean_regret"] -
                    readout.first_term(pair.conflict, "binding_majority",
                                     term(pair.conflict, "binding_majority", 0))["mean_regret"]
                    for pair in pairs), Fraction(0)) / 2
    assert result["mean_contrast_bounds"] == (expected, expected)
    missing_keys = [(pairs[0].seed, "aligned", "binding_sum"),
                    (pairs[1].seed, "conflict", "advisory_majority")]
    incomplete = dict(observations)
    for key in missing_keys:
        incomplete[key] = None
    bounded = readout.screen(pairs, incomplete,
                             completed_episodes=set(observations) - set(missing_keys), qualified=True)
    assert bounded["verdict"] == "incomplete"
    for policies in product(range(6), repeat=2):
        restored = dict(incomplete)
        for key, policy in zip(missing_keys, policies, strict=True):
            pair = next(pair for pair in pairs if pair.seed == key[0])
            restored[key] = term(getattr(pair, key[1]), key[2], policy)
        actual = readout.screen(pairs, restored, completed_episodes=set(restored), qualified=True)
        assert bounded["mean_contrast_bounds"][0] <= actual["mean_contrast_bounds"][0] <= (
            bounded["mean_contrast_bounds"][1])


def test_incomplete_second_terms_cannot_pass_even_with_all_primary_outcomes():
    pairs = (design.generate(93106), design.generate(93107))
    observations = assignments(pairs)
    result = readout.screen(pairs, observations, completed_episodes=set(), qualified=True)
    assert result["verdict"] == "incomplete" and result["first_terms_available"] == 16
    assert all(row["available"] for block in result["blocks"]
               for stratum in block["strata"].values() for row in stratum.values())
    result = readout.screen(pairs, observations, completed_episodes=set(observations), qualified=False)
    assert result["verdict"] == "qualification_failed"


def test_assignment_deletion_and_wrong_arm_are_rejected_not_dropped():
    pairs = (design.generate(93108), design.generate(93109))
    observations = assignments(pairs)
    incomplete = dict(observations)
    incomplete.pop(next(iter(incomplete)))
    with pytest.raises(ValueError, match="sixteen"):
        readout.screen(pairs, incomplete, completed_episodes=set(), qualified=True)
    first = next(iter(observations))
    observations[first] = replace(observations[first], arm="binding_majority")
    with pytest.raises(ValueError, match="replay mismatch"):
        readout.screen(pairs, observations, completed_episodes=set(), qualified=True)


@pytest.mark.parametrize("higher", (True, False))
def test_both_directions_can_be_discovery_leads_but_never_publication_evidence(higher):
    pairs = (design.generate(93110), design.generate(93111))
    observations = {}
    for pair in pairs:
        regrets = [readout.first_term(pair.conflict, "binding_majority",
                                      term(pair.conflict, "binding_majority", p))["mean_regret"]
                   for p in range(6)]
        low, high = min(range(6), key=regrets.__getitem__), max(range(6), key=regrets.__getitem__)
        baseline, treatment = (low, high) if higher else (high, low)
        for stratum in readout.STRATA:
            for arm in institution.ARMS:
                policy = treatment if stratum == "conflict" and arm == "binding_majority" else baseline
                observations[(pair.seed, stratum, arm)] = term(getattr(pair, stratum), arm, policy)
    result = readout.screen(pairs, observations, completed_episodes=set(observations), qualified=True)
    assert result["verdict"] == "selected_case_lead"
    assert result["direction"] == ("higher_sum_mandate_regret" if higher else "lower_sum_mandate_regret")
    assert not result["publication_evidence"]
    # A comparable target difference in aligned settings fails specificity.
    for pair in pairs:
        conflict = observations[(pair.seed, "conflict", "binding_majority")]
        observations[(pair.seed, "aligned", "binding_majority")] = term(
            pair.aligned, "binding_majority", conflict.enacted)
    result = readout.screen(pairs, observations, completed_episodes=set(observations), qualified=True)
    assert result["verdict"] == "no_selected_case_lead"
