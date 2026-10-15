"""Copied genuine authorities, fabricated money/actions; no real allocation."""
from copy import deepcopy
from hashlib import sha256
import json
import multiprocessing
from pathlib import Path

import pytest

from paper3 import retrospective_extended_budget as legacy
from paper3 import retrospective_recovery_budget_v2 as budget
from paper3.pivot_b_budget import Ledger, atomic

SOURCE = Path(__file__).resolve().parents[1] / "results/paper3/pivot_b_budget"


@pytest.fixture
def ledger(tmp_path):
    for name in budget.AUTHORITY_FILES:
        (tmp_path / name).write_bytes((SOURCE / name).read_bytes())
    (tmp_path / "entries").mkdir()
    atomic(tmp_path / "entries/old-pending.json",
           dict(stage="old", status="reserved", reserved_usd="9"))
    atomic(tmp_path / "entries/old-uncertified.json", dict(stage="old", status="settled",
           reserved_usd=".5", accounted_usd=".5", certified=False))
    return budget.RecoveryLedger(tmp_path)


def test_extension_not_new_allowance_and_old_views_unchanged(ledger):
    before = {p.name: p.read_bytes() for p in (ledger.root / "entries").glob("*.json")}
    assert ledger.snapshot()["cap_usd"] == "17.00"
    assert ledger.snapshot()["available_for_new_stages_usd"] == "7.50"
    assert legacy.ExtendedLedger(ledger.root).snapshot()["cap_usd"] == "15.00"
    assert Ledger(ledger.root).snapshot()["cap_usd"] == "10.00"
    ledger.allocate_group("new", {"one": "4", "two": "3.5"})
    ledger.reserve("one", "new-1", "4", "a" * 64)
    ledger.reserve("two", "new-2", "3.5", "b" * 64)
    assert ledger.snapshot()["accounted_usd"] == "17.0"
    assert ledger.snapshot()["available_for_new_stages_usd"] == "0.00"
    for name, data in before.items():
        assert (ledger.root / "entries" / name).read_bytes() == data


def test_old_unused_commitment_stays_earmarked_not_silently_abandoned(ledger):
    old = legacy.ExtendedLedger(ledger.root)
    old.allocate_group("old-group", {"old-block": "4"})
    frozen = {p.relative_to(ledger.root): p.read_bytes()
              for folder in ("stage_groups", "stages") for p in (ledger.root / folder).glob("*.json")}
    assert ledger.snapshot()["available_for_new_stages_usd"] == "3.50"
    with pytest.raises(ValueError, match="admission"):
        ledger.allocate_group("new", {"new-block": "3.51"})
    with pytest.raises((ValueError, FileNotFoundError)):
        ledger.close("old-block", "c" * 64)
    assert not (ledger.root / budget.GROUPS / "new.json").exists()
    for path, data in frozen.items():
        assert (ledger.root / path).read_bytes() == data


def test_new_account_does_not_reset_costs_or_release_old_reservations(ledger):
    ledger.allocate("new", "1")
    before = (ledger.root / "entries/old-pending.json").read_bytes()
    with pytest.raises((ValueError, FileNotFoundError)):
        ledger.settle("old-pending", "0", True, "a" * 64)
    ledger.reserve("new", "own", ".5", "a" * 64)
    with pytest.raises(ValueError, match="cannot be released"):
        ledger.settle("own", ".1", False, "b" * 64)
    ledger.settle("own", ".5", False, "b" * 64)
    assert ledger.snapshot()["accounted_usd"] == "10.0"
    assert ledger.snapshot()["pending"] == 1
    assert ledger.snapshot()["uncertified"] == 2
    assert (ledger.root / "entries/old-pending.json").read_bytes() == before


@pytest.mark.parametrize("path", budget.AUTHORITY_FILES)
def test_whole_authority_chain_rechecked_on_each_transaction(ledger, path):
    ledger.allocate("new", "1")
    target = ledger.root / path
    data = json.loads(target.read_text())
    data["credit_purchases_authorized"] = True
    target.write_text(json.dumps(data))
    for operation in (ledger.snapshot, lambda: ledger.reserve("new", "r", ".1", "a" * 64),
                      lambda: budget.RecoveryLedger(ledger.root)):
        with pytest.raises(ValueError, match="authority"):
            operation()


def test_prior_entries_frozen_and_stage_pins_not_optional(ledger):
    ledger.allocate("new", "1")
    with pytest.raises(ValueError, match="scope"):
        budget.RecoveryLedger(ledger.root).reserve("new", "r", ".1", "a" * 64)
    shared = budget.RecoveryLedger(ledger.root, stage_pins=ledger.stage_pins())
    target = ledger.root / "entries/old-pending.json"
    data = json.loads(target.read_text())
    data["reserved_usd"] = "0"
    target.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="prior ledger"):
        shared.reserve("new", "r", ".1", "a" * 64)
    with pytest.raises(ValueError, match="prior ledger"):
        shared.snapshot()


