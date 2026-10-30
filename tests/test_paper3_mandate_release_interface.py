"""Pure presentation checks; strict formatting is not the scientific result."""

import json

import pytest

from paper3 import mandate_release_design as design
from paper3 import mandate_release_institution as institution
from paper3 import mandate_release_interface as interface


def test_role_and_policy_labels_roundtrip_through_strict_action_decoder():
    case = design.cases()[1]
    assert case.display_projects == ("Blue", "Amber")
    assert case.display_roles == (1, 2, 3, 4, 5, 6, 0)
    raw = json.dumps(dict(second_project="Blue", coalition=[1, 2, 3, 4],
                          message="Y1 package"))
    offer = interface.decode(case, "draft", raw)
    assert offer == dict(second_project="Y1", coalition=[0, 1, 2, 3],
                         message="Y1 package")
    assert interface.decode(case, "response", json.dumps(dict(
        support=False, counter_project="Amber", message="prefer Y2"
    ))) == dict(support=False, counter_project="Y2", message="prefer Y2")
    assert interface.decode(case, "consent", '{"consent":true}') == {"consent": True}
    assert interface.decode(case, "x_vote", '{"vote":false}') == {"vote": False}
    with pytest.raises(ValueError):
        interface.decode(case, "draft", '{"second_project":"Blue",'
                         '"coalition":[1,1,2,3],"message":"duplicate"}')
    with pytest.raises(ValueError):
        interface.decode(case, "x_vote", '{"vote":true,"reason":"extra"}')


def test_matched_prompts_differ_only_by_announced_institution_pre_shock():
    case = design.cases()[0]
    context = dict(before=case.game.before, possible_after_shock=case.game.after,
                   shock_probability=str(case.game.shock_probability), proposer=0)
    locked = interface.messages(case, 0, "draft", dict(context, arm="irrevocable"))
    release = interface.messages(case, 0, "draft",
                                 dict(context, arm="constituent_release"))
    assert locked[1] == release[1]
    assert locked[0] != release[0]
    payload = json.loads(locked[1]["content"])
    assert payload["utility_columns"] == ["X", "Amber", "Blue"]
    assert len(payload["current_citizen_utilities"]) == 7
    assert all(len(row["citizens"]) == 9 for row in payload["current_citizen_utilities"])
    assert payload["if_shock_changed_representatives"] == [case.display_roles[3]]
    assert payload["if_shock_release_yes_counts"][0]["release_yes"] >= 5
    for district in payload["current_citizen_utilities"]:
        assert district["district_sums"] == [
            sum(citizen[index] for citizen in district["citizens"])
            for index in range(3)
        ]
        assert district["full_bundle_sums"] == [
            sum(citizen[0] + citizen[index] for citizen in district["citizens"])
            for index in (1, 2)
        ]
    assert "shock_realized" not in payload["history"]
    assert "realized_citizen_utilities" not in payload["history"]
    with pytest.raises(ValueError):
        interface.messages(case, 0, "draft", dict(context, arm="irrevocable",
                                                  shock_realized=True))


def test_all_six_action_schemas_require_only_expected_fields():
    case = design.cases()[0]
    expected = {
        "draft": {"second_project", "coalition", "message"},
        "response": {"support", "counter_project", "message"},
        "final": {"second_project", "coalition", "message"},
        "consent": {"consent"},
        "x_vote": {"vote"},
        "y_vote": {"vote"},
    }
    for stage, fields in expected.items():
        schema = interface.schema(case, stage)
        assert set(schema["properties"]) == fields
        assert set(schema["required"]) == fields
        assert schema["additionalProperties"] is False


def test_episode_can_use_display_parser_without_leaking_realization():
    case = design.cases()[0]
    seen = []

    def ask(actor, stage, context):
        messages = interface.messages(case, actor, stage, context)
        user = json.loads(messages[1]["content"])
        seen.append((stage, user))
        if stage in ("draft", "final"):
            response = dict(second_project=case.display_projects[0],
                            coalition=[case.display_roles[actor]
                                       for actor in (0, 1, 2, 3)], message="test")
        elif stage == "response":
            response = dict(support=True, counter_project=case.display_projects[0],
                            message="test")
        elif stage == "consent":
            response = dict(consent=True)
        else:
            response = dict(vote=False)
        return interface.decode(case, stage, json.dumps(response))

    result = institution.episode(case.game, "constituent_release", True, 0, ask)
    assert len(seen) == 29
    assert all("shock_realized" not in user["history"]
               for stage, user in seen if stage != "y_vote")
    assert all(user["history"]["shock_realized"] is True
               for stage, user in seen if stage == "y_vote")
    assert result.active and result.released == (3,)
