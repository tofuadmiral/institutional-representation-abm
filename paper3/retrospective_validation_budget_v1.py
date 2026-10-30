"""Append-only $21.31 TOTAL authority; every older ledger remains immutable.

Reuse the exact transactional code objects with a distinct prospective namespace.
The complete $19.30 graph is validated/accounted by its original adapter; no
historical uncertainty or unused gate commitment is retired by this adapter.
"""
from decimal import Decimal

from paper3 import retrospective_deepinfra_budget_v2 as previous
from paper3 import retrospective_deepinfra_freeze_v2 as historical
from paper3 import retrospective_receipt_recovery_v1 as billing
from paper3.pivot_b_budget import Ledger

TOTAL_CAP = Decimal("21.31")
EXTENSION_FILE = "authority_extension_2026_10_27.json"
EXTENSION_SHA = "ab8118271b0dce1449b826f1d4b474b8c51021c2eb822c9f8ae3b1660cae0a8e"
ORIGINAL_SHA = previous.ORIGINAL_SHA
STAGES = "validation_stages_v1"
GROUPS = "validation_stage_groups_v1"
CLOSURES = "validation_stage_closures_v1"
AUTHORITY_FILES = (*previous.AUTHORITY_FILES, EXTENSION_FILE)
atomic = previous.atomic


def transaction(function):
    return billing.bind(function, TOTAL_CAP=TOTAL_CAP, EXTENSION_SHA=EXTENSION_SHA,
                        STAGES=STAGES, GROUPS=GROUPS, CLOSURES=CLOSURES,
                        legacy=previous)


class ValidationLedger(previous.RecoveryLedger):
    def __init__(self, root, *, stage_pins=None):
        Ledger.__init__(self, root)
        self._legacy = previous.RecoveryLedger(
            root, retirement_pins=historical.RETIREMENT_PINS)
        self._stage_pins = dict(stage_pins or {})
        self._retirement_pins = {}  # All approved OLD dispositions stay in _legacy.
        for stage, digest in self._stage_pins.items():
            previous.identifier(stage)
            previous._sha(digest)
        self._check_authority()

    def _check_authority(self):
        self._legacy._check_authority()
        path = self.root / EXTENSION_FILE
        if previous._digest(path) != EXTENSION_SHA:
            raise ValueError("pinned $21.31 authority changed")
        record = previous.json.loads(path.read_text())
        if not (record["budget_id"] == previous.BUDGET_ID
                and record["original_authority_sha256"] == ORIGINAL_SHA
                and record["previous_extension_sha256"] == previous.EXTENSION_SHA
                and previous.amount(record["previous_total_cap_usd"]) == previous.TOTAL_CAP
                and previous.amount(record["new_total_cap_usd"]) == TOTAL_CAP
                and record["credit_purchases_authorized"] is False
                and record["old_protocols_modified"] is False):
            raise ValueError("append-only cumulative authority chain changed")

    _binding = transaction(previous.RecoveryLedger._binding)
    _group = transaction(previous.RecoveryLedger._group)
    _stage = transaction(previous.RecoveryLedger._stage)
    _closed = transaction(previous.RecoveryLedger._closed)
    _commitments = transaction(previous.RecoveryLedger._commitments)
    snapshot = transaction(previous.RecoveryLedger.snapshot)
    allocate_group = transaction(previous.RecoveryLedger.allocate_group)
    reserve = transaction(previous.RecoveryLedger.reserve)
    settle = transaction(previous.RecoveryLedger.settle)
    close = transaction(previous.RecoveryLedger.close)
