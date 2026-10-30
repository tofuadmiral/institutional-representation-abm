"""Read-only retirement-scope tests; no canonical ledger mutation or API call."""
from copy import deepcopy
from pathlib import Path

import pytest

from paper3 import retrospective_deepinfra_retirement_v2 as retirement

ROOT = Path(__file__).resolve().parents[1] / "results/paper3/pivot_b_budget"


def test_6910_prior_charges_and_exact_human_unused_only_scope():
    entries = retirement.inventory(ROOT)
    assert len(entries) == retirement.ENTRY_COUNT == 6910
    record = retirement.certificate(entries, 0)
    assert retirement.verify_certificate(ROOT, record) == record
    assert not record["incurred_reservations_released"]
    assert not record["old_run_reopened"]
    assert record["retired_unused_cap_usd"] == "4.39135184"


@pytest.mark.parametrize("field,value", [
    ("stage", "wrong"), ("retired_unused_cap_usd", "5"),
    ("original_archive_sha256", "0" * 64),
    ("human_authorization_sha256", "0" * 64),
    ("incurred_reservations_released", True), ("retired_at_unix", -1),
])
def test_changed_scope_or_evidence_rejected(field, value):
    record = retirement.certificate(retirement.inventory(ROOT), 0)
    record[field] = value
    with pytest.raises(ValueError):
        retirement.verify_certificate(ROOT, record)


def test_dropped_pending_charge_is_not_free_budget():
    record = deepcopy(retirement.certificate(retirement.inventory(ROOT), 0))
    record["original_entries"].pop(next(iter(record["original_entries"])))
    with pytest.raises(ValueError):
        retirement.verify_certificate(ROOT, record)
