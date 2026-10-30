from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import json

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design
from paper3 import retrospective_interface as original
from paper3 import retrospective_keyed_interface as interface
from paper3 import retrospective_keyed_qualification as qualification
from paper3 import retrospective_deepseek_route as route
from tests.test_paper3_retrospective_labeled_interface import trace


@pytest.mark.parametrize("width", range(2, 9))
def test_every_coordinate_roundtrip_for_all_legal_menu_widths(width):
    template = design.generate(3240001).conflict
    utilities = tuple(tuple(tuple(tuple(0 if p == 0 else
        (t * 7 + d * 3 + c * 5 + p * 11) % 21 - 10 for p in range(width))
        for c in range(9)) for d in range(7)) for t in range(2))
    game = replace(template, utilities=utilities)
    cards = interface.payoff_cards(game)
    assert interface.restore_utilities(json.loads(json.dumps(cards)), width) == utilities
    for t in range(2):
        for d in range(7):
            for p in range(width):
                card = cards[f"term_{t}"][f"district_{d}"][f"policy_{p}"]
                assert card["citizen_utilities"] == [utilities[t][d][c][p] for c in range(9)]
                assert card["district_sum"] == sum(utilities[t][d][c][p] for c in range(9))


@pytest.mark.parametrize("tamper", ("term", "district", "policy", "extra", "sum", "bool", "citizens"))
def test_missing_extra_or_inconsistent_cards_fail_closed(tamper):
    cards = interface.payoff_cards(design.generate(3240001).conflict)
    district = cards["term_0"]["district_0"]
    card = district["policy_0"]
    if tamper == "term":
        cards.pop("term_1")
    elif tamper == "district":
        cards["term_0"].pop("district_6")
    elif tamper == "policy":
        district.pop("policy_5")
    elif tamper == "extra":
        card["recommendation"] = True
    elif tamper == "sum":
        card["district_sum"] += 1
    elif tamper == "bool":
        card["citizen_utilities"][0] = False
    else:
        card["citizen_utilities"].pop()
    with pytest.raises(ValueError):
        interface.restore_utilities(cards, 6)


@pytest.mark.parametrize("arm", institution.ARMS)
def test_common_lossless_cards_preserve_history_sealing_and_handover(arm):
    game = design.generate(3240001).conflict
    seen = []

    def ask(actor, identity, term, stage, context, index):
        before = deepcopy(context)
        base = original.messages(game, arm, actor, identity, term, stage, context)
        keyed = interface.messages(game, arm, actor, identity, term, stage, context)
        assert context == before
        value, prior = [json.loads(m[1]["content"]) for m in (keyed, base)]
        assert keyed[0]["content"] == interface.SYSTEM
        cards = value.pop("payoff_cards")
        assert interface.restore_utilities(cards, 6) == game.utilities
        assert cards == interface.payoff_cards(game)  # Independent of arm/actor/history.
        restored = [[value["assessment_cards"][f"district_{d}"][f"policy_{p}"]
                     for p in range(6)] for d in range(7)]
        assert restored == prior.pop("menu_assessments")
        prior.pop("utilities")
        value.pop("assessment_cards")
        assert value.pop("data_layout")["assessment_cards_term"] == term
        assert value == prior  # All other disclosure/role/history/rules identical.
        if stage == "response":
            assert "responses" not in value
        assert "requested" not in value and "executed" not in value
        fragment = interface.structured(keyed, game, stage)
        assert fragment["tool_choice"] == "auto" and len(fragment["tools"]) == 1
        assert fragment["tools"][0]["function"]["parameters"] == (
            interface.structured(base, game, stage)["tools"][0]["function"]["parameters"])
        seen.append(identity)
        if stage in ("draft", "final"):
            return dict(policy=4, message="fixture")
        if stage == "response":
            return dict(support=True, counter_policy=1, message="fixture")
        return dict(vote=True)

    episode = institution.episode(game, arm, ask)
    assert episode.calls == len(seen) == 30
    assert [t.requested for t in episode.terms] == [(True,) * 7] * 2
    if arm.startswith("binding"):
        assert any(identity.startswith("successor") for identity in seen)


