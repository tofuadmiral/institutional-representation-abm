import copy
from dataclasses import asdict

import pytest

from analysis.paper3_episode_readout import readout
from paper3.commitment_memory import profile


def episode():
    p = profile(1301)
    votes = [True, True, False, True, True, True, True]
    return dict(status="completed", profile=asdict(p), events=[
        dict(type="draft_offer", offer_id="draft-1", package=0, first="A"),
        dict(type="final_offer", offer_id="final-2", package=1, first="B"),
        dict(type="ratification", offer_id="final-2", signatures=[True, True, True, False, True, False, False]),
        dict(type="first_vote", project="B1", votes=votes, passed=True)],
        actions=[dict(actor=i, obligation_due=False, vote=i in (0, 1, 2)) for i in range(7)],
        second_passed=False, realized_utility={i: row["B1"] for i, row in p.utilities.items()})


def test_rule_pivotality_can_exist_without_first_bill_pivotality():
    value = episode()
    saved = copy.deepcopy(value)
    report = readout(value)
    assert value == saved
    assert report["first_round_promise_breaches"] == [2]
    actor2 = report["first_ballot_flips"][2]
    assert not actor2["policy_pivotal"] and actor2["rule_state_pivotal"]
    assert actor2["flipped_rule_status"] == "second_vote_due"
    assert report["rule_status"] == "condition_failed"
    assert report["second_round_state_report_errors"] == []
    assert report["actual_total"] == 23
    assert report["second_ballot_flips"][4]["own_utility_change_if_only_this_vote_flipped"] == -2


def test_no_payoffs_for_failure_and_reject_inconsistent_saved_outcomes():
    assert not readout(dict(status="failed"))["outcomes_available"]
    value = episode()
    value["realized_utility"][0] += 1
    with pytest.raises(ValueError, match="payoff mismatch"):
        readout(value)
    value = episode()
    value["actions"] = value["actions"][:-1]
    with pytest.raises(ValueError, match="seven actual ballots"):
        readout(value)
