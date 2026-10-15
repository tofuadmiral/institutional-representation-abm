"""Serialization and transaction-safe ten-dollar admission for the new run."""
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import time

from experiments import paper3_transport_diagnostic as t
from paper3.pivot_b_budget import Ledger, amount, atomic, identifier
STOP = Decimal("10")


def jsonable(value):
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, Fraction):
        return dict(numerator=value.numerator, denominator=value.denominator)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(item) for item in value]
    return value


class StopLedger(Ledger):
    """Keep old reservations; impose $10 under the same locked transaction."""
    def reserve(self, stage, request_id, maximum, request_sha256):
        identifier(stage)
        identifier(request_id)
        reserve = amount(maximum)
        t.require(reserve > 0 and type(request_sha256) is str and
                  len(request_sha256) == 64 and all(c in "0123456789abcdef" for c in request_sha256),
                  "invalid reservation")
        with self.locked():
            limit = amount(t.load(self.root / "stages" / (stage + ".json"))["cap_usd"])
            path = self.root / "entries" / (request_id + ".json")
            t.require(not path.exists(), "already admitted; no retry")
            rows = self._entries()
            t.require(self._total(rows) + reserve <= STOP and
                      self._total(rows, stage) + reserve <= limit, "ten-dollar/stage admission stop")
            row = dict(budget_id=t.load(self.root / "authority.json")["budget_id"],
                       request_id=request_id, stage=stage, request_sha256=request_sha256,
                       reserved_usd=str(reserve), status="reserved", admitted_unix=time.time())
            atomic(path, row)
            return row


def prior_inventory(root):
    return {path.name: t.sha(path.read_bytes()) for path in
            sorted((Path(root) / "entries").glob("*.json"))}


def verify_prior(root, expected, stage):
    current = {path.name: path for path in (Path(root) / "entries").glob("*.json")}
    t.require(set(expected) <= set(current), "prior ledger entry deleted")
    for name, sha in expected.items():
        t.require(t.sha(current[name].read_bytes()) == sha, "prior ledger entry changed")
    t.require(all(t.load(path)["stage"] == stage for name, path in current.items()
                  if name not in expected), "unrelated spending during allocation")
