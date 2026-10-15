"""Offline checks that the simpler tool schema does not change the game."""
from __future__ import annotations

from decimal import Decimal
import json

from paper3 import coalition_contracts as game
from paper3 import constituent_b_gptoss_gate_design as prior_design
from paper3 import constituent_b_gptoss_simple_actions as actions
from paper3 import constituent_b_tool_interface as tool


def test_fresh_contexts_and_reservations():
    rows = actions.cases()
    assert [row["id"] for row in rows] == [
        "new-action-draft", "new-action-response", "new-action-first-vote"]
    assert [row["request"]["seed"] for row in rows] == [664000, 664001, 664002]
    assert sum(Decimal(row["reserved_usd"]) for row in rows) == Decimal("0.00901692")
    for row in rows:
        request = row["request"]
        assert request["model"] == actions.MODEL
        assert request["provider"]["only"] == [actions.PROVIDER_TAG]
        assert request["provider"]["allow_fallbacks"] is False
        assert request["reasoning"] == dict(effort="medium", exclude=False)
        assert request["tool_choice"]["function"]["name"] == tool.TOOL_NAME
        assert len(request["tools"]) == 1
        assert "response_format" not in request
    old_draft = next(case for case in prior_design.cases()
                     if case.get("stage") == "draft")
    assert rows[0]["context"]["messages"] != old_draft["messages"]


def test_server_schema_simplifies_but_controller_legality_unchanged():
    draft, response, vote = actions.contexts()
    shape = actions.simplified_schema(draft)
    coalition = shape["properties"]["coalition"]
    assert coalition == dict(type="array", items=dict(type="integer"))
    assert shape["properties"]["projects"]["properties"]["A"] == dict(type="string")
    assert actions.simplified_schema(vote) == dict(
        type="object", properties=dict(vote=dict(type="boolean")),
        required=["vote"], additionalProperties=False)
    legal = dict(projects=dict(A="A0", B="B1"), first="A",
                 coalition=[0, 1, 3, 5], message="legal")
    assert game.parse_action(json.dumps(legal), "draft") == legal
    illegal = dict(legal, coalition=[0, 1, 3])
    try:
        game.parse_action(json.dumps(illegal), "draft")
    except ValueError:
        pass
    else:
        raise AssertionError("local coalition rule must reject an illegal tool argument")
    answer = dict(legal, support=True)
    assert game.parse_action(json.dumps(answer), "response") == answer
    assert game.parse_action('{"vote":true}', "first_vote") == dict(vote=True)
