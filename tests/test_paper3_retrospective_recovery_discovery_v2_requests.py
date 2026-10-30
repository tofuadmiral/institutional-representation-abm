from decimal import Decimal
import json

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_deepseek_discovery_requests as earlier
from paper3 import retrospective_recovery_discovery_v2_requests as requests
from paper3 import retrospective_keyed_interface as interface
from paper3 import retrospective_contract_qualification_v2 as qualification
from paper3 import retrospective_contract_route_v2 as route
from paper3 import retrospective_readout as readout
from paper3 import retrospective_contract_recovery as recovery
from paper3 import retrospective_contract_discovery_requests as closed


def test_same_profiles_arms_paired_units_and_screen_without_inherited_qualification():
    assert {p.seed for p in requests.pairs()} == {3731001, 3731002}
    assert requests.pairs() != earlier.pairs()
    assignments = requests.assignments()
    assert len(assignments) == 16 and len({r["id"] for r in assignments}) == 16
    seeds = {r["seed_base"] + i for r in assignments for i in range(30)}
    assert len(seeds) == 60
    assert not seeds & {r["seed_base"] + i for r in earlier.assignments() for i in range(30)}
    assert not seeds & {r["seed_base"] + i for r in closed.assignments() for i in range(30)}
    assert not seeds & set(range(route.SEED_BASE, qualification.SEED_BASE + 18))
    for pair in requests.pairs():
        assert len({r["seed_base"] for r in assignments if r["seed"] == pair.seed}) == 1
    outcomes = {(p.seed, s, a): None for p in requests.pairs()
                for s in readout.STRATA for a in institution.ARMS}
    result = readout.screen(requests.pairs(), outcomes, completed_episodes=set(), qualified=False)
    assert result["verdict"] == "qualification_failed" and not result["publication_evidence"]
    assert float(result["min_effect"]) == .04


def test_all480_bounds_cover_named_cards_maximum_history_and_native_wire():
    bounds = requests.legal_history_bounds()
    assert bounds["maximum_calls"] == 480 and Decimal(bounds["reservation_usd"]) > 0
    assert not any(bounds[k] for k in ("qualification_inherited", "allocation_authorized",
                                      "cumulative_authority_extended"))
    for assignment, bounded in zip(requests.assignments(), bounds["assignments"], strict=True):
        assert assignment["id"] == bounded["id"] and len(bounded["input_bounds"]) == 30
        # Durable ledger identifiers must be valid for every prospectively assigned case.
        assert len("pivot_b_retrospective_recovery_discovery_v2-b0-" + assignment["id"] + "-00-a2") <= 100

        def ask(actor, identity, term, stage, context, index):
            request = requests.action_request(assignment, actor, identity, term, stage, context, index)
            prompt = json.loads(request["messages"][1]["content"])
            assert interface.restore_utilities(prompt["payoff_cards"], 6) == assignment["game"].utilities
            assert "aligned" not in json.dumps(prompt) and "conflict" not in json.dumps(prompt)
            assert request["max_tokens"] == 14000 and request["tool_choice"] == "auto"
            assert request["provider"]["only"] == [route.TAG]
            assert route.reservation(request)["input_token_bound"] <= bounded["input_bounds"][index]
            if stage in ("draft", "final"):
                return dict(policy=3, message="😀" * 128)
            if stage == "response":
                return dict(support=True, counter_policy=2, message="fixture")
            return dict(vote=actor >= 3)
        assert institution.episode(assignment["game"], assignment["arm"], ask).calls == 30


def test_whole_block_full_path_and25_reissue_bounds_not_expected_spending():
    bounds = requests.legal_history_bounds()
    for seed in requests.FRAME_SEEDS:
        ids = {a["id"] for a in requests.assignments() if a["seed"] == seed}
        rows = [a for a in bounds["assignments"] if a["id"] in ids]
        base = sum((Decimal(a["reserved_usd"]) for a in rows), Decimal(0))
        largest = (Decimal(max(v for a in rows for v in a["input_bounds"])) * route.PRICE_IN +
                   Decimal(route.OUTPUT_BOUND) * route.PRICE_OUT) / 1000000
        proof = recovery.reservation_bound(base, largest)
        assert proof["fits_proposed_stage_cap"]
        assert Decimal(proof["full_path_usd"]) == base + 25 * largest
        assert not proof["allocation_authorized"] and not proof["old_run_reopen_authorized"]
