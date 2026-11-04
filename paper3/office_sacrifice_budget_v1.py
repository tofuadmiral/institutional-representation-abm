"""New diagnostic namespace within the existing cumulative $21.31 authority."""
from paper3 import retrospective_validation_budget_v1 as previous
from paper3 import retrospective_receipt_recovery_v1 as billing
from paper3.pivot_b_budget import Ledger

TOTAL_CAP = previous.TOTAL_CAP
STAGES = "office_probe_stages_v1"
GROUPS = "office_probe_groups_v1"
CLOSURES = "office_probe_closures_v1"


def transaction(function):
    return billing.bind(function, STAGES=STAGES, GROUPS=GROUPS,
                        CLOSURES=CLOSURES, legacy=previous)


class ProbeLedger(previous.ValidationLedger):
    def __init__(self, root, *, stage_pins=None):
        Ledger.__init__(self, root)
        self._legacy = previous.ValidationLedger(root)
        self._stage_pins = dict(stage_pins or {})
        self._retirement_pins = {}
        self._check_authority()

    def _check_authority(self):
        self._legacy._check_authority()

    _binding = transaction(previous.ValidationLedger._binding)
    _group = transaction(previous.ValidationLedger._group)
    _stage = transaction(previous.ValidationLedger._stage)
    _closed = transaction(previous.ValidationLedger._closed)
    _commitments = transaction(previous.ValidationLedger._commitments)
    snapshot = transaction(previous.ValidationLedger.snapshot)
    allocate_group = transaction(previous.ValidationLedger.allocate_group)
    reserve = transaction(previous.ValidationLedger.reserve)
    settle = transaction(previous.ValidationLedger.settle)
    close = transaction(previous.ValidationLedger.close)
