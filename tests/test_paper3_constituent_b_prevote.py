import pytest

from analysis import paper3_constituent_b_prevote as prevote
from paper3 import (coalition_contracts, constituent_b_design,
                    constituent_b_qwen_design, constituent_contract_bridge)


def _prepared():
    return constituent_b_design.frame(672100)[0]["prepared"]


def _offer(a="A0", b="B0", first="A", coalition=None):
    return dict(projects=dict(A=a, B=b), first=first,
                coalition=[0, 1, 2, 3] if coalition is None else coalition)


def test_proposal_score_is_not_an_enacted_outcome():
    prepared = _prepared()
    proposal = prevote.score_offer(prepared, _offer())
    assert proposal["full_delivery_policy"] == "A0+B0"
    assert proposal["total_citizen_relative_utility"] == sum(
        proposal["district_relative_utilities"].values())
    assert len(proposal["district_relative_utilities"]) == 7
    assert 0 <= proposal["citizens_worse_than_status_quo"] <= 63


def test_same_policy_different_terms_do_not_fabricate_citizen_effect():
    comparison = prevote.compare_offers(
        _prepared(), _offer(), _offer(first="B", coalition=[3, 4, 5, 6]))
    assert comparison["terms_changed"]
    assert not comparison["full_delivery_policy_changed"]
    assert comparison["total_citizen_utility_change"] == 0
    assert (comparison["citizens_gain"], comparison["citizens_lose"],
            comparison["citizens_tie"]) == (0, 0, 63)


def test_changed_proposal_retains_every_citizen_and_conserves_utility():
    comparison = prevote.compare_offers(_prepared(), _offer(), _offer(a="A1", b="B1"))
    assert comparison["full_delivery_policy_changed"]
    assert sum(comparison[key] for key in
               ("citizens_gain", "citizens_lose", "citizens_tie")) == 63
    assert comparison["total_citizen_utility_change"] == comparison[
        "citizen_comparison"]["overall"]["total_utility_change"]


def test_invalid_proposed_project_rejected():
    with pytest.raises(ValueError):
        prevote.score_offer(_prepared(), _offer(a="A7"))


def test_every_discovery_profile_policy_and_pair_conserves_citizen_utility():
    """Check the complete finite menu without reading any model outcomes."""
    menu = coalition_contracts.all_outcomes()
    assert len(menu) == 9
    for row in constituent_b_qwen_design.profiles():
        prepared = row["prepared"]
        for before in menu:
            scored = constituent_contract_bridge.evaluate_passed(prepared, before)
            assert len(scored["citizens"]) == 63
            for after in menu:
                compared = constituent_contract_bridge.compare_passed(
                    prepared, before, after)
                assert len(compared["citizens"]) == 63
