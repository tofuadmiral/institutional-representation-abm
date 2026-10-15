"""Copied authority, fabricated financial records; never actual allocations."""
from copy import deepcopy
from hashlib import sha256
import json
import multiprocessing
from pathlib import Path

import pytest

from paper3 import retrospective_extended_budget as budget
from paper3.pivot_b_budget import Ledger, atomic

SOURCE = Path(__file__).resolve().parents[1] / "results/paper3/pivot_b_budget"


@pytest.fixture
def ledger(tmp_path):
    for name in budget.AUTHORITY_FILES:
        (tmp_path / name).write_bytes((SOURCE / name).read_bytes())
    (tmp_path / "entries").mkdir()
    atomic(tmp_path / "entries/old-pending.json",
           dict(stage="old", status="reserved", reserved_usd="9"))
    atomic(tmp_path / "entries/old-uncertified.json",
           dict(stage="old", status="settled", reserved_usd=".5", accounted_usd=".5", certified=False))
    return budget.ExtendedLedger(tmp_path)


def test_total_fifteen_not_twenty_seven_and_original_snapshot_still_ten(ledger):
    before = {p.name: p.read_bytes() for p in (ledger.root / "entries").glob("*.json")}
    assert ledger.snapshot()["accounted_usd"] == "9.5"
    assert ledger.snapshot()["remaining_usd"] == "5.50"
    assert Ledger(ledger.root).snapshot()["cap_usd"] == "10.00"
    ledger.allocate("new", "4")
    ledger.reserve("new", "first", "4", "a" * 64)
    assert ledger.snapshot()["accounted_usd"] == "13.5"
    assert ledger.snapshot()["cap_usd"] == "15.00"
    assert Ledger(ledger.root).snapshot()["accounted_usd"] == "13.5"
    assert Ledger(ledger.root).snapshot()["remaining_usd"] == "-3.50"
    assert before == {p.name: p.read_bytes() for p in (ledger.root / "entries").glob("old*.json")}
    assert sha256((ledger.root / "authority.json").read_bytes()).hexdigest() == budget.ORIGINAL_SHA


def test_entire_stage_cap_must_fit_before_allocation(ledger):
    with pytest.raises(ValueError, match="full-stage"):
        ledger.allocate("too-large", "5.51")
    assert not (ledger.root / "stages/too-large.json").exists()
    ledger.allocate("exact", "5.5")
    ledger.reserve("exact", "exact", "5.5", "a" * 64)
    with pytest.raises(ValueError, match="admission"):
        ledger.reserve("exact", "extra", ".01", "b" * 64)
    assert ledger.snapshot()["remaining_usd"] == "0.00"


def test_reservation_guards_recheck_combined_stage_and_total_used(ledger):
    ledger.allocate("one", "4")
    with pytest.raises(ValueError, match="full-stage"):
        ledger.allocate("too-many", "4")  # Cannot earmark the same balance twice.
    ledger.allocate("two", "1.5")
    ledger.reserve("one", "one", "4", "a" * 64)
    with pytest.raises(ValueError, match="admission"):
        ledger.reserve("two", "two", "4", "b" * 64)
    assert ledger.snapshot()["accounted_usd"] == "13.5"
    with pytest.raises(ValueError, match="admission"):
        ledger.reserve("one", "over-stage", ".1", "c" * 64)


def test_uncertified_cannot_release_own_or_old_reservations(ledger):
    ledger.allocate("new", "1")
    ledger.reserve("new", "own", ".5", "a" * 64)
    with pytest.raises(ValueError, match="cannot be released"):
        ledger.settle("own", ".1", False, "b" * 64)
    ledger.settle("own", ".5", False, "b" * 64)
    assert ledger.snapshot()["accounted_usd"] == "10.0"
    assert ledger.snapshot()["pending"] == 1
    assert ledger.snapshot()["uncertified"] == 2
    before = (ledger.root / "entries/old-pending.json").read_bytes()
    with pytest.raises(ValueError):
        ledger.settle("old-pending", "0", True, "c" * 64)
    assert (ledger.root / "entries/old-pending.json").read_bytes() == before


def test_certified_releases_only_own_entry_and_exact_stage_scope_can_be_shared(ledger):
    ledger.allocate("new", "1")
    ledger.reserve("new", "own", ".5", "a" * 64)
    shared = budget.ExtendedLedger(ledger.root, stage_pins=ledger.stage_pins())
    shared.settle("own", ".1", True, "b" * 64)
    assert shared.snapshot()["accounted_usd"] == "9.6"
    assert shared.snapshot()["pending"] == 1
    assert shared.snapshot()["uncertified"] == 1
    with pytest.raises(ValueError, match="already recorded"):
        ledger.settle("own", "0", True, "b" * 64)
    with pytest.raises(ValueError, match="already admitted"):
        ledger.reserve("new", "own", ".5", "a" * 64)


def test_above_bound_charge_is_retained_and_prevents_further_admission(ledger):
    ledger.allocate("new", "1")
    ledger.reserve("new", "own", ".5", "a" * 64)
    ledger.settle("own", "7", False, "b" * 64)
    assert ledger.snapshot()["accounted_usd"] == "16.5"
    with pytest.raises(ValueError, match="admission"):
        ledger.reserve("new", "next", ".1", "c" * 64)


