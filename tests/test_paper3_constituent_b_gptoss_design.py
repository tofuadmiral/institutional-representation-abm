"""Independent offline checks of fresh gate prompts, answers and bounds."""
from __future__ import annotations

from decimal import Decimal
import json

from paper3 import coalition_contracts as game
from paper3 import constituent_b_gptoss_gate_design as design
from paper3 import constituent_b_gptoss_requests as requests
from paper3 import constituent_b_tool_interface as tool
from paper3 import hosted_reasoning_channel_calls as channel


def test_fresh_inventory_and_same_substantive_task():
    rows = design.cases()
    assert len(rows) == 12 and len({row["name"] for row in rows}) == 12
    assert [row["kind"] for row in rows].count("fact") == 9
    assert [row["stage"] for row in rows if row["kind"] == "action"] == [
        "draft", "response", "first_vote"]
    assert all('"expected"' not in str(row["messages"]) for row in rows)
    assert {row["expected"]["agreement_active"] for row in rows
            if row.get("fact_type") == "contract"} == {True, False}
    assert {row["expected"]["project_passed"] for row in rows
            if row.get("fact_type") == "contract"} == {True, False}
    assert any(row["expected"]["citizens_better_than_q"] <
               row["expected"]["citizens_worse_than_q"] for row in rows
               if row.get("fact_type") == "mandate")


def test_mandate_answers_recomputed_from_sent_citizens():
    for row in design.cases():
        if row.get("fact_type") != "mandate":
            continue
        context = json.loads(row["messages"][1]["content"].split("\n", 1)[0])
        coordinates = context["policy_coordinates"]
        policy = list(coordinates["q"])
        for project in context["fixed_enacted_projects"]:
            axis = 0 if project.startswith("A") else 1
            policy[axis] = coordinates[project][axis]
        delta = []
        for citizen in context["own_citizens"]:
            before = sum(weight * (q - ideal) ** 2 for q, ideal, weight in
                         zip(coordinates["q"], citizen["ideal"], citizen["weights"]))
            after = sum(weight * (p - ideal) ** 2 for p, ideal, weight in
                        zip(policy, citizen["ideal"], citizen["weights"]))
            delta.append(before - after)
        assert row["expected"] == dict(
            district_total_utility=sum(delta),
            citizens_better_than_q=sum(value > 0 for value in delta),
            citizens_worse_than_q=sum(value < 0 for value in delta))
        assert sum(context["district_summed_utilities"][name]
                   for name in context["fixed_enacted_projects"]) == sum(delta)


def test_contract_answers_recomputed_from_sent_record():
    for row in design.cases():
        if row.get("fact_type") != "contract":
            continue
        system, user = row["messages"]
        arm = next(name for name, rules in game.ARM_RULES.items()
                   if rules in system["content"])
        context = json.loads(user["content"].split("\n", 1)[0])
        record = context["fixed_record"]
        members = context["coalition"]
        approvals = next(event["approvals"] for event in record
                         if event["type"] == "consent")
        active = all(approvals[i] for i in members)
        if arm == "universal_clearance":
            active = active and all(approvals)
        due = active
        if context["vote_stage"] == "second_vote":
            first = next(event for event in record if event["type"] == "first_vote")
            due = due and first["passed"] and all(first["executed"][i]
                                                  for i in members)
        requested = context["fixed_requested_votes"]
        executed = [bool(due and arm != "public_promise" and i in members)
                    or requested[i] for i in game.ACTORS]
        assert row["expected"] == dict(agreement_active=bool(active),
                                       executed_yes_count=sum(executed),
                                       project_passed=sum(executed) >= 4)


def test_requests_pin_model_provider_tool_and_cost():
    rows = requests.cases()
    assert {row["request"]["seed"] for row in rows} == set(range(662000, 662012))
    assert sum(Decimal(row["reserved_usd"]) for row in rows) == Decimal("0.03586926")
    for row in rows:
        req = row["request"]
        assert req["model"] == requests.MODEL
        assert req["provider"]["only"] == [requests.PROVIDER_TAG]
        assert req["provider"]["allow_fallbacks"] is False
        assert req["tool_choice"]["function"]["name"] == tool.TOOL_NAME
        assert req["reasoning"] == dict(effort="medium", exclude=False)
        assert len(req["tools"]) == 1
        assert "response_format" not in req


def test_actual_channel_required_and_bad_count_diagnostic_only():
    observed = dict(reasoning_channel_characters=10,
                    usage=dict(completion_tokens=89,
                               completion_tokens_details=dict(reasoning_tokens=96)))
    report = channel.native_evidence(observed)
    assert report["present"] is True
    assert report["reported_count_consistent"] is False
    observed["reasoning_channel_characters"] = 0
    assert channel.native_evidence(observed)["present"] is False
