"""Fresh $10 B allowance: process-safe, durable reservation accounting.

Started but unresolved requests continue to consume their entire reservation.
Neither a new process nor a new stage resets the allowance. No network access.
"""
from contextlib import contextmanager
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import re
import time

CAP = Decimal("10.00")
BUDGET_ID = "paper3-pivot-b-2026-09-24"


def amount(value):
    n = Decimal(str(value))
    if not n.is_finite() or n < 0:
        raise ValueError("nonnegative finite amount required")
    return n


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise ValueError("unsafe budget identifier")
    return value


def atomic(path, value):
    path = Path(path)
    temporary = path.with_suffix(".partial")
    with temporary.open("x") as f:
        json.dump(value, f, sort_keys=True, indent=2)
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Ledger:
    def __init__(self, root):
        self.root = Path(root)
        authority = json.loads((self.root/"authority.json").read_text())
        if (authority["budget_id"] != BUDGET_ID or amount(authority["cap_usd"]) != CAP
                or authority["credit_purchases_authorized"] is not False):
            raise ValueError("fresh authority mismatch")

    @contextmanager
    def locked(self):
        with (self.root/"ledger.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            if list(self.root.rglob("*.partial")):
                raise ValueError("interrupted ledger write; do not resume inference")
            yield

    def _entries(self):
        return [json.loads(p.read_text()) for p in sorted((self.root/"entries").glob("*.json"))]

    def _total(self, rows, stage=None):
        return sum((amount(r["accounted_usd"] if r["status"] == "settled" else r["reserved_usd"])
                    for r in rows if stage is None or r["stage"] == stage), Decimal(0))

    def snapshot(self):
        with self.locked():
            rows = self._entries()
            used = self._total(rows)
            return dict(budget_id=BUDGET_ID, cap_usd=str(CAP), accounted_usd=str(used),
                        remaining_usd=str(CAP-used), entries=len(rows),
                        pending=sum(r["status"] != "settled" for r in rows),
                        uncertified=sum(r.get("certified") is False for r in rows))

    def allocate(self, stage, cap):
        identifier(stage)
        limit = amount(cap)
        if not 0 < limit <= CAP:
            raise ValueError("stage cap outside allowance")
        with self.locked():
            (self.root/"stages").mkdir(exist_ok=True)
            (self.root/"entries").mkdir(exist_ok=True)
            path = self.root/"stages"/(stage+".json")
            if path.exists():
                saved = json.loads(path.read_text())
                if amount(saved["cap_usd"]) != limit:
                    raise ValueError("cannot change an existing stage cap")
                return saved
            saved = dict(stage=stage, cap_usd=str(limit), allocated_unix=time.time())
            atomic(path, saved)
            return saved

    def reserve(self, stage, request_id, maximum, request_sha256):
        identifier(stage); identifier(request_id)
        reserve = amount(maximum)
        if reserve <= 0 or not re.fullmatch(r"[a-f0-9]{64}", request_sha256):
            raise ValueError("invalid request reservation")
        with self.locked():
            limit = amount(json.loads((self.root/"stages"/(stage+".json")).read_text())["cap_usd"])
            path = self.root/"entries"/(request_id+".json")
            if path.exists():
                raise ValueError("request already admitted; no retries/restarts")
            rows = self._entries()
            if self._total(rows)+reserve > CAP or self._total(rows, stage)+reserve > limit:
                raise ValueError("budget admission denied")
            row = dict(budget_id=BUDGET_ID, request_id=request_id, stage=stage,
                       request_sha256=request_sha256, reserved_usd=str(reserve),
                       status="reserved", admitted_unix=time.time())
            atomic(path, row)
            return row

    def settle(self, request_id, accounted, certified, evidence_sha256):
        identifier(request_id)
        cost = amount(accounted)
        if type(certified) is not bool or not re.fullmatch(r"[a-f0-9]{64}", evidence_sha256):
            raise ValueError("settlement certificate invalid")
        with self.locked():
            path = self.root/"entries"/(request_id+".json")
            row = json.loads(path.read_text())
            if row["status"] != "reserved":
                raise ValueError("settlement already recorded")
            if not certified and cost < amount(row["reserved_usd"]):
                raise ValueError("uncertified reservation cannot be released")
            # An above-bound actual charge is retained, never clipped. Caller
            # must treat it as a global instrument failure, not keep spending.
            row.update(status="settled", accounted_usd=str(cost), certified=certified,
                       evidence_sha256=evidence_sha256, settled_unix=time.time())
            atomic(path, row)
            return row
