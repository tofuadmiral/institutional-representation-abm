from fractions import Fraction
import pytest

from analysis.paper3_disclosure_readout import readout
from paper3.agenda_benchmarks import generated_profile


def test_synthetic_equal_cells_have_zero_information_loss():
    p = generated_profile(1004007)
    result = readout(p, {"early-D": "q", "early-B": "q", "late": "q"},
                     {"early": {"D": "q", "B": "q"}, "late": {"D": "q", "B": "q"}})
    assert result["leader_expected_utility_loss_exact"] == "0"
    assert not result["leader_loss_matches_scripted_information_value"]
    assert all(Fraction(v["raw_exact"]) == 0 for v in result["observed_early_minus_late_expected_utility"].values())


def test_utility_loss_is_half_the_sum_of_branch_differences():
    p = generated_profile(1004007)
    outcomes = {"early": {"D": "p6", "B": "p4"}, "late": {"D": "p6", "B": "p3"}}
    result = readout(p, {"early-D": "p6", "early-B": "p4", "late": "p6"}, outcomes)
    assert result["leader_expected_utility_loss_exact"] == "33/2"
    assert result["leader_loss_matches_scripted_information_value"]
    assert all(all(v.values()) for v in result["enacted_matches_scripted_continuation_given_observed_lock"].values())
    assert not result["compatibility"]["early-B"]["alternatives"]["ratification_only_own_best"]


def test_incomplete_profile_not_imputed():
    with pytest.raises(ValueError, match="complete"):
        readout(generated_profile(1004007), {}, {})
