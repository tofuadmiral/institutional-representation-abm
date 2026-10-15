"""Independent engine replay of prospective diagnostic facts; no hosted calls."""
from copy import deepcopy
import json

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_score_ledger_qualification as q
from paper3 import retrospective_score_ledger as ledger
from paper3 import retrospective_serialization_contract as contract
from tests.test_paper3_retrospective_serialization_contract import stream


def _replay(case, own=True):
    assumptions = json.loads(case["messages"][1]["content"])["hypothetical_assumptions"]
    actor = case["actor"]
    first = 1 if case["arm"].endswith("majority") else 2
    peers = dict(zip([a for a in range(7) if a != actor],
                     assumptions.get("other_six_ballots", [True] * 6), strict=True))
    tested_term = case["term"]
    future = assumptions.get("second_term_enacted_policy", 1)
    def ask(a, identity, term, stage, context, index):
        policy = first if term == 0 else future
        if stage in ("draft", "final"):
            return dict(policy=policy, message="offline")
        if stage == "response":
            return dict(support=False, counter_policy=policy, message="offline")
        if term == tested_term and "other_six_ballots" in assumptions:
            return dict(vote=own if a == actor else peers[a])
        return dict(vote=a < 4)
    return institution.episode(case["game"], case["arm"], ask)


@pytest.mark.parametrize("case", [c for c in q.cases() if c["kind"] == "fact"],
                         ids=lambda c: c["id"])
def test_expected_facts_against_full_economic_controller_not_ledger(case):
    actor = case["actor"]
    expected = case["expected"]
    if q.presence.terminal(case):
        episode = _replay(case)
        assert expected == dict(acting_identity=episode.terms[1].occupants[actor],
            original_incumbent_score=episode.initial_incumbent_scores[actor],
            successor_score=episode.successor_scores[actor], third_term_bonus=0)
        answer = q.presence.encode(expected)
    else:
        for own, suffix in ((True, "yes"), (False, "no")):
            episode = _replay(case, own)
            assert expected["enacted_policy_if_" + suffix] == episode.terms[case["term"]].enacted
            assert expected["original_score_if_" + suffix] == episode.initial_incumbent_scores[actor]
            if case["term"] == 0:
                assert expected["next_identity_if_" + suffix] == episode.terms[0].next_occupants[actor]
            else:
                score = episode.successor_scores[actor]
                assert expected["acting_score_if_" + suffix] == (
                    episode.initial_incumbent_scores[actor] if score is None else score)
        answer = expected
    result = q.score(case, stream(json.dumps(answer)))
    assert result["valid_action"] and result["exact"]


def test_prespecified_coverage_and_no_future_credit_omission():
    facts = [c for c in q.cases() if c["kind"] == "fact"]
    terminals = [c for c in facts if q.presence.terminal(c)]
    assert len(facts) == 12 and len(terminals) == 4
    assert sum(c["expected"]["successor_score"] is not None for c in terminals) == 2
    assert {c["expected"]["successor_score"] > 0 for c in terminals
            if c["expected"]["successor_score"] is not None} == {True, False}
    first = [c for c in facts if c["term"] == 0]
    assert {sum(row[json.loads(c["messages"][1]["content"])["hypothetical_assumptions"]
                   ["second_term_enacted_policy"]] for row in c["game"].utilities[1][c["actor"]])
            for c in first} == {-17, -13, 0, 13}
    for c in facts:
        if not q.presence.terminal(c):
            peers = json.loads(c["messages"][1]["content"])["hypothetical_assumptions"]["other_six_ballots"]
            assert sum(peers) in (2, 3, 4)
    for c in terminals:
        if c["expected"]["successor_score"] is not None:
            data = json.loads(c["messages"][1]["content"])
            past = data["score_ledger"]["districts"][f"district_{c['actor']}"]["accrued_district_utility"]
            assert c["expected"]["original_incumbent_score"] != past


def test_ledger_common_and_no_expected_answer_in_schema_or_tasks():
    for case in q.cases():
        fragment = q.structured(case)
        assert fragment["messages"][0]["content"] == ledger.SYSTEM
        data = contract._object(fragment["messages"][1]["content"])
        assert "expected" not in data
        assert fragment["tool_choice"] == "auto"
        assert len(fragment["tools"]) == 1
        assert "const" not in json.dumps(fragment["tools"])
        assert "enum" not in json.dumps(fragment["tools"]) if case["kind"] == "fact" else True
        if case["kind"] == "action":
            assert "hypothetical_assumptions" not in data
    assert len(q.requests()) == 24
    assert len({r["request"]["seed"] for r in q.requests()}) == 24


def test_tampered_ledger_rejected_before_request():
    case = deepcopy(q.cases()[0])
    data = json.loads(case["messages"][1]["content"])
    data["score_ledger"]["third_term_bonus"] = 1
    case["messages"][1]["content"] = json.dumps(data)
    with pytest.raises(ValueError, match="ledger changed"):
        q.structured(case)


def test_wrong_horizon_remains_a_safe_factual_failure_not_a_corrected_answer():
    case = next(c for c in q.cases() if c["id"] == "binding_majority-terminal")
    answer = q.presence.encode(case["expected"])
    answer["original_incumbent_score"] = 12
    result = q.score(case, stream(json.dumps(answer)))
    assert result["valid_action"] and not result["exact"]
    assert result["action"]["original_incumbent_score"] == 12
