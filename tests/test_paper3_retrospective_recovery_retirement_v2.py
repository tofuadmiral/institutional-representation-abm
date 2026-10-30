"""Copied public ledger evidence; fabricated disposition NEVER enters real results."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from paper3 import retrospective_extended_budget as legacy
from paper3 import retrospective_recovery_budget_v2 as budget
from paper3 import retrospective_recovery_retirement_v2 as retirement
from paper3.pivot_b_budget import atomic

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def copied(tmp_path_factory):
    root = tmp_path_factory.mktemp("public-copied-ledger") / "ledger"
    shutil.copytree(REPO / "paper3/data/pivot_b_retrospective_anticipation_v1_batch0/ledger", root)
    (root / budget.EXTENSION_FILE).write_bytes(
        (REPO / "results/paper3/pivot_b_budget" / budget.EXTENSION_FILE).read_bytes())
    entries = retirement.inventory(root)
    assert retirement.inventory_sha(entries) == retirement.ENTRIES_SHA
    record = retirement.certificate(entries, 1791820000.0)
    (root / retirement.DIRECTORY).mkdir()
    path = root / retirement.DIRECTORY / (retirement.STAGE + ".json")
    atomic(path, record)
    return root, path, record


def test_only_pinned_disposition_changes_new_adapter_unused_cap(copied):
    root, path, _ = copied
    before = {p.relative_to(root): p.read_bytes() for folder in ("stages", "stage_groups", "entries")
              for p in (root / folder).glob("*.json")}
    original = legacy.ExtendedLedger(root).snapshot()
    unscoped = budget.RecoveryLedger(root).snapshot()
    pins = {retirement.STAGE: legacy._digest(path)}
    after = budget.RecoveryLedger(root, retirement_pins=pins).snapshot()
    assert original["unspent_active_stage_caps_usd"] == unscoped["unspent_active_stage_caps_usd"] == "3.76458102"
    assert after["unspent_active_stage_caps_usd"] == "0E-8"
    for name in ("entries", "accounted_usd", "pending", "uncertified"):
        assert original[name] == unscoped[name] == after[name]
    assert after["available_for_new_stages_usd"] == "10.171410909"
    assert legacy.ExtendedLedger(root).snapshot() == original
    for relative, data in before.items():
        assert (root / relative).read_bytes() == data


@pytest.mark.parametrize("field", ("stage", "stage_sha256", "group_sha256", "old_protocol",
    "terminal_block0_sha256", "closure_block0_sha256", "original_archive_sha256",
    "recomputed_original_report_sha256", "human_authorization_sha256", "retired_unused_cap_usd",
    "incurred_reservations_released", "old_run_reopened", "launch_authorized"))
def test_retirement_scope_is_not_a_generic_cap_release(copied, field):
    root, _, record = copied
    changed = deepcopy(record)
    changed[field] = "changed"
    with pytest.raises(ValueError, match="scope"):
        retirement.verify_certificate(root, changed)


def test_bool_coercion_and_nonfinite_clock_rejected(copied):
    root, _, record = copied
    changed = deepcopy(record)
    changed["launch_authorized"] = 0
    with pytest.raises(ValueError, match="scope"):
        retirement.verify_certificate(root, changed)
    changed = deepcopy(record)
    changed["retired_at_unix"] = float("nan")
    with pytest.raises(ValueError, match="timestamp"):
        retirement.verify_certificate(root, changed)


def test_forged_empty_history_or_changed_actual_reservation_rejected(copied):
    root, path, record = copied
    changed = deepcopy(record)
    changed["original_entries"] = {}
    with pytest.raises(ValueError, match="scope"):
        retirement.verify_certificate(root, changed)
    entry = root / "entries" / next(iter(record["original_entries"]))
    original = entry.read_bytes()
    try:
        data = json.loads(original)
        data["reserved_usd"] = "0"
        entry.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="reservation"):
            retirement.verify_record(root, legacy._digest(path))
    finally:
        entry.write_bytes(original)


def test_unrelated_stage_cannot_be_approved_via_pins(copied):
    root, path, _ = copied
    with pytest.raises(ValueError, match="only the directly approved"):
        budget.RecoveryLedger(root, retirement_pins={"anything": legacy._digest(path)})


def test_permission_or_live_pid_not_treated_as_process_absence(monkeypatch):
    def alive(pid, signal):
        return None
    monkeypatch.setattr(retirement.os, "kill", alive)
    with pytest.raises(ValueError, match="process exists"):
        retirement._pid_gone(1)
    def denied(pid, signal):
        raise PermissionError("fabricated")
    monkeypatch.setattr(retirement.os, "kill", denied)
    with pytest.raises(PermissionError):
        retirement._pid_gone(1)
    def gone(pid, signal):
        raise ProcessLookupError("fabricated")
    monkeypatch.setattr(retirement.os, "kill", gone)
    assert retirement._pid_gone(1) is None


def test_real_disposition_creation_is_not_exercised_by_these_fixtures(copied):
    # The test-created certificate has real public evidence pins, but is not a
    # production audit or authorization to write the live ledger. No real write.
    _, path, _ = copied
    assert "results/paper3/pivot_b_budget" not in str(path)
    assert path.resolve() != (REPO / "results/paper3/pivot_b_budget" / retirement.DIRECTORY /
                              (retirement.STAGE + ".json")).resolve()
