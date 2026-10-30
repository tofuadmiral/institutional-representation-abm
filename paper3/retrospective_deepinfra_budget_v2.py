"""Prospective $19.30 TOTAL ledger, preserving the frozen $10/$12/$15/$17 ledgers.

New allocations use a distinct namespace; old records are never migrated.
All historical charges and unresolved reservations still count. In particular,
this module does NOT create a retirement: without an externally pinned, separately
verified disposition its cap remains fully earmarked. No network or launch authority.
"""
from contextlib import contextmanager
from decimal import Decimal
import json
import time

from paper3 import retrospective_deepinfra_budget_v1 as legacy
from paper3 import retrospective_deepinfra_retirement_v2 as retirement
from paper3.pivot_b_budget import BUDGET_ID, Ledger, amount, atomic, identifier

TOTAL_CAP = Decimal("19.30")
EXTENSION_FILE = "authority_extension_2026_10_21.json"
EXTENSION_SHA = "d4ce6261bf5d4ea94675d27755c8573253c3f2baf6f31e016d69366e4fe378b8"
ORIGINAL_SHA = "201a399b27f65bb350425632402458994f768975aed550132d16f6b5679ac925"
MIGRATION_CERTIFICATE_SHA = "5185c919aa1cb394630a252631cfd4522cb188cb36d3352911af153b99cf200c"
AUTHORITY_FILES = (*legacy.AUTHORITY_FILES, EXTENSION_FILE, retirement.AUTHORIZATION_FILE)
STAGES = "overload_stages_v2"
GROUPS = "overload_stage_groups_v2"
CLOSURES = "overload_stage_closures_v2"
_digest, _sha = legacy._digest, legacy._sha


