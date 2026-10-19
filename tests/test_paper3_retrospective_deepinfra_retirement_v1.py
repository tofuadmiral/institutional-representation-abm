"""Read-only actual-baseline validation; never writes a retirement or launches."""
from copy import deepcopy
from pathlib import Path

import pytest

from paper3 import retrospective_deepinfra_retirement_v1 as retirement


ROOT = Path(__file__).resolve().parents[1] / "results/paper3/pivot_b_budget"


def test_exact_current_baseline_and_explicit_unused_only_authority():
    retirement.authorization(ROOT)
    entries = retirement.inventory(ROOT)
    assert len(entries) == 6787 and retirement.inventory_sha(entries) == retirement.ENTRIES_SHA
    record = retirement.certificate(entries, 0)
    assert retirement.verify_certificate(ROOT, record) == record
    assert record["incurred_reservations_released"] is False
    assert record["old_run_reopened"] is False and record["old_files_modified"] is False
    assert record["retired_unused_cap_usd"] == "4.39399734"
    assert not record["launch_authorized"]


@pytest.mark.parametrize("mutation", ["stage", "amount", "entry", "proof", "authority", "negative_time"])
def test_changed_scope_evidence_or_cost_inventory_rejected(mutation):
    record = retirement.certificate(retirement.inventory(ROOT), 0)
    broken = deepcopy(record)
    if mutation == "stage":
        broken["stage"] = retirement.GROUP + "-0"
    elif mutation == "amount":
        broken["retired_unused_cap_usd"] = "9"
    elif mutation == "entry":
        broken["original_entries"].pop(next(iter(broken["original_entries"])))
    elif mutation == "proof":
        broken["actual_isolated_replay"]["report_sha256"] = "0" * 64
    elif mutation == "authority":
        broken["human_authorization_sha256"] = "0" * 64
    else:
        broken["retired_at_unix"] = -1
    with pytest.raises(ValueError):
        retirement.verify_certificate(ROOT, broken)
