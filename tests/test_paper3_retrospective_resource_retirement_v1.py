"""Copied actual historical evidence; fabricated retirement stays in PRIVATE temp.

No real ledger mutation, paid call, provider qualification or study launch.
"""
from copy import deepcopy
from pathlib import Path
import json
import shutil

import pytest

from paper3 import retrospective_resource_budget_v1 as budget
from paper3 import retrospective_resource_retirement_v1 as retirement
from paper3 import retrospective_recovery_budget_v2 as old
from paper3.pivot_b_budget import atomic

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def copied(tmp_path_factory):
    root = tmp_path_factory.mktemp("private-copy-total19-ledger") / "ledger"
    shutil.copytree(REPO / "paper3/data/pivot_b_retrospective_late_context_bounded_gate_v1/ledger", root)
    actual = REPO / "results/paper3/pivot_b_budget" / retirement.DIRECTORY / (retirement.STAGE + ".json")
    if actual.exists():
        destination = root / retirement.DIRECTORY / actual.name
        destination.parent.mkdir(exist_ok=True)
        shutil.copy2(actual, destination)
    entries = retirement.inventory(root)
    assert len(entries) == retirement.ENTRY_COUNT
    assert retirement.inventory_sha(entries) == retirement.ENTRIES_SHA
    (root / retirement.DIRECTORY).mkdir(exist_ok=True)
    path = root / retirement.DIRECTORY / (retirement.STAGE + ".json")
    if path.exists():
        # Later readiness runs copy the genuine completed disposition, rather
        # than depending on the live repository still being pre-retirement.
        record = json.loads(path.read_text())
        retirement.verify_certificate(root, record)
    else:
        record = retirement.certificate(entries, 1792310400.0)
        atomic(path, record)  # PRIVATE fabricated evidence only.
    return root, path, record


def test_only_approved_unused_B1_released_and_old_views_stay_frozen(copied):
    root, path, _ = copied
    before = retirement.inventory(root)
    pins = {retirement.STAGE: old._digest(path)}
    unscoped = budget.RecoveryLedger(root).snapshot()
    scoped = budget.RecoveryLedger(root, retirement_pins=pins).snapshot()
    historical = old.RecoveryLedger(root, retirement_pins=retirement.old_retirement_pins(root)).snapshot()
    assert unscoped["cap_usd"] == scoped["cap_usd"] == "19.00"
    assert historical["cap_usd"] == "17.00"
    assert unscoped["unspent_active_stage_caps_usd"] == "4.68239488"
    assert scoped["unspent_active_stage_caps_usd"] == "0.29045544"
    assert scoped["available_for_new_stages_usd"] == "9.443759709"
    assert unscoped["accounted_usd"] == scoped["accounted_usd"] == historical["accounted_usd"] == "9.265784851"
    assert scoped["pending"] == historical["pending"] == 4
    assert scoped["uncertified"] == historical["uncertified"] == 299
    assert retirement.inventory(root) == before
    assert not (root / old.CLOSURES / (retirement.STAGE + ".json")).exists()


def test_full_nine_dollar_admission_requires_the_pinned_disposition(copied, tmp_path):
    source, _, _ = copied
    root = tmp_path / "private-admission"
    shutil.copytree(source, root)
    with pytest.raises(ValueError, match="admission"):
        budget.RecoveryLedger(root).allocate_group("whole", {"b0": "4.5", "b1": "4.5"})
    path = root / retirement.DIRECTORY / (retirement.STAGE + ".json")
    ledger = budget.RecoveryLedger(root, retirement_pins={retirement.STAGE: old._digest(path)})
    before = retirement.inventory(root)
    ledger.allocate_group("whole", {"b0": "4.5", "b1": "4.5"})
    assert ledger.snapshot()["available_for_new_stages_usd"] == "0.443759709"
    assert retirement.inventory(root) == before


@pytest.mark.parametrize("field", (
    "stage", "stage_sha256", "group_sha256", "old_protocol",
    "terminal_block0_sha256", "closure_block0_sha256", "original_archive_sha256",
    "recomputed_original_report_sha256", "human_authorization_sha256",
    "retired_unused_cap_usd", "incurred_reservations_released", "old_run_reopened",
    "old_files_modified", "launch_authorized", "actual_isolated_replay"))
def test_certificate_is_not_a_generic_release_or_cached_pass(copied, field):
    root, _, value = copied
    record = deepcopy(value)
    record[field] = "changed"
    with pytest.raises(ValueError, match="scope"):
        retirement.verify_certificate(root, record)


def test_boolean_coercion_and_nonfinite_timestamps_fail(copied):
    root, _, value = copied
    record = deepcopy(value)
    record["launch_authorized"] = 0
    with pytest.raises(ValueError, match="scope"):
        retirement.verify_certificate(root, record)
    record["retired_at_unix"] = float("nan")
    with pytest.raises(ValueError, match="timestamp"):
        retirement.verify_certificate(root, record)


def test_any_incurred_entry_change_rejects_disposition(copied):
    root, _, value = copied
    path = root / "entries" / next(iter(value["original_entries"]))
    data = path.read_bytes()
    try:
        row = json.loads(data)
        row["reserved_usd"] = "0"
        path.write_text(json.dumps(row))
        with pytest.raises(ValueError, match="incurred"):
            retirement.verify_certificate(root, value)
    finally:
        path.write_bytes(data)


def test_wrong_stage_pin_and_repeat_retirement_rejected(copied, monkeypatch):
    root, path, _ = copied
    with pytest.raises(ValueError, match="only the directly approved"):
        budget.RecoveryLedger(root, retirement_pins={"wrong": old._digest(path)})
    # Actual retire entrypoint sees an existing disposition BEFORE replay/write.
    private_repo = root.parent / "private-repo"
    (private_repo / "results/paper3").mkdir(parents=True)
    (private_repo / "results/paper3/pivot_b_budget").symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="already retired"):
        retirement.retire(private_repo)


def test_historical_stage_cannot_be_closed_or_reserved_by_total19(copied):
    root, path, _ = copied
    ledger = budget.RecoveryLedger(root, retirement_pins={retirement.STAGE: old._digest(path)})
    for operation in (
        lambda: ledger.close(retirement.STAGE, "a"*64),
        lambda: ledger.reserve(retirement.STAGE, "wrong", ".1", "a"*64),
        lambda: ledger.allocate_group("collision", {retirement.STAGE: "1"})):
        with pytest.raises(ValueError):
            operation()


def test_pid_visibility_failure_never_means_absence(monkeypatch):
    def alive(*_):
        return None
    monkeypatch.setattr(retirement.original_retirement.os, "kill", alive)
    with pytest.raises(ValueError, match="process exists"):
        retirement._pid_gone(1)
    def denied(*_):
        raise PermissionError("fabricated")
    monkeypatch.setattr(retirement.original_retirement.os, "kill", denied)
    with pytest.raises(PermissionError):
        retirement._pid_gone(1)


def test_test_copy_never_enters_actual_budget(copied):
    root, path, _ = copied
    assert root.resolve() != (REPO / "results/paper3/pivot_b_budget").resolve()
    assert path.resolve() != (REPO / "results/paper3/pivot_b_budget" / retirement.DIRECTORY /
                              (retirement.STAGE + ".json")).resolve()
