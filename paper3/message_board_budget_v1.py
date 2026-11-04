"""Prospective namespace within the unchanged TOTAL21.31 ledger graph.

Importing does not allocate. Tests use a private copy of historical accounting.
The completed office-probe adapter and all older authority remain immutable.
"""
from paper3 import office_sacrifice_budget_v1 as previous
from paper3 import retrospective_receipt_recovery_v1 as billing
from paper3.pivot_b_budget import Ledger

TOTAL_CAP = previous.TOTAL_CAP
STAGES = "message_board_stages_v1"
GROUPS = "message_board_groups_v1"
CLOSURES = "message_board_closures_v1"


def transaction(function):
    return billing.bind(function, STAGES=STAGES, GROUPS=GROUPS,
                        CLOSURES=CLOSURES, legacy=previous)


class BoardLedger(previous.ProbeLedger):
    def __init__(self, root, *, stage_pins=None):
        Ledger.__init__(self, root)
        self._legacy = previous.ProbeLedger(root)
        self._stage_pins = dict(stage_pins or {})
        self._retirement_pins = {}
        self._check_authority()

    def _check_authority(self):
        self._legacy._check_authority()

    _binding = transaction(previous.ProbeLedger._binding)
    _group = transaction(previous.ProbeLedger._group)
    _stage = transaction(previous.ProbeLedger._stage)
    _closed = transaction(previous.ProbeLedger._closed)
    _commitments = transaction(previous.ProbeLedger._commitments)
    snapshot = transaction(previous.ProbeLedger.snapshot)
    allocate_group = transaction(previous.ProbeLedger.allocate_group)
    reserve = transaction(previous.ProbeLedger.reserve)
    settle = transaction(previous.ProbeLedger.settle)
    close = transaction(previous.ProbeLedger.close)
