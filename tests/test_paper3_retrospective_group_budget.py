"""Copied authority/fabricated allocation only, no actual budget changes."""
from copy import deepcopy
from decimal import Decimal
import multiprocessing

import pytest

from paper3 import retrospective_extended_budget as budget
from paper3.pivot_b_budget import atomic
from tests import test_paper3_retrospective_extended_budget as copied


@pytest.fixture
def ledger(tmp_path):
    return copied.ledger.__wrapped__(tmp_path)


def test_entire_study_is_admitted_before_either_block_and_cannot_restart(ledger):
    prior = {p.name:p.read_bytes() for p in (ledger.root / "entries").glob("*.json")}
    result = ledger.allocate_group("whole", {"block-0":"3", "block-1":"2.5"})
    assert len(result["stage_pins"]) == 2
    snap = ledger.snapshot()
    assert Decimal(snap["unspent_active_stage_caps_usd"]) == Decimal("5.5")
    assert Decimal(snap["available_for_new_stages_usd"]) == 0
    ledger.reserve("block-0", "first", ".1", "a"*64)
    assert Decimal(ledger.snapshot()["available_for_new_stages_usd"]) == 0
    with pytest.raises(ValueError, match="restart"):
        ledger.allocate_group("whole", {"block-0":"3", "block-1":"2.5"})
    assert prior == {p.name:p.read_bytes() for p in (ledger.root / "entries").glob("old*.json")}


def test_inadmissible_combined_budget_creates_neither_group_nor_stages(ledger):
    with pytest.raises(ValueError, match="whole-group total admission"):
        ledger.allocate_group("too-large", {"a":"3", "b":"2.51"})
    assert not (ledger.root / "stage_groups").exists()
    assert not (ledger.root / "stages").exists()


def test_crash_materializing_second_block_preserves_both_caps_admits_zero_and_never_repairs(ledger, monkeypatch):
    ordinary = budget.atomic
    def interrupted(path, record):
        if path.name == "b.json":
            raise OSError("fabricated interrupted materialization")
        ordinary(path, record)
    monkeypatch.setattr(budget, "atomic", interrupted)
    with pytest.raises(OSError):
        ledger.allocate_group("whole", {"a":"3", "b":"2.5"})
    assert not (ledger.root / "stages/b.json").exists()
    assert Decimal(ledger.snapshot()["unspent_active_stage_caps_usd"]) == Decimal("5.5")
    assert Decimal(ledger.snapshot()["available_for_new_stages_usd"]) == 0
    with pytest.raises(ValueError, match="incomplete whole-group"):
        ledger.reserve("a", "no-spending", ".1", "a"*64)
    with pytest.raises(ValueError, match="restart"):
        ledger.allocate_group("whole", {"a":"3", "b":"2.5"})
    with pytest.raises(ValueError, match="restart"):
        ledger.allocate("b", ".1")
    with pytest.raises(ValueError, match="restart"):
        ledger.allocate_group("different", {"b":".1", "new":".1"})
    assert not (ledger.root / "entries/no-spending.json").exists()


def test_audit_can_reopen_complete_group_with_explicit_original_stage_pins(ledger):
    record = ledger.allocate_group("whole", {"a":"2", "b":"2"})
    replay = budget.ExtendedLedger(ledger.root, stage_pins=record["stage_pins"])
    replay.reserve("b", "second", ".2", "b"*64)
    assert replay.snapshot() == ledger.snapshot()


def test_closing_one_audited_block_never_releases_other_block_or_unknown_costs(ledger):
    ledger.allocate_group("whole", {"a":"2", "b":"2"})
    ledger.reserve("a", "a-one", ".2", "a"*64)
    ledger.settle("a-one", ".2", False, "b"*64)
    ledger.close("a", "c"*64)
    snap = ledger.snapshot()
    assert Decimal(snap["unspent_active_stage_caps_usd"]) == Decimal("2")
    assert Decimal(snap["accounted_usd"]) == Decimal("6.7")
    assert snap["pending"] == 1 and snap["uncertified"] == 2
    ledger.reserve("b", "b-pending", ".2", "b"*64)
    with pytest.raises(ValueError, match="unresolved"):
        ledger.close("b", "c"*64)


@pytest.mark.parametrize("mutation", ("group_deleted", "stage_changed", "group_cap"))
def test_missing_or_changed_group_evidence_cannot_release_commitments(ledger, mutation):
    ledger.allocate_group("whole", {"a":"2", "b":"2"})
    path = ledger.root / "stage_groups/whole.json"
    if mutation == "group_deleted":
        path.unlink()  # FABRICATED private ledger only.
    elif mutation == "stage_changed":
        stage = ledger.root / "stages/b.json"
        record = deepcopy(budget.json.loads(stage.read_text()))
        record["cap_usd"] = ".1"
        atomic(stage, record)
    else:
        record = deepcopy(budget.json.loads(path.read_text()))
        record["cap_usd"] = ".1"
        atomic(path, record)
    with pytest.raises((ValueError, FileNotFoundError)):
        ledger.snapshot()


def worker(root, group, queue):
    try:
        ledger = budget.ExtendedLedger(root)
        ledger.allocate_group(group, {group+"-0":"1.5", group+"-1":"1.5"})
        queue.put("admitted")
    except ValueError:
        queue.put("denied")


def test_concurrent_full_studies_cannot_earmark_the_same_remaining_balance(ledger):
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = [context.Process(target=worker, args=(ledger.root, group, queue)) for group in ("x", "y")]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0
    assert sorted(queue.get(timeout=3) for _ in processes) == ["admitted", "denied"]
    assert Decimal(ledger.snapshot()["unspent_active_stage_caps_usd"]) == Decimal("3")