@pytest.mark.parametrize("path", budget.AUTHORITY_FILES)
def test_authority_mutation_after_initialization_stops_all_transactions(ledger, path):
    ledger.allocate("new", "1")
    target = ledger.root / path
    data = json.loads(target.read_text())
    data["credit_purchases_authorized"] = True
    target.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="authority"):
        ledger.snapshot()
    with pytest.raises(ValueError, match="authority"):
        ledger.reserve("new", "own", ".5", "a" * 64)
    with pytest.raises(ValueError, match="authority"):
        budget.ExtendedLedger(ledger.root)


@pytest.mark.parametrize("mutation", ("cap", "stage", "prior_change", "prior_delete", "extension"))
def test_pinned_scope_and_pre_stage_inventory_immutable(ledger, mutation):
    ledger.allocate("new", "1")
    path = ledger.root / "stages/new.json"
    if mutation.startswith("prior"):
        path = ledger.root / "entries/old-pending.json"
        if mutation == "prior_delete":
            path.unlink()
        else:
            data = json.loads(path.read_text())
            data["reserved_usd"] = "0"
            path.write_text(json.dumps(data))
    else:
        data = json.loads(path.read_text())
        data[dict(cap="cap_usd", stage="stage", extension="authority_extension_sha256")[mutation]] = "changed"
        path.write_text(json.dumps(data))
    with pytest.raises((ValueError, FileNotFoundError)):
        ledger.reserve("new", "own", ".1", "a" * 64)


def test_cannot_claim_old_stage_or_adopt_scope_without_explicit_hash(ledger):
    (ledger.root / "stages").mkdir()
    atomic(ledger.root / "stages/old.json", dict(stage="old", cap_usd="1"))
    with pytest.raises(ValueError, match="migrate"):
        ledger.allocate("old", "1")
    ledger.allocate("new", "1")
    other = budget.ExtendedLedger(ledger.root)
    with pytest.raises(ValueError, match="scope"):
        other.reserve("new", "unscoped", ".1", "a" * 64)
    with pytest.raises(ValueError, match="migrate"):
        ledger.allocate("new", "1")


@pytest.mark.parametrize("maximum", ("-1", "NaN", "Infinity", "0"))
def test_invalid_reservations_fail_before_writing_entry(ledger, maximum):
    ledger.allocate("new", "1")
    with pytest.raises((ValueError, ArithmeticError)):
        ledger.reserve("new", "bad", maximum, "a" * 64)
    assert not (ledger.root / "entries/bad.json").exists()


def test_interrupted_write_prevents_admission(ledger):
    ledger.allocate("new", "1")
    (ledger.root / "entries/partial.partial").write_text("fabricated incomplete")
    with pytest.raises(ValueError, match="interrupted"):
        ledger.reserve("new", "own", ".1", "a" * 64)


def reserve_in_process(root, pins, index):
    obj = budget.ExtendedLedger(root, stage_pins=pins)
    try:
        obj.reserve("parallel", f"p{index}", ".4", sha256(str(index).encode()).hexdigest())
        return True
    except ValueError:
        return False


def test_process_shared_admission_cannot_overspend_current_total(ledger):
    ledger.allocate("parallel", "5.5")
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(4) as pool:
        admitted = pool.starmap(reserve_in_process, [
            (str(ledger.root), deepcopy(ledger.stage_pins()), i) for i in range(20)])
    assert sum(admitted) == 13
    assert ledger.snapshot()["accounted_usd"] == "14.7"
    assert ledger.snapshot()["pending"] == 14
    assert ledger.snapshot()["uncertified"] == 1


def test_unspent_caps_remain_earmarked_until_append_only_terminal_closure(ledger):
    ledger.allocate("new", "4")
    stage_before = (ledger.root / "stages/new.json").read_bytes()
    ledger.reserve("new", "own", ".5", "a" * 64)
    with pytest.raises(ValueError, match="unresolved"):
        ledger.close("new", "b" * 64)
    ledger.settle("own", ".1", True, "b" * 64)
    snap = ledger.snapshot()
    assert snap["accounted_usd"] == "9.6"
    assert snap["unspent_active_stage_caps_usd"] == "3.9"
    assert snap["available_for_new_stages_usd"] == "1.50"
    with pytest.raises(ValueError, match="full-stage"):
        ledger.allocate("too-soon", "2")
    ledger.close("new", "c" * 64)
    snap = ledger.snapshot()
    assert snap["unspent_active_stage_caps_usd"] == "0"
    assert snap["available_for_new_stages_usd"] == "5.40"
    assert (ledger.root / "stages/new.json").read_bytes() == stage_before
    ledger.allocate("next", "5")
    with pytest.raises(ValueError, match="closed"):
        ledger.reserve("new", "after-terminal", ".1", "d" * 64)
    with pytest.raises(ValueError, match="already closed"):
        ledger.close("new", "e" * 64)


def allocate_in_process(root, index):
    obj = budget.ExtendedLedger(root)
    try:
        obj.allocate(f"block{index}", "4")
        return True
    except ValueError:
        return False


def test_concurrent_whole_block_admission_cannot_earmark_same_money_twice(ledger):
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(4) as pool:
        admitted = pool.starmap(allocate_in_process, [(str(ledger.root), i) for i in range(4)])
    assert sum(admitted) == 1
    snap = ledger.snapshot()
    assert snap["accounted_usd"] == "9.5"
    assert snap["unspent_active_stage_caps_usd"] == "4"
    assert snap["available_for_new_stages_usd"] == "1.50"
