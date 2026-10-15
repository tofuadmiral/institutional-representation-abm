from copy import deepcopy
from decimal import Decimal
import json

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design
from paper3 import retrospective_interface as original
from paper3 import retrospective_labeled_interface as interface
from paper3 import retrospective_labeled_qualification as qualification
from paper3 import retrospective_requests as route


def trace(action):
    frame = dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0, id="one",
        type="function", function=dict(name="submit_decision", arguments=json.dumps(action)))]),
        finish_reason="tool_calls")])
    return dict(lines=["data: " + json.dumps(frame), "", "data: [DONE]", ""])


@pytest.mark.parametrize("arm", institution.ARMS)
def test_legend_is_common_preserves_all_data_and_sealing_through_handover(arm):
    game = design.generate(3190001).conflict
    seen = []

    def ask(actor, identity, term, stage, context, index):
        before = deepcopy(context)
        base = original.messages(game, arm, actor, identity, term, stage, context)
        messages = interface.messages(game, arm, actor, identity, term, stage, context)
        assert context == before
        value, prior = (json.loads(row[1]["content"]) for row in (messages, base))
        legend = value.pop("data_layout")
        assert value == prior
        assert legend["utilities_axes"] == ["term", "district", "citizen", "policy"]
        assert legend["utilities_shape"] == [2, 7, 9, 6]
        assert legend["menu_assessments_term"] == term
        assert messages[0]["content"] == interface.SYSTEM
        assert "expected" not in value
        if stage == "response":
            assert "responses" not in value
        assert "requested" not in value and "executed" not in value
        fragment = interface.structured(messages, game, stage)
        assert fragment["tool_choice"] == "auto" and len(fragment["tools"]) == 1
        seen.append(identity)
        if stage in ("draft", "final"):
            return dict(policy=4, message="fixture")
        if stage == "response":
            return dict(support=True, counter_policy=1, message="fixture")
        return dict(vote=True)

    outcome = institution.episode(game, arm, ask)
    assert outcome.calls == len(seen) == 30
    if arm.startswith("binding"):
        assert any(identity.startswith("successor") for identity in seen)


def test_fresh_cases_no_answer_schema_leak_and_all_strategies_legal():
    cases = qualification.cases()
    assert len(cases) == 18 and sum(case["kind"] == "fact" for case in cases) == 12
    assert qualification.FRAME_SEED != 3100001
    terminal = [case for case in cases if case["id"].endswith("terminal")]
    assert all(case["parameters"] == terminal[0]["parameters"] for case in terminal)
    for case in cases:
        prompt = json.loads(case["messages"][1]["content"])
        assert "expected" not in prompt and "const" not in json.dumps(case["parameters"])
        if case["kind"] == "fact":
            assert qualification.score(case, trace(case["expected"]))["exact"]
            wrong = deepcopy(case["expected"])
            field = next(key for key, value in wrong.items() if type(value) is int)
            wrong[field] += 1
            assert not qualification.score(case, trace(wrong))["exact"]
        else:
            for policy in range(6):
                if case["stage"] in ("draft", "final"):
                    action = dict(policy=policy, message="arbitrary legal policy")
                elif case["stage"] == "response":
                    action = dict(support=False, counter_policy=policy, message="legal")
                else:
                    action = dict(vote=bool(policy % 2))
                assert qualification.score(case, trace(action))["exact"]


def test_independent_counterfactual_arithmetic_own_ballot_not_enactment():
    for case in qualification.cases():
        if not case["id"].endswith("counterfactual"):
            continue
        prompt = json.loads(case["messages"][1]["content"])
        assert "YOUR OWN ballot" in prompt["task"]
        peers = prompt["hypothetical_assumptions"]["other_six_ballots"]
        for vote, field in ((True, "score_if_yes"), (False, "score_if_no")):
            enacted = prompt["final"]["policy"] if sum(peers) + vote >= 4 else 0
            citizens = [row[enacted] for row in case["game"].utilities[0][case["actor"]]]
            retained = case["arm"].startswith("advisory") or (
                sum(v >= 0 for v in citizens) >= 5 if case["arm"].endswith("majority")
                else sum(citizens) >= 0)
            assert case["expected"][field] == sum(citizens) + retained * case["game"].office_value
        if len(set(peers)) == 1:
            assert case["expected"]["score_if_yes"] == case["expected"]["score_if_no"]


def test_eighteen_serial_wire_bounds_and_pinned_route():
    rows = qualification.requests()
    bounds = [route.reservation(row["request"]) for row in rows]
    assert sum(Decimal(row["reserved_usd"]) for row in bounds) == Decimal(".09299080")
    assert max(row["input_token_bound"] for row in bounds) == 17274
    assert all(row["input_token_bound"] + route.OUTPUT_BOUND <= route.CONTEXT for row in bounds)
    assert [row["request"]["seed"] for row in rows] == list(range(3150000, 3150018))
    assert all(row["request"]["provider"]["allow_fallbacks"] is False and
               row["request"]["reasoning"] == dict(enabled=True, exclude=False) for row in rows)
