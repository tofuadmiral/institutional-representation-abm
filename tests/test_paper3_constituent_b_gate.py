import json

from paper3 import coalition_contracts as game
from paper3 import constituent_b_gate as gate


def test_gate_inventory_scores_all_expected_facts_and_legal_actions():
    cases = gate.cases()
    assert len(cases) == 12
    assert len({case["name"] for case in cases}) == 12
    assert [case["kind"] for case in cases].count("fact") == 9
    for case in cases:
        if case["kind"] == "fact":
            assert gate.score(json.dumps(case["expected"]), case)["exact"]
        else:
            if case["stage"] == "response":
                reply = dict(projects=dict(A="A0", B="B0"), first="A",
                             coalition=[0, 1, 3, 4], message="ok", support=True)
            elif case["stage"] == "draft":
                reply = dict(projects=dict(A="A0", B="B0"), first="A",
                             coalition=[0, 1, 3, 4], message="ok")
            else:
                reply = dict(vote=True)
            assert gate.score(json.dumps(reply), case)["exact"]


def test_gate_rejects_wrong_values_types_duplicates_and_malformed_actions():
    fact = gate.cases()[0]
    wrong = dict(fact["expected"])
    wrong["district_total_utility"] += 1
    assert not gate.score(json.dumps(wrong), fact)["exact"]
    wrong["district_total_utility"] = True
    assert not gate.score(json.dumps(wrong), fact)["exact"]
    duplicate = '{"district_total_utility":1,"district_total_utility":2}'
    assert not gate.score(duplicate, fact)["exact"]
    action = gate.cases()[-2]
    assert action["stage"] == "response"
    assert not gate.score('{"support":true,"projects":{}}', action)["exact"]


def test_gate_rule_cases_include_both_active_and_inactive_contracts():
    contracts = [c for c in gate.cases() if c["name"].startswith("contract-")]
    assert {c["expected"]["agreement_active"] for c in contracts} == {True, False}
    assert {c["expected"]["project_passed"] for c in contracts} == {True, False}
    mandates = [c for c in gate.cases() if c["name"].startswith("mandate-")]
    assert any(c["expected"]["district_total_utility"] < 0 for c in mandates)
    assert any(c["expected"]["citizens_worse_than_q"] >
               c["expected"]["citizens_better_than_q"] for c in mandates)


def test_fact_answer_keys_recompute_from_only_the_sent_prompt_inputs():
    """No reliance on the case generator's hidden expected-answer calculation."""
    for case in gate.cases():
        if case["kind"] != "fact":
            continue
        system, user = case["messages"]
        assert '"expected"' not in system["content"] + user["content"]
        context = json.loads(user["content"].split("\n", 1)[0])
        if case["name"].startswith("mandate-"):
            policies = context["policy_coordinates"]
            enacted = list(policies["q"])
            for project in context["fixed_enacted_projects"]:
                dimension = 0 if project.startswith("A") else 1
                enacted[dimension] = policies[project][dimension]
            changes = []
            for citizen in context["own_citizens"]:
                baseline = sum(weight * (q - ideal) ** 2 for q, ideal, weight
                               in zip(policies["q"], citizen["ideal"], citizen["weights"]))
                new = sum(weight * (p - ideal) ** 2 for p, ideal, weight
                          in zip(enacted, citizen["ideal"], citizen["weights"]))
                changes.append(baseline - new)
            assert case["expected"] == dict(
                district_total_utility=sum(changes),
                citizens_better_than_q=sum(value > 0 for value in changes),
                citizens_worse_than_q=sum(value < 0 for value in changes))
            assert sum(context["district_summed_utilities"][project]
                       for project in context["fixed_enacted_projects"]) == sum(changes)
        else:
            assert case["name"].startswith("contract-")
            arm = next(name for name, rules in game.ARM_RULES.items()
                       if rules in system["content"])
            events = context["fixed_record"]
            coalition = context["coalition"]
            consent = next(event for event in events if event["type"] == "consent")
            active = all(consent["approvals"][member] for member in coalition)
            if arm == "universal_clearance":
                active = active and all(consent["approvals"])
            due = active
            if context["vote_stage"] == "second_vote":
                first = next(event for event in events if event["type"] == "first_vote")
                due = due and first["passed"] and all(
                    first["executed"][member] for member in coalition)
            requested = context["fixed_requested_votes"]
            executed = [True if due and arm != "public_promise" and i in coalition
                        else requested[i] for i in game.ACTORS]
            assert case["expected"] == dict(
                agreement_active=bool(active),
                executed_yes_count=sum(executed),
                project_passed=sum(executed) >= 4)
