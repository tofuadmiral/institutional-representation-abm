from copy import deepcopy
import json

from paper3 import retrospective_qualification as qualification


def trace(action):
    frame = dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0, id="one",
        type="function", function=dict(name="submit_decision", arguments=json.dumps(action)))]),
        finish_reason="tool_calls")])
    return dict(lines=["data: " + json.dumps(frame), "", "data: [DONE]", ""])


def test_eighteen_qualification_cases_cover_all_arms_payoffs_and_handover():
    cases = qualification.cases()
    assert len(cases) == 18 and len({case["id"] for case in cases}) == 18
    facts = [case for case in cases if case["kind"] == "fact"]
    assert len(facts) == 12
    for case in facts:
        result = qualification.score(case, trace(case["expected"]))
        assert result["valid_action"] and result["exact"]
        assert qualification.structured(case)["tool_choice"] == "auto"
        if case["id"].endswith("assessment"):
            assert case["expected"]["district_sum"] != 0
            assert case["expected"]["majority_passed"] != case["expected"]["sum_passed"]
            assert case["expected"]["incumbent_retained"] == case["arm"].startswith("advisory")
        if case["id"] in ("binding_majority-terminal", "binding_sum-terminal"):
            expected = case["expected"]
            assert expected["acting_identity"].startswith("successor-")
            assert expected["successor_score"] is not None
            assert expected["third_term_bonus"] == 0


def test_wrong_facts_fail_without_type_coercion_or_hypothesis_scoring():
    for case in qualification.cases():
        if case["kind"] == "fact":
            wrong = deepcopy(case["expected"])
            key = next(key for key, value in wrong.items() if type(value) is int)
            wrong[key] += 1
            result = qualification.score(case, trace(wrong))
            assert result["valid_action"] and not result["exact"]
            wrong[key] = True
            assert not qualification.score(case, trace(wrong))["valid_action"]
        else:
            for policy in range(6):
                if case["stage"] in ("draft", "final"):
                    action = dict(policy=policy, message="any legal policy")
                elif case["stage"] == "response":
                    action = dict(support=False, counter_policy=policy, message="legal counteroffer")
                else:
                    action = dict(vote=bool(policy % 2))
                result = qualification.score(case, trace(action))
                assert result["valid_action"] and result["exact"]


def test_terminal_schema_does_not_reveal_retention_or_successor_answer():
    terminal = [case for case in qualification.cases() if case["id"].endswith("terminal")]
    assert all(case["parameters"] == terminal[0]["parameters"] for case in terminal)
    assert terminal[0]["parameters"]["properties"]["successor_score"]["type"] == ["integer", "null"]
    for case in terminal:
        wrong = dict(case["expected"], successor_score=(None if case["expected"]["successor_score"]
                                                       is not None else 987))
        result = qualification.score(case, trace(wrong))
        assert result["valid_action"] and not result["exact"]


def test_pivotal_nonpivotal_reports_have_correct_independent_score_arithmetic():
    for case in qualification.cases():
        if not case["id"].endswith("counterfactual"):
            continue
        prompt = json.loads(case["messages"][1]["content"])
        peers = prompt["hypothetical_assumptions"]["other_six_ballots"]
        policy = prompt["final"]["policy"]
        for vote, key in ((True, "score_if_yes"), (False, "score_if_no")):
            enacted = policy if sum(peers) + vote >= 4 else 0
            values = [row[enacted] for row in case["game"].utilities[0][case["actor"]]]
            retention = (case["arm"].startswith("advisory") or
                         (sum(value >= 0 for value in values) >= 5 if case["arm"].endswith("majority")
                          else sum(values) >= 0))
            assert case["expected"][key] == sum(values) + retention * case["game"].office_value
        if case["arm"] in ("advisory_majority", "binding_sum"):
            assert case["expected"]["score_if_yes"] == case["expected"]["score_if_no"]
