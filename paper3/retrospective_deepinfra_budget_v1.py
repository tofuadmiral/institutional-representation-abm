"""Approved total19 migration: preserve incurred costs and release only unused B1.

The old namespace and old adapter are immutable. New groups retain the old
binding format but this separately frozen adapter verifies the new retirement
pin before subtracting its unused commitment. No extra spending authority.
"""
from decimal import Decimal

from paper3 import retrospective_resource_budget_v1 as original
from paper3 import retrospective_deepinfra_retirement_v1 as retirement

TOTAL_CAP = original.TOTAL_CAP
EXTENSION_SHA, BUDGET_ID = original.EXTENSION_SHA, original.BUDGET_ID
AUTHORITY_FILES = (*original.AUTHORITY_FILES, retirement.AUTHORIZATION_FILE)
STAGES, GROUPS, CLOSURES = original.STAGES, original.GROUPS, original.CLOSURES
amount, atomic, _digest, _sha = original.amount, original.atomic, original._digest, original._sha
# Actual approved retirement completed after original sealed isolated replay.
MIGRATION_CERTIFICATE_SHA = "fec1b64001790a8837935583c0533c4714df063ab09717c5962323197e123258"


class RecoveryLedger(original.RecoveryLedger):
    def _commitments(self, rows):
        unused = super()._commitments(rows)
        record = retirement.verify_record(self.root, MIGRATION_CERTIFICATE_SHA)
        value = Decimal(record["retired_unused_cap_usd"])
        if unused < value:
            raise ValueError("retired unused block is no longer committed")
        return unused - value
