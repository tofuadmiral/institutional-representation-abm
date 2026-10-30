"""Fresh exogenous inventory only; no model results, freeze or allocation."""
from dataclasses import asdict
from pathlib import Path

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_analysis as science
from paper3 import retrospective_electorates as electorates
from paper3 import retrospective_recovery_design_v2 as design


def test_full_fresh_inventory_preserves_all_arms_strata_horizons_and_pairing():
    items = design.assignments()
    assert len(items) == 16 and sum(a["intended_calls"] for a in items) == 480
    assert {a["seed"] for a in items} == {3881001, 3881002}
    assert len({a["id"] for a in items}) == 16
    for i, seed in enumerate(design.FRAME_SEEDS):
        block = [a for a in items if a["seed"] == seed]
        assert len(block) == 8
        assert {a["arm"] for a in block} == set(institution.ARMS)
        assert {a["stratum"] for a in block} == set(science.STRATA)
        assert {a["seed_base"] for a in block} == {3890000 + 64 * i}
        expected = electorates.generate(seed)
        for a in block:
            actual, original = asdict(a["game"]), asdict(getattr(expected, a["stratum"]))
            actual.pop("game_id")
            original.pop("game_id")
            assert actual == original
            assert len(a["game"].utilities) == 2
            assert len(a["game"].utilities[0]) == 7
            assert all(len(d) == 9 for d in a["game"].utilities[0])
    assert design.assignments() == items


def test_current_historical_seed_inventory_has_no_overlap():
    result = design.seed_audit(Path(__file__).resolve().parents[1])
    assert not result["overlap"] and result["historical_files"] >= 10428
    assert len(result["planned"]) == 63
    assert not result["allocation_authorized"] and not result["frozen_protocol"]
