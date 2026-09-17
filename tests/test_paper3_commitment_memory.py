import pytest

from paper3.commitment_memory import contract_state, parse, profile, project_sequence, second_vote


def history(signatures=None, votes=None):
    signatures = signatures if signatures is not None else [True] * 4 + [False] * 3
    votes = votes if votes is not None else [True] * 4 + [False] * 3
    return [dict(type="draft_offer", offer_id="draft-1", package=3, first="B"),
            dict(type="final_offer", offer_id="final-2", package=0, first="A"),
            dict(type="ratification", offer_id="final-2", signatures=signatures),
            dict(type="first_vote", project="A0", votes=votes, passed=sum(votes) >= 4)]


def test_active_and_superseded():
    state = contract_state(history())
    assert state["status"] == "second_vote_due"
    assert state["signers"] == [0, 1, 2, 3]
    assert state["superseded_offer_ids"] == ["draft-1"]
    assert project_sequence(history()) == ("A0", "B0")


def test_four_votes_not_enough_if_signer_defects():
    assert contract_state(history(votes=[False, True, True, True, True, False, False]))["status"] == "condition_failed"


def test_insufficient_signatures():
    assert contract_state(history(signatures=[True] * 3 + [False] * 4))["status"] == "not_ratified"


def test_release_must_have_every_signer():
    events = history() + [dict(type="mutual_release", offer_id="final-2", consenting_signers=[0, 1, 2, 3])]
    assert contract_state(events)["status"] == "released"
    events[-1]["consenting_signers"] = [0, 1, 2]
    with pytest.raises(ValueError):
        contract_state(events)


def test_wrong_contract_cannot_release():
    events = history() + [dict(type="mutual_release", offer_id="draft-1", consenting_signers=[0, 1, 2, 3])]
    assert contract_state(events)["status"] == "second_vote_due"


@pytest.mark.parametrize("raw", ['{"vote":1}', '{"vote":"true"}', '{"vote":true,"extra":0}', 'yes'])
def test_no_response_repairs(raw):
    with pytest.raises(ValueError):
        parse(raw, {"vote": bool})


def test_profile_symmetry():
    a, b = profile(7), profile(7, True)
    for actor in range(7):
        assert a.utilities[actor]["A0"] == b.utilities[actor]["B0"]
        assert a.utilities[actor]["B1"] == b.utilities[actor]["A1"]


class AllNo:
    def generate(self, *args, **kwargs):
        return '{"obligation_due":false,"vote":false}'


def test_no_votes_are_overridden_and_payoffs_are_actual():
    result = second_vote(AllNo(), profile(7), history(), ledger=False, release=False)
    assert result["due_count"] == 4
    assert result["breaches"] == 4
    assert result["obligation_errors"] == 4
    assert not result["second_passed"]
    assert result["realized_utility"][0] == profile(7).utilities[0]["A0"]


def test_release_negative_control_has_no_obligations():
    result = second_vote(AllNo(), profile(7), history(), ledger=True, release=True)
    assert result["due_count"] == result["breaches"] == result["obligation_errors"] == 0
