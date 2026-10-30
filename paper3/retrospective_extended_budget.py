"""Prospective $15 TOTAL authority, with immutable original $10/$12 evidence.

No network, experiment preparation or launch permission. A separately approved
and frozen runner must supply stage scope and full-block bounds. Tests use copied
authority records and fabricated entries only; never migrate an old stage.
"""
from contextlib import contextmanager
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
import time

from paper3.pivot_b_budget import Ledger, BUDGET_ID, amount, atomic, identifier

TOTAL_CAP = Decimal("15.00")
ORIGINAL_SHA = "201a399b27f65bb350425632402458994f768975aed550132d16f6b5679ac925"
PREVIOUS_EXTENSION_SHA = "9cc476e141a9227aa359f8d8561f1a1201d79a70b7fa29cbb5790beb44db7183"
PREVIOUS_EXTENSION_FILE = "authority_extension_2026_10_03.json"
EXTENSION_SHA = "b82487ab561e165c525d8a5c0e11e07d45143b50f8184f670f0135283d004e66"
EXTENSION_FILE = "authority_extension_2026_10_04.json"
AUTHORITY_FILES = ("authority.json", PREVIOUS_EXTENSION_FILE, EXTENSION_FILE)


def _digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _sha(value):
    if type(value) is not str or not re.fullmatch("[a-f0-9]{64}", value):
        raise ValueError("exact SHA256 required")
    return value