def test_group_partial_materialization_retains_all_money_admits_nothing(ledger):
    ledger.allocate_group("whole", {"one": "4", "two": "3"})
    (ledger.root / budget.STAGES / "two.json").unlink()
    assert ledger.snapshot()["unspent_active_stage_caps_usd"] == "7"
    with pytest.raises(ValueError, match="materialization"):
        ledger.reserve("one", "r", ".1", "a" * 64)
    with pytest.raises(ValueError, match="restart"):
        ledger.allocate_group("whole", {"one": "4", "two": "3"})


@pytest.mark.parametrize("folder", (budget.STAGES, budget.GROUPS))
def test_changed_stage_or_group_fails_closed(ledger, folder):
    ledger.allocate("new", "1")
    path = ledger.root / folder / "new.json"
    data = json.loads(path.read_text())
    data["cap_usd"] = "17"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        ledger.reserve("new", "r", ".1", "a" * 64)


def test_no_namespace_migration_or_historical_stage_collision(ledger):
    old = legacy.ExtendedLedger(ledger.root)
    old.allocate("old-block", "1")
    with pytest.raises(ValueError, match="migrate"):
        ledger.allocate_group("new", {"old-block": "1"})
    ledger.allocate("new", "1")
    assert not (ledger.root / "stages/new.json").exists()
    with pytest.raises((ValueError, FileNotFoundError)):
        old.reserve("new", "wrong-adapter", ".1", "a" * 64)


def test_full_pre_freeze_financial_baseline_must_match(ledger):
    prior = {p.name: budget._digest(p) for p in (ledger.root / "entries").glob("*.json")}
    baseline = dict(prior_entries=prior, accounted_usd="9.5", unused_commitments_usd="0")
    wrong = deepcopy(baseline)
    wrong["accounted_usd"] = "0"
    with pytest.raises(ValueError, match="baseline"):
        ledger.allocate_group("new", {"one": "1"}, expected_baseline=wrong)
    ledger.allocate_group("new", {"one": "1"}, expected_baseline=baseline)


def test_partial_write_blocks_every_admission(ledger):
    (ledger.root / "entries/unfinished.partial").write_text("fabricated")
    with pytest.raises(ValueError, match="interrupted"):
        ledger.allocate("new", "1")


def test_closure_releases_only_unused_new_cap_and_retains_uncertified_cost(ledger):
    ledger.allocate("new", "4")
    ledger.reserve("new", "r", ".5", "a" * 64)
    with pytest.raises(ValueError, match="unresolved"):
        ledger.close("new", "b" * 64)
    ledger.settle("r", ".5", False, "b" * 64)
    old_stage = (ledger.root / budget.STAGES / "new.json").read_bytes()
    ledger.close("new", "c" * 64)
    assert ledger.snapshot()["accounted_usd"] == "10.0"
    assert ledger.snapshot()["unspent_active_stage_caps_usd"] == "0"
    assert (ledger.root / budget.STAGES / "new.json").read_bytes() == old_stage
    with pytest.raises(ValueError, match="closed"):
        ledger.reserve("new", "after", ".1", "d" * 64)
    with pytest.raises(ValueError, match="already closed"):
        ledger.close("new", "d" * 64)


def test_above_bound_charge_is_not_clipped(ledger):
    ledger.allocate("new", "1")
    ledger.reserve("new", "r", ".5", "a" * 64)
    ledger.settle("r", "8", False, "b" * 64)
    assert ledger.snapshot()["accounted_usd"] == "17.5"
    with pytest.raises(ValueError, match="admission"):
        ledger.reserve("new", "next", ".1", "c" * 64)


def _allocate(root, index):
    obj = budget.RecoveryLedger(root)
    try:
        obj.allocate("parallel" + str(index), "4")
        return True
    except ValueError:
        return False


def _reserve(root, pins, index):
    obj = budget.RecoveryLedger(root, stage_pins=pins)
    try:
        obj.reserve("parallel", f"r{index}", ".4", sha256(str(index).encode()).hexdigest())
        return True
    except ValueError:
        return False


def test_competing_processes_cannot_double_earmark(ledger):
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        admitted = pool.starmap(_allocate, [(str(ledger.root), i) for i in range(4)])
    assert sum(admitted) == 1
    assert ledger.snapshot()["unspent_active_stage_caps_usd"] == "4"


def test_competing_processes_cannot_overspend(ledger):
    ledger.allocate("parallel", "7.5")
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        admitted = pool.starmap(_reserve, [(str(ledger.root), ledger.stage_pins(), i) for i in range(24)])
    assert sum(admitted) == 18
    assert ledger.snapshot()["accounted_usd"] == "16.7"
