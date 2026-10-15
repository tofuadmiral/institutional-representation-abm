"""Offline-only pilot checks; fake transport never sends a model request."""
from decimal import Decimal

import pytest

from experiments import paper3_qwen35_darkbloom_gate as gate
from experiments import paper3_qwen35_exchange_pilot as pilot
from paper3 import coalition_contracts as game
from paper3 import coalition_exchange_design as design
from paper3.pivot_b_budget import atomic


def test_schedule_action_contract_and_cost():
    assignments=pilot.schedule()
    assert len(assignments)==24
    assert len({a["id"] for a in assignments})==24
    assert len({(a["fixture_index"],a["form"],a["repeat"]) for a in assignments})==8
    assert all(len([a for a in assignments if a["block"]==b])==3 for b in range(8))
    for a in assignments:
        assert a["arm"] in game.ARMS
        case=pilot.make_case(a,0,"draft",game.messages(
            design.display_profile(design.fixtures()[a["fixture_index"]],a["form"]),
            a["arm"],0,"draft",[]),0)
        assert case["request"]["model"]==gate.MODEL
        assert case["request"]["provider"]["only"]==[gate.TAG]
        assert case["request"]["reasoning"]["enabled"]
        assert case["request"]["response_format"]["type"]=="json_schema"
        assert case["request"]["seed"]==a["seed_base"]
        assert Decimal(case["reserved_usd"])>0
    assert pilot.specification()["max_calls"]==720


def test_seed_audit_catches_old_requested_seed(tmp_path):
    folder=tmp_path/"results/paper3/old"
    folder.mkdir(parents=True)
    atomic(folder/"manifest.json",dict(protocol=dict(seed=design.SEED_BASES[0])))
    with pytest.raises(ValueError,match="overlap"):
        pilot.seed_audit(tmp_path)


def test_failed_gate_prohibits_pilot_freeze(tmp_path):
    with pytest.raises(ValueError, match="gate did not pass"):
        pilot.prepare(tmp_path/"never_frozen")
    assert not (tmp_path/"never_frozen").exists()