class RecoveryLedger(legacy.RecoveryLedger):
    def __init__(self, root, *, stage_pins=None, retirement_pins=None):
        Ledger.__init__(self, root)
        self._legacy = legacy.RecoveryLedger(root,
            retirement_pins=retirement.old_retirement_pins(root))
        self._stage_pins = dict(stage_pins or {})
        self._retirement_pins = dict(retirement_pins or {})
        if set(self._retirement_pins) - {retirement.STAGE}:
            raise ValueError("only the directly approved old block may be retired")
        for digest in self._retirement_pins.values():
            _sha(digest)
        for stage, digest in self._stage_pins.items():
            identifier(stage)
            _sha(digest)
        self._check_authority()

    def _check_authority(self):
        self._legacy._check_authority()
        path = self.root / EXTENSION_FILE
        if _digest(path) != EXTENSION_SHA:
            raise ValueError("pinned $19.30 authority changed")
        record = json.loads(path.read_text())
        if not (record["budget_id"] == BUDGET_ID and
                record["original_authority_sha256"] == ORIGINAL_SHA and
                record["previous_extension_sha256"] == legacy.EXTENSION_SHA and
                amount(record["previous_total_cap_usd"]) == legacy.TOTAL_CAP and
                amount(record["new_total_cap_usd"]) == TOTAL_CAP and
                record["credit_purchases_authorized"] is False and
                record["old_protocols_modified"] is False):
            raise ValueError("$10->$12->$15->$17->$19->$19.30 authority scope changed")

    @contextmanager
    def locked(self):
        with Ledger.locked(self):
            self._check_authority()
            yield

    def _prior(self, record):
        if type(record["prior_entries"]) is not dict:
            raise ValueError("prior entry inventory required")
        for name, digest in record["prior_entries"].items():
            if not name.endswith(".json") or identifier(name[:-5]) + ".json" != name:
                raise ValueError("unsafe prior entry")
            _sha(digest)
            if _digest(self.root / "entries" / name) != digest:
                raise ValueError("prior ledger entry deleted or changed")

    def _binding(self, record, stage):
        if (record["stage"] != stage or
                record["authority_extension_sha256"] != EXTENSION_SHA or
                record["original_authority_sha256"] != ORIGINAL_SHA or
                amount(record["total_cap_usd"]) != TOTAL_CAP or
                not 0 < amount(record["cap_usd"]) <= TOTAL_CAP):
            raise ValueError("prospective $19.30 stage binding changed")
        self._prior(record)
        if record["retirement_pins"] != self._retirement_pins:
            raise ValueError("prospective retirement evidence differs from pinned scope")

    def _group(self, group):
        identifier(group)
        record = json.loads((self.root / GROUPS / (group + ".json")).read_text())
        if (record["group"] != group or record["authority_extension_sha256"] != EXTENSION_SHA or
                record["original_authority_sha256"] != ORIGINAL_SHA or
                amount(record["total_cap_usd"]) != TOTAL_CAP or
                type(record["stages"]) is not dict or not 1 <= len(record["stages"]) <= 16):
            raise ValueError("whole-group authority/inventory changed")
        for stage, allocation in record["stages"].items():
            identifier(stage)
            self._binding(allocation, stage)
            if allocation["group"] != group:
                raise ValueError("stage/group binding changed")
            if any((self.root / folder / (stage + ".json")).exists()
                   for folder in (legacy.STAGES, "stages")):
                raise ValueError("new stage collides with historical stage")
        total = sum((amount(a["cap_usd"]) for a in record["stages"].values()), Decimal(0))
        if total != amount(record["cap_usd"]) or not 0 < total <= TOTAL_CAP:
            raise ValueError("whole-group cap changed")
        return record

    def _stage(self, stage):
        identifier(stage)
        path = self.root / STAGES / (stage + ".json")
        if stage not in self._stage_pins or _digest(path) != self._stage_pins[stage]:
            raise ValueError("stage missing from pinned prospective scope")
        record = json.loads(path.read_text())
        self._binding(record, stage)
        group = self._group(record["group"])
        if group["stages"].get(stage) != record:
            raise ValueError("stage differs from whole-group allocation")
        for name, expected in group["stages"].items():
            path = self.root / STAGES / (name + ".json")
            if not path.is_file() or json.loads(path.read_text()) != expected:
                raise ValueError("incomplete group materialization; no restart")
        return record

    def _closed(self, stage, digest):
        path = self.root / CLOSURES / (stage + ".json")
        if not path.exists():
            return False
        record = json.loads(path.read_text())
        if (record["stage"] != stage or record["stage_sha256"] != digest or
                record["authority_extension_sha256"] != EXTENSION_SHA):
            raise ValueError("stage closure binding changed")
        _sha(record["terminal_evidence_sha256"])
        return True

    def _commitments(self, rows):
        # The legacy adapter still validates its exact frozen namespace. It
        # knows nothing about a new account, new authority, or cancellation.
        unused = self._legacy._commitments(rows)
        for digest in self._retirement_pins.values():
            record = retirement.verify_record(self.root, digest)
            if unused < amount(record["retired_unused_cap_usd"]):
                raise ValueError("retired cap no longer part of legacy commitments")
            unused -= amount(record["retired_unused_cap_usd"])
        grouped = set()
        for path in sorted((self.root / GROUPS).glob("*.json")):
            group = self._group(path.stem)
            for stage, allocation in group["stages"].items():
                if stage in grouped:
                    raise ValueError("stage appears in multiple allocation groups")
                grouped.add(stage)
                saved = self.root / STAGES / (stage + ".json")
                if saved.exists() and json.loads(saved.read_text()) != allocation:
                    raise ValueError("materialized grouped stage changed")
                if not saved.exists() or not self._closed(stage, _digest(saved)):
                    unused += max(Decimal(0), amount(allocation["cap_usd"]) - self._total(rows, stage))
        for path in (self.root / STAGES).glob("*.json"):
            if path.stem not in grouped:
                raise ValueError("prospective stage lost its allocation group")
        return unused

    def snapshot(self):
        with self.locked():
            rows = self._entries()
            used, commitments = self._total(rows), self._commitments(rows)
            return dict(budget_id=BUDGET_ID, cap_usd=str(TOTAL_CAP), original_cap_usd="10.00",
                authority_extension_sha256=EXTENSION_SHA, accounted_usd=str(used),
                remaining_usd=str(TOTAL_CAP - used), entries=len(rows),
                unspent_active_stage_caps_usd=str(commitments),
                available_for_new_stages_usd=str(TOTAL_CAP - used - commitments),
                pending=sum(r["status"] != "settled" for r in rows),
                uncertified=sum(r.get("certified") is False for r in rows))

    def allocate(self, stage, cap):
        return self.allocate_group(stage, {stage: cap})

    def allocate_group(self, group, stage_caps, *, expected_baseline=None):
        identifier(group)
        if type(stage_caps) is not dict or not 1 <= len(stage_caps) <= 16:
            raise ValueError("explicit bounded whole-stage inventory required")
        caps = {identifier(stage): amount(cap) for stage, cap in stage_caps.items()}
        total = sum(caps.values(), Decimal(0))
        if not all(0 < cap <= TOTAL_CAP for cap in caps.values()) or total > TOTAL_CAP:
            raise ValueError("whole-group caps outside approved total")
        with self.locked():
            target = self.root / GROUPS / (group + ".json")
            grouped = {s for p in (self.root / GROUPS).glob("*.json") for s in self._group(p.stem)["stages"]}
            # The legacy adapter already validates its complete historical graph.
            # Detect collisions across all retained stage namespaces, including
            # never-started stages that have no charge rows yet.
            historical = set()
            for folder in self.root.iterdir():
                if not folder.is_dir() or "stage" not in folder.name or folder.name in (STAGES, GROUPS, CLOSURES):
                    continue
                for path in folder.glob("*.json"):
                    record = json.loads(path.read_text())
                    if isinstance(record.get("stage"), str):
                        historical.add(record["stage"])
                    if isinstance(record.get("stages"), dict):
                        historical.update(record["stages"])
            if (target.exists() or set(caps) & (grouped | historical) or any(
                    (self.root / folder / (s + ".json")).exists()
                    for s in caps for folder in (STAGES, legacy.STAGES, "stages"))):
                raise ValueError("existing group/stage cannot migrate or restart")
            rows = self._entries()
            prior = {p.name: _digest(p) for p in sorted((self.root / "entries").glob("*.json"))}
            baseline = dict(prior_entries=prior, accounted_usd=str(self._total(rows)),
                            unused_commitments_usd=str(self._commitments(rows)))
            if expected_baseline is not None and baseline != expected_baseline:
                raise ValueError("pre-freeze financial baseline changed")
            if self._total(rows) + self._commitments(rows) + total > TOTAL_CAP:
                raise ValueError("whole-group total admission denied")
            for folder in (GROUPS, STAGES, "entries"):
                (self.root / folder).mkdir(exist_ok=True)
            allocations = {s: dict(stage=s, group=group, cap_usd=str(cap),
                total_cap_usd=str(TOTAL_CAP), original_authority_sha256=ORIGINAL_SHA,
                authority_extension_sha256=EXTENSION_SHA, prior_entries=prior,
                retirement_pins=dict(self._retirement_pins),
                allocated_unix=time.time()) for s, cap in caps.items()}
            record = dict(group=group, cap_usd=str(total), total_cap_usd=str(TOTAL_CAP),
                original_authority_sha256=ORIGINAL_SHA, authority_extension_sha256=EXTENSION_SHA,
                stages=allocations)
            atomic(target, record)  # Whole commitment first; incomplete means STOP.
            for stage, allocation in allocations.items():
                path = self.root / STAGES / (stage + ".json")
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
            # Revalidate all commitments too: a changed old group is not benign.
            if (self._total(rows) + self._commitments(rows) > TOTAL_CAP or
                    self._total(rows) + reserve > TOTAL_CAP or
                    self._total(rows, stage) + reserve > amount(allocation["cap_usd"])):
                raise ValueError("total/stage admission denied")
            row = dict(budget_id=BUDGET_ID, request_id=request_id, stage=stage,
                request_sha256=request_sha256, reserved_usd=str(reserve),
                status="reserved", admitted_unix=time.time())
            atomic(path, row)
            return row

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
            row.update(status="settled", accounted_usd=str(cost), certified=certified,
                       evidence_sha256=evidence_sha256, settled_unix=time.time())
            atomic(path, row)
            return row

    def close(self, stage, terminal_evidence_sha256):
        """Caller must independently prove the terminal; never closes an old stage."""
        _sha(terminal_evidence_sha256)
        with self.locked():
            self._stage(stage)
            digest = self._stage_pins[stage]
            if self._closed(stage, digest):
                raise ValueError("stage already closed")
            if any(r["stage"] == stage and r["status"] != "settled" for r in self._entries()):
                raise ValueError("unresolved own reservation prevents closure")
            (self.root / CLOSURES).mkdir(exist_ok=True)
            record = dict(stage=stage, stage_sha256=digest, authority_extension_sha256=EXTENSION_SHA,
                terminal_evidence_sha256=terminal_evidence_sha256, closed_unix=time.time())
            atomic(self.root / CLOSURES / (stage + ".json"), record)
            return record
