"""Fresh exogenous inventory only; no model results, freeze or allocation."""
from dataclasses import asdict
from pathlib import Path

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_analysis as science
from paper3 import retrospective_electorates as electorates
from paper3 import retrospective_resource_design_v1 as design


def test_full_fresh_inventory_preserves_all_arms_strata_horizons_and_pairing():
    items = design.assignments()
    assert len(items) == 16 and sum(a["intended_calls"] for a in items) == 480
    assert {a["seed"] for a in items} == {2026101802, 2026101803}
    assert len({a["id"] for a in items}) == 16
    for i, seed in enumerate(design.FRAME_SEEDS):
        block = [a for a in items if a["seed"] == seed]
        assert len(block) == 8
        assert {a["arm"] for a in block} == set(institution.ARMS)
        assert {a["stratum"] for a in block} == set(science.STRATA)
        assert {a["seed_base"] for a in block} == {2026102000 + 64 * i}
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
    repo = Path(__file__).resolve().parents[1]
    root = repo / "results/paper3/pivot_b_retrospective_resource_pilot_v1"
    args = {}
    if root.exists():
        from experiments import paper3_transport_diagnostic as t
        args = dict(current_freeze=root, expected_protocol=t.sha(t.canonical(t.load(root / "manifest.json")).encode()))
    result = design.seed_audit(repo, **args)
    assert not result["overlap"] and result["historical_files"] >= 10428
    assert len(result["planned"]) == 63
    assert not result["allocation_authorized"] and not result["frozen_protocol"]