class ExtendedLedger(Ledger):
    def __init__(self, root, *, stage_pins=None):
        super().__init__(root)  # Still requires the original $10 authority.
        self._stage_pins = dict(stage_pins or {})
        for stage, digest in self._stage_pins.items():
            identifier(stage)
            _sha(digest)
        self._check_authority()

    def _check_authority(self):
        original, extension = self.root / "authority.json", self.root / EXTENSION_FILE
        previous = self.root / PREVIOUS_EXTENSION_FILE
        if (_digest(original) != ORIGINAL_SHA or _digest(extension) != EXTENSION_SHA or
                _digest(previous) != PREVIOUS_EXTENSION_SHA):
            raise ValueError("pinned original/extension authority changed")
        prior = json.loads(previous.read_text())
        if not (prior["budget_id"] == BUDGET_ID and
                prior["original_authority_sha256"] == ORIGINAL_SHA and
                amount(prior["previous_total_cap_usd"]) == Decimal("10") and
                amount(prior["new_total_cap_usd"]) == Decimal("12") and
                prior["credit_purchases_authorized"] is False and
                prior["old_protocols_modified"] is False):
            raise ValueError("previous total extension scope changed")
        record = json.loads(extension.read_text())
        if not (record["budget_id"] == BUDGET_ID and
                record["original_authority_sha256"] == ORIGINAL_SHA and
                record["previous_extension_sha256"] == PREVIOUS_EXTENSION_SHA and
                amount(record["previous_total_cap_usd"]) == Decimal("12") and
                amount(record["new_total_cap_usd"]) == TOTAL_CAP and
                record["credit_purchases_authorized"] is False and
                record["old_protocols_modified"] is False):
            raise ValueError("total extension scope changed")

    @contextmanager
    def locked(self):
        with super().locked():
            self._check_authority()  # Recheck inside every admission transaction.
            yield

    def _stage(self, stage):
        identifier(stage)
        path = self.root / "stages" / (stage + ".json")
        if stage not in self._stage_pins or _digest(path) != self._stage_pins[stage]:
            raise ValueError("stage missing from pinned prospective scope")
        record = json.loads(path.read_text())
        if not (record["stage"] == stage and
                record["authority_extension_sha256"] == EXTENSION_SHA and
                record["original_authority_sha256"] == ORIGINAL_SHA and
                amount(record["total_cap_usd"]) == TOTAL_CAP and
                0 < amount(record["cap_usd"]) <= TOTAL_CAP):
            raise ValueError("prospective stage binding changed")
        for name, digest in record["prior_entries"].items():
            identifier(Path(name).stem)
            if Path(name).name != name or not name.endswith(".json"):
                raise ValueError("unsafe prior ledger path")
            _sha(digest)
            if _digest(self.root / "entries" / name) != digest:
                raise ValueError("prior ledger entry deleted or changed")
        if "group" in record:
            group = self._group(record["group"])
            if group["stages"].get(stage) != record:
                raise ValueError("grouped stage differs from whole allocation")
            # A crash while materializing either stage admits ZERO requests.
            for name, expected in group["stages"].items():
                path = self.root / "stages" / (name + ".json")
                if not path.is_file() or json.loads(path.read_text()) != expected:
                    raise ValueError("incomplete whole-group allocation; do not restart")
        return record

    def _group(self, group):
        identifier(group)
        path = self.root / "stage_groups" / (group + ".json")
        record = json.loads(path.read_text())
        if (record["group"] != group or record["authority_extension_sha256"] != EXTENSION_SHA or
                record["original_authority_sha256"] != ORIGINAL_SHA or
                amount(record["total_cap_usd"]) != TOTAL_CAP or
                type(record["stages"]) is not dict or not 1 <= len(record["stages"]) <= 16):
            raise ValueError("whole-group authority or inventory changed")
        for stage, allocation in record["stages"].items():
            identifier(stage)
            if (allocation["stage"] != stage or allocation["group"] != group or
                    allocation["authority_extension_sha256"] != EXTENSION_SHA or
                    allocation["original_authority_sha256"] != ORIGINAL_SHA or
                    amount(allocation["total_cap_usd"]) != TOTAL_CAP or
                    not 0 < amount(allocation["cap_usd"]) <= TOTAL_CAP):
                raise ValueError("whole-group stage binding changed")
        if sum((amount(a["cap_usd"]) for a in record["stages"].values()), Decimal(0)) != amount(record["cap_usd"]):
            raise ValueError("whole-group cap changed")
        if not 0 < amount(record["cap_usd"]) <= TOTAL_CAP:
            raise ValueError("whole-group total outside authority")
        return record

    def _closed(self, stage, digest):
        path = self.root / "stage_closures" / (stage + ".json")
        if not path.exists():
            return False
        record = json.loads(path.read_text())
        if (record.get("stage") != stage or record.get("stage_sha256") != digest or
                record.get("authority_extension_sha256") != EXTENSION_SHA):
            raise ValueError("stage closure binding changed")
        _sha(record["terminal_evidence_sha256"])
        return True

    def _commitments(self, rows):
        """Unspent active caps are earmarked, not charged or ledger entries."""
        unused = Decimal(0)
        grouped = set()
        for path in sorted((self.root / "stage_groups").glob("*.json")):
            group = self._group(path.stem)
            for stage, allocation in group["stages"].items():
                if stage in grouped:
                    raise ValueError("stage appears in multiple allocation groups")
                grouped.add(stage)
                stage_path = self.root / "stages" / (stage + ".json")
                if stage_path.exists():
                    if json.loads(stage_path.read_text()) != allocation:
                        raise ValueError("materialized grouped stage changed")
                    closed = self._closed(stage, _digest(stage_path))
                else:
                    closed = False  # Entire absent-stage allocation stays earmarked.
                if not closed:
                    unused += max(Decimal(0), amount(allocation["cap_usd"]) - self._total(rows, stage))
        for path in sorted((self.root / "stages").glob("*.json")):
            record = json.loads(path.read_text())
            if record.get("authority_extension_sha256") != EXTENSION_SHA:
                continue  # Legacy stages stay legacy; actual charges still count.
            stage = record["stage"]
            identifier(stage)
            if "group" in record:
                if stage not in grouped:
                    raise ValueError("grouped stage lost its whole-allocation record")
                continue
            if path.name != stage + ".json":
                raise ValueError("prospective stage identity changed")
            cap = amount(record["cap_usd"])
            if not 0 < cap <= TOTAL_CAP:
                raise ValueError("prospective cap changed")
            if not self._closed(stage, _digest(path)):
                unused += max(Decimal(0), cap - self._total(rows, stage))
        return unused

    def snapshot(self):
        with self.locked():
            rows = self._entries()
            used = self._total(rows)
            return dict(budget_id=BUDGET_ID, cap_usd=str(TOTAL_CAP),
                original_cap_usd="10.00", authority_extension_sha256=EXTENSION_SHA,
                accounted_usd=str(used), remaining_usd=str(TOTAL_CAP - used), entries=len(rows),
                unspent_active_stage_caps_usd=str(self._commitments(rows)),
                available_for_new_stages_usd=str(TOTAL_CAP - used - self._commitments(rows)),
                pending=sum(r["status"] != "settled" for r in rows),
                uncertified=sum(r.get("certified") is False for r in rows))

    def allocate(self, stage, cap):
        """Full-stage admission, once; not authorization to start inference."""
        identifier(stage)
        limit = amount(cap)
        if not 0 < limit <= TOTAL_CAP:
            raise ValueError("stage cap outside approved total")
        with self.locked():
            path = self.root / "stages" / (stage + ".json")
            if path.exists() or any(stage in self._group(p.stem)["stages"]
                for p in (self.root / "stage_groups").glob("*.json")):
                raise ValueError("existing stage cannot migrate/restart")
            rows = self._entries()
            if self._total(rows) + self._commitments(rows) + limit > TOTAL_CAP:
                raise ValueError("full-stage total admission denied")
            (self.root / "stages").mkdir(exist_ok=True)
            (self.root / "entries").mkdir(exist_ok=True)
            prior = {p.name: _digest(p) for p in sorted((self.root / "entries").glob("*.json"))}
            record = dict(stage=stage, cap_usd=str(limit), total_cap_usd=str(TOTAL_CAP),
                original_authority_sha256=ORIGINAL_SHA, authority_extension_sha256=EXTENSION_SHA,
                prior_entries=prior, allocated_unix=time.time())
            atomic(path, record)
            self._stage_pins[stage] = _digest(path)
            return record

    def allocate_group(self, group, stage_caps, *, expected_baseline=None):
        """One durable whole-study admission before either block can spend.

The group commitment is written FIRST. Partial materialization preserves ALL
caps, admits no requests and cannot be restarted/repaired by this API. Only a
separate human decision can resolve an interrupted financial allocation.
"""
        identifier(group)
        if type(stage_caps) is not dict or not 1 <= len(stage_caps) <= 16:
            raise ValueError("explicit bounded whole-stage inventory required")
        caps = {identifier(stage): amount(cap) for stage, cap in stage_caps.items()}
        total = sum(caps.values(), Decimal(0))
        if not all(0 < cap <= TOTAL_CAP for cap in caps.values()) or total > TOTAL_CAP:
            raise ValueError("whole-group caps outside approved total")
        with self.locked():
            target = self.root / "stage_groups" / (group + ".json")
            already_grouped = {stage for path in (self.root / "stage_groups").glob("*.json")
                               for stage in self._group(path.stem)["stages"]}
            if target.exists() or set(caps) & already_grouped or any(
                    (self.root / "stages" / (stage + ".json")).exists() for stage in caps):
                raise ValueError("existing group/stage cannot restart or migrate")
            rows = self._entries()
            prior = {p.name: _digest(p) for p in sorted((self.root / "entries").glob("*.json"))}
            if expected_baseline is not None:
                actual = dict(prior_entries=prior, accounted_usd=str(self._total(rows)),
                              unused_commitments_usd=str(self._commitments(rows)))
                if actual != expected_baseline:
                    raise ValueError("pre-freeze financial baseline changed")
            if self._total(rows) + self._commitments(rows) + total > TOTAL_CAP:
                raise ValueError("whole-group total admission denied")
            for name in ("stage_groups", "stages", "entries"):
                (self.root / name).mkdir(exist_ok=True)
            allocations = {stage: dict(stage=stage, group=group, cap_usd=str(cap),
                total_cap_usd=str(TOTAL_CAP), original_authority_sha256=ORIGINAL_SHA,
                authority_extension_sha256=EXTENSION_SHA, prior_entries=prior,
                allocated_unix=time.time()) for stage, cap in caps.items()}
            record = dict(group=group, cap_usd=str(total), total_cap_usd=str(TOTAL_CAP),
                original_authority_sha256=ORIGINAL_SHA, authority_extension_sha256=EXTENSION_SHA,
                stages=allocations)
            atomic(target, record)  # Complete shared commitment before per-stage files.
            for stage, allocation in allocations.items():
                path = self.root / "stages" / (stage + ".json")
                atomic(path, allocation)
                self._stage_pins[stage] = _digest(path)
            return dict(group=group, group_sha256=_digest(target), stage_pins=self.stage_pins())

    def stage_pins(self):
        return dict(self._stage_pins)

    def reserve(self, stage, request_id, maximum, request_sha256):
        identifier(stage)
        identifier(request_id)
        reserve = amount(maximum)
        _sha(request_sha256)
        if reserve <= 0:
            raise ValueError("positive request reservation required")
        with self.locked():
            allocation = self._stage(stage)
            if self._closed(stage, self._stage_pins[stage]):
                raise ValueError("closed stage cannot admit another request")
            path = self.root / "entries" / (request_id + ".json")
            if path.exists():
                raise ValueError("already admitted; no restart")
            rows = self._entries()
            if (self._total(rows) + reserve > TOTAL_CAP or
                    self._total(rows, stage) + reserve > amount(allocation["cap_usd"])):
                raise ValueError("total/stage admission denied")
            row = dict(budget_id=BUDGET_ID, request_id=request_id, stage=stage,
                request_sha256=request_sha256, reserved_usd=str(reserve),
                status="reserved", admitted_unix=time.time())
            atomic(path, row)
            return row

    def close(self, stage, terminal_evidence_sha256):
        """Append-only financial closure after an externally audited terminal.

        Caller must prove terminal provenance in the production audit. No
        unresolved request is released, and no old stage or entry is modified.
        """
        _sha(terminal_evidence_sha256)
        with self.locked():
            self._stage(stage)
            digest = self._stage_pins[stage]
            if self._closed(stage, digest):
                raise ValueError("stage already closed")
            if any(r["stage"] == stage and r["status"] != "settled" for r in self._entries()):
                raise ValueError("unresolved own reservation prevents closure")
            (self.root / "stage_closures").mkdir(exist_ok=True)
            record = dict(stage=stage, stage_sha256=digest,
                authority_extension_sha256=EXTENSION_SHA,
                terminal_evidence_sha256=terminal_evidence_sha256, closed_unix=time.time())
            atomic(self.root / "stage_closures" / (stage + ".json"), record)
            return record

    def settle(self, request_id, accounted, certified, evidence_sha256):
        identifier(request_id)
        cost = amount(accounted)
        _sha(evidence_sha256)
        if type(certified) is not bool:
            raise ValueError("settlement certificate boolean required")
        with self.locked():
            path = self.root / "entries" / (request_id + ".json")
            row = json.loads(path.read_text())
            allocation = self._stage(row["stage"])
            if path.name in allocation["prior_entries"]:
                raise ValueError("cannot mutate pre-stage reservation")
            if row["status"] != "reserved":
                raise ValueError("settlement already recorded")
            if not certified and cost < amount(row["reserved_usd"]):
                raise ValueError("uncertified reservation cannot be released")
            # Above-bound charges stay in full; future admissions must fail.
            row.update(status="settled", accounted_usd=str(cost), certified=certified,
                       evidence_sha256=evidence_sha256, settled_unix=time.time())
            atomic(path, row)
            return row
