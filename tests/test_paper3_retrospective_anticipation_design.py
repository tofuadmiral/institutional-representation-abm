"""Deterministic candidate scheduling/collision checks; no real ledger/model."""
from copy import deepcopy
from dataclasses import asdict

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_analysis as analysis
from paper3 import retrospective_anticipation_design as design
from paper3.pivot_b_budget import atomic


def test_fixed_full_inventory_determinism_and_matching():
    left, right = design.assignments(), design.assignments()
    assert left == right and len(left) == 16
    assert len({a["id"] for a in left}) == 16
    assert {a["arm"] for a in left} == set(institution.ARMS)
    assert {a["stratum"] for a in left} == set(analysis.STRATA)
    assert sum(a["intended_calls"] for a in left) == 480
    assert analysis.validate(left, {a["id"]: (None, None) for a in left}) == design.FRAME_SEEDS
    for seed in design.FRAME_SEEDS:
        assert len({a["seed_base"] for a in left if a["seed"] == seed}) == 1
    # Returned mutable dictionaries do not contaminate subsequent planned cases.
    left[0]["id"] = "changed-copy"
    assert design.assignments()[0]["id"] != "changed-copy"


@pytest.mark.parametrize("kind", ("frame", "order", "request"))
def test_seed_collision_never_relabels_or_replaces_a_case(tmp_path, kind):
    seed = dict(frame=design.FRAME_SEEDS[0], order=design.ORDER_SEED,
                request=design.DECISION_SEED_BASE + 29)[kind]
    path = tmp_path / "results/paper3/older/manifest.json"
    path.parent.mkdir(parents=True)
    atomic(path, dict(protocol=dict(seed=seed)))
    with pytest.raises(ValueError, match="collision"):
        design.seed_audit(tmp_path)


def test_seed_audit_read_only_and_commits_full_historical_inventory(tmp_path):
    path = tmp_path / "results/paper3/older/calls/action.json"
    path.parent.mkdir(parents=True)
    atomic(path, dict(request=dict(seed=1234)))
    before = path.read_bytes()
    result = design.seed_audit(tmp_path)
    assert result["historical_files"] == 1 and not result["overlap"]
    assert len(result["planned"]) == 63  # 60 paired request slots plus two frames and order.
    assert before == path.read_bytes()
    atomic(path, dict(request=dict(seed=1235)))
    assert design.seed_audit(tmp_path)["inventory_sha256"] != result["inventory_sha256"]


def test_missing_or_unreadable_history_cannot_produce_a_clean_collision_check(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="historical root missing"):
        design.seed_audit(tmp_path)
    (tmp_path / "results/paper3").mkdir(parents=True)
    def inaccessible(path, onerror):
        onerror(PermissionError("fabricated unreadable history"))
    monkeypatch.setattr(design.os, "walk", inaccessible)
    with pytest.raises(PermissionError):
        design.seed_audit(tmp_path)


def test_bound_prices_all_sixteen_and_both_retry_reservations_without_actual_allocation(monkeypatch):
    received = []
    def fake_bound(items, ceiling):
        received.append((deepcopy(items), ceiling))
        return dict(assignments=tuple(asdict(a["game"]) for a in items),
            logical_calls=240, maximum_physical_calls=241, full_reservation_usd="4.0")
    monkeypatch.setattr(design.budget, "block_bound", fake_bound)
    result = design.full_bound()
    assert len(received) == 2 and all(len(rows) == 8 and ceiling == 1 for rows, ceiling in received)
    assert result["logical_calls"] == 480 and result["maximum_physical_calls"] == 482
    assert result["full_reservation_usd"] == "8.0"
    assert not result["allocation_authorized"] and not result["frozen_protocol"]


def test_own_source_freeze_exclusion_requires_exact_external_pin_and_keeps_other_runs(tmp_path):
    from hashlib import sha256
    import json
    current = tmp_path / "results/paper3/current"
    current.mkdir(parents=True)
    record = dict(format="paper3-anticipation-freeze-v1", frame_seed=design.FRAME_SEEDS[0])
    atomic(current / "manifest.json", record)
    protocol = sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    with pytest.raises(ValueError, match="collision"):
        design.seed_audit(tmp_path)
    report = design.seed_audit(tmp_path, current_freeze=current, expected_protocol=protocol)
    assert not report["overlap"] and report["historical_files"] == 0
    with pytest.raises(ValueError, match="external protocol"):
        design.seed_audit(tmp_path, current_freeze=current, expected_protocol="0"*64)
    other = tmp_path / "results/paper3/older"
    other.mkdir()
    atomic(other / "manifest.json", dict(seed=design.FRAME_SEEDS[1]))
    with pytest.raises(ValueError, match="collision"):
        design.seed_audit(tmp_path, current_freeze=current, expected_protocol=protocol)
    with pytest.raises(ValueError, match="historical root"):
        design.seed_audit(tmp_path, current_freeze=tmp_path / "results/paper3", expected_protocol=protocol)
