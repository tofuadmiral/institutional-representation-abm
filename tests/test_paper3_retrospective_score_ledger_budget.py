"""Engineering budget checks; no provider calls or scientific evidence."""
from decimal import Decimal
import json
from random import Random

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_score_ledger_budget as budget
from paper3 import retrospective_contract_route_v2 as route
from tests.test_paper3_retrospective_score_ledger import fixture


@pytest.mark.parametrize("width", range(2, 9))
@pytest.mark.parametrize("arm", institution.ARMS)
def test_full_legal_history_bound_dominates_varied_actions_and_unicode(width, arm):
    game, seed = fixture(width), 3990000
    report = budget.legal_history_bounds(game, arm, seed)
    rng = Random(width)
    texts = ("\\", '"', "\t", "\n", "\r", "\U0010ffff", "\U0001f984", "a", "")
    # Fixed outcomes cover all first-term retention states; other actions differ
    # from the envelope scripts, including variable drafts/finals/counteroffers.
    for first in range(width):
        def ask(actor, identity, term, stage, context, index):
            request = budget.action_request(game, arm, seed, actor, identity,
                term, stage, context, index)
            actual = route.reservation(request)
            assert actual["input_token_bound"] <= report["input_bounds"][index]
            assert actual["input_token_bound"] + route.OUTPUT_BOUND <= route.CONTEXT
            if stage in ("draft", "final"):
                return dict(policy=first if term == 0 and stage == "final"
                    else rng.randrange(width), message=rng.choice(texts) * 128)
            if stage == "response":
                return dict(support=bool(rng.randrange(2)), counter_policy=rng.randrange(width),
                            message=rng.choice(texts) * 128)
            return dict(vote=True if term == 0 else bool(rng.randrange(2)))
        institution.episode(game, arm, ask)
    assert len(report["input_bounds"]) == 30
    assert report["logical_calls"] == 30
    expected = sum((Decimal(x) * route.PRICE_IN + Decimal(14000) * route.PRICE_OUT)
                   / 1000000 for x in report["input_bounds"])
    assert Decimal(report["reservation_usd"]) == expected
    assert not report["allocation_authorized"]


def test_double_json_scalar_encoding_max_four_bytes_per_legal_character():
    legal = [chr(i) for i in range(32, 127)] + [
        "\t", "\n", "\r", "\u00a0", "\u07ff", "\u0800", "\uffff",
        "\U00010000", "\U0010ffff"]
    def wire(text):
        payload = json.dumps(dict(message=text), ensure_ascii=False, separators=(",", ":"))
        return len(json.dumps(dict(content=payload), ensure_ascii=False,
                              separators=(",", ":")).encode())
    baseline = wire("")
    assert all(wire(char) - baseline <= 4 for char in legal)
    assert wire("\\" * 128) - baseline == 512
    assert wire("\U0010ffff" * 128) - baseline == 512


def test_boolean_padding_monotone_and_never_mutates_scientific_request():
    game = fixture(2)
    def ask(actor, identity, term, stage, context, index):
        request = budget.action_request(game, "binding_sum", 3990000,
            actor, identity, term, stage, context, index)
        before = json.dumps(request, sort_keys=True)
        padded = budget.padded_reservation(request)
        assert padded["input_token_bound"] >= route.reservation(request)["input_token_bound"]
        assert json.dumps(request, sort_keys=True) == before
        if stage in ("draft", "final"):
            return dict(policy=1, message="\\" * 128)
        if stage == "response":
            return dict(support=True, counter_policy=0, message="\\" * 128)
        return dict(vote=False)
    institution.episode(game, "binding_sum", ask)


def test_full_assignment_inventory_and_entire_retry_reservation():
    assignments = tuple(dict(id=arm, game=fixture(2), arm=arm, seed_base=3990000)
                        for arm in institution.ARMS)
    result = budget.block_bound(assignments, maximum_reissues=1)
    rows = result["assignments"]
    primary = sum(Decimal(row["reservation_usd"]) for row in rows)
    retry = max(Decimal(row["largest_attempt_usd"]) for row in rows)
    assert result["logical_calls"] == 120 and result["maximum_physical_calls"] == 121
    assert Decimal(result["full_reservation_usd"]) == primary + retry
    assert not result["allocation_authorized"] and not result["publication_evidence"]
    with pytest.raises(ValueError, match="identities"):
        budget.block_bound((assignments[0], assignments[0]))
    with pytest.raises(ValueError, match="retry"):
        budget.block_bound(assignments, True)


def test_action_envelope_equals_every_pinned_qualification_action_without_inheritance_claim():
    from experiments import paper3_retrospective_score_ledger_gate_v1 as qualification
    actions = [c for c in qualification.qualification.cases() if c["kind"] == "action"]
    assert len(actions) == 12
    for case in actions:
        actual = budget.structured(case["messages"], case["game"], case["stage"])
        expected = qualification.qualification.structured(case)
        assert actual == expected
        assert actual["tools"][0]["function"]["description"] == budget.QUALIFIED_TOOL_DESCRIPTION