def test_independent_factual_oracles_and_no_answer_or_strategy_leak():
    cases = qualification.cases()
    assert len(cases) == 18 and sum(c["kind"] == "fact" for c in cases) == 12
    assert qualification.FRAME_SEED not in {3100001, 3140001, 3220001}
    for case in cases:
        prompt = json.loads(case["messages"][1]["content"])
        assert not {"utilities", "menu_assessments", "expected", "recommended_policy"} & prompt.keys()
        assert "const" not in json.dumps(case["parameters"])
        if case["kind"] != "fact":
            for p in range(6):
                action = (dict(policy=p, message="any legal policy") if case["stage"] in ("draft", "final")
                    else dict(support=bool(p % 2), counter_policy=p, message="legal")
                    if case["stage"] == "response" else dict(vote=bool(p % 2)))
                assert qualification.score(case, trace(action))["exact"]
            continue
        game, d, arm = case["game"], case["actor"], case["arm"]

        def values(t, p):
            return [game.utilities[t][d][c][p] for c in range(9)]

        def retained(p):
            citizens = values(0, p)
            return arm.startswith("advisory") or (sum(v >= 0 for v in citizens) >= 5
                if arm.endswith("majority") else sum(citizens) >= 0)

        p = prompt["final"]["policy"]
        if case["id"].endswith("assessment"):
            citizens = values(0, p)
            expected = dict(district_sum=sum(citizens), citizens_better=sum(v > 0 for v in citizens),
                citizens_worse=sum(v < 0 for v in citizens),
                majority_passed=sum(v >= 0 for v in citizens) >= 5,
                sum_passed=sum(citizens) >= 0, incumbent_retained=retained(p))
        elif case["id"].endswith("counterfactual"):
            assumptions = prompt["hypothetical_assumptions"]
            expected = {}
            for vote, name in ((True, "score_if_yes"), (False, "score_if_no")):
                enacted = p if sum(assumptions["other_six_ballots"]) + vote >= 4 else 0
                expected[name] = (sum(values(0, enacted)) +
                    sum(values(1, assumptions["second_term_enacted_policy"])) +
                    game.office_value * retained(enacted))
        else:
            first_policy = prompt["history"][0]["enacted"]
            keeps_office = retained(first_policy)
            expected = dict(acting_identity=f"{'incumbent' if keeps_office else 'successor'}-r{d}",
                original_incumbent_score=sum(values(0, first_policy)) + sum(values(1, p)) +
                    keeps_office * game.office_value,
                successor_score=None if keeps_office else sum(values(1, p)), third_term_bonus=0)
        assert case["expected"] == expected
        assert qualification.score(case, trace(expected))["exact"]
        wrong = deepcopy(expected)
        field = next(k for k, v in wrong.items() if type(v) is int)
        wrong[field] += 1
        assert not qualification.score(case, trace(wrong))["exact"]


def test_candidate_wire_bounds_unchanged_route_and_fresh_seeds():
    rows = qualification.requests()
    amounts = [Decimal(route.reservation(r["request"])["reserved_usd"]) for r in rows]
    worst_path = sum(amounts) + sum(sorted(amounts, reverse=True)[:2])
    assert worst_path <= Decimal(".30")  # Candidate bound, not an allocated cap.
    assert [r["request"]["seed"] for r in rows] == list(range(3250000, 3250018))
    for row in rows:
        request = row["request"]
        assert request["model"] == route.MODEL and request["provider"]["only"] == [route.TAG]
        assert not request["provider"]["allow_fallbacks"]
        assert request["reasoning"] == dict(enabled=True, exclude=False)
        assert request["max_tokens"] == 14000 and request["tool_choice"] == "auto"
        assert route.reservation(request)["input_token_bound"] + 14000 <= route.CONTEXT
