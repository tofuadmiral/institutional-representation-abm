import copy
from dataclasses import asdict

import pytest

from analysis.paper3_incentive_audit import audit_episode, audit_utilities
from paper3.commitment_memory import profile


def test_completed_profile_outside_options_and_signers():
    p = profile(1301)
    result = audit_utilities(p.utilities)
    packages = result["packages"]
    assert packages[0]["strict_beneficiaries"] == list(range(6))
    assert len(packages[0]["improving_coalitions"]) == 22  # C(6,4)+C(6,5)+C(6,6)
    assert packages[1]["incremental_payoffs"] == [11, 8, 11, -5, -2, -4, -6]
    assert packages[1]["improving_coalitions"] == []
    assert packages[2]["improving_coalitions"] == []
    assert packages[3]["incremental_payoffs"] == [0] * 7
    assert packages[3]["improving_coalitions"] == []  # Indifference is not strict improvement.
    for package in packages[1:3]:
        assert package["positive_vs_zero_coalition_count"] == 22
        assert package["positive_vs_zero_with_outside_option_loser_count"] == 22
    assert all(row["harmed_nonmembers"] == [6]
               for row in packages[0]["outsiders_harmed_by_each_improving_coalition"])
    episode = dict(status="completed", profile=asdict(p), events=[
        dict(type="final_offer", offer_id="final-2", package=1, first="B"),
        dict(type="ratification", offer_id="final-2", signatures=[True, True, True, False, True, False, False])],
        realized_utility={i: v for i, v in enumerate([-1, -1, -2, 8, 9, 8, 2])})
    assert audit_episode(episode)["observed_offer"]["signers_losing_relative_to_benchmark_if_fully_delivered"] == [
        dict(actor=4, independent_payoff=9, full_delivery_payoff=7, difference=-2)]


def test_generator_support_structure_is_not_seed_diversity():
    # Regression examples supplement, rather than prove, the analytic sign-range argument.
    for seed in (0, 7, 10, 503, 1301):
        for reverse in (False, True):
            packages = audit_utilities(profile(seed, reverse).utilities)["packages"]
            assert [len(p["strict_beneficiaries"]) for p in packages] == [6, 3, 3, 0]
            assert [len(p["improving_coalitions"]) for p in packages] == [22, 0, 0, 0]


def test_payoff_changes_change_audit_not_hardcoded_taxonomy():
    utilities = copy.deepcopy(profile(1301).utilities)
    utilities[6] = dict(A0=1, A1=1, B0=1, B1=1)
    for package in audit_utilities(utilities)["packages"]:
        assert package["incremental_payoffs"] == [0] * 7
        assert not package["improving_coalitions"]


def test_reject_incomplete_and_malformed_inputs():
    with pytest.raises(ValueError, match="completed"):
        audit_episode(dict(status="failed"))
    with pytest.raises(ValueError, match="seven"):
        audit_utilities({0: dict(A0=1, A1=2, B0=1, B1=2)})
    utilities = copy.deepcopy(profile(1301).utilities)
    utilities[0]["A0"] = True
    with pytest.raises(ValueError, match="integer"):
        audit_utilities(utilities)
