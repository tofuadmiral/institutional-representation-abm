"""Unfrozen durable episode evidence and exact OFFLINE replay.

No allocation, transport, resume, qualification inheritance or scientific gate.
The production wrapper must first verify sources and physical/financial evidence.
Evidence references avoid duplicating full native transcripts in every snapshot.
"""
from copy import deepcopy
from dataclasses import dataclass, fields
import fcntl
from fractions import Fraction
import json
import math
from pathlib import Path
from threading import Lock

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_independent_calls as physical
from paper3 import retrospective_independent_execution as execution
from paper3.pivot_b_budget import atomic, identifier

FORMAT = "retrospective-episode-journal-v1"
KINDS = {"inventory", "prepared", "evidence", "decision", "term", "episode", "terminal"}


@dataclass(frozen=True)
class EvidenceReference:
    logical_id: str
    physical_id: str
    sha256: str


CLASSES = {c.__name__: c for c in (institution.Game, institution.Offer, institution.Response,
    institution.Assessment, institution.Term, institution.Episode, EvidenceReference)}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def encode(value):
    """Lossless allowlisted codec; bool/int, tuple/list and Fraction stay distinct."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        institution.require(math.isfinite(value), "finite evidence float")
        return value
    if type(value) is Fraction:
        return dict(kind="fraction", numerator=value.numerator, denominator=value.denominator)
    if type(value) is tuple:
        return dict(kind="tuple", items=[encode(v) for v in value])
    if type(value) is list:
        return [encode(v) for v in value]
    if type(value) is dict:
        items = [[encode(k), encode(v)] for k, v in value.items()]
        items.sort(key=lambda pair: canonical(pair[0]))
        return dict(kind="map", items=items)
    if type(value) in CLASSES.values():
        return dict(kind="dataclass", name=type(value).__name__,
                    fields={f.name: encode(getattr(value, f.name)) for f in fields(value)})
    raise ValueError("unregistered evidence type")


def decode(value):
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        institution.require(math.isfinite(value), "finite evidence float")
        return value
    if type(value) is list:
        return [decode(v) for v in value]
    institution.require(type(value) is dict, "typed evidence object")
    kind = value.get("kind")
    if kind == "fraction":
        institution.require(set(value) == {"kind", "numerator", "denominator"} and
            type(value["numerator"]) is int and type(value["denominator"]) is int and
            value["denominator"] > 0, "exact rational evidence")
        result = Fraction(value["numerator"], value["denominator"])
    elif kind in ("tuple", "map"):
        institution.require(set(value) == {"kind", "items"} and type(value["items"]) is list,
                            "typed collection evidence")
        if kind == "tuple":
            result = tuple(decode(v) for v in value["items"])
        else:
            result = {}
            for pair in value["items"]:
                institution.require(type(pair) is list and len(pair) == 2, "mapping pair")
                key = decode(pair[0])
                institution.require(key not in result, "duplicate or colliding mapping key")
                result[key] = decode(pair[1])
    elif kind == "dataclass":
        institution.require(set(value) == {"kind", "name", "fields"} and value["name"] in CLASSES,
                            "allowlisted evidence class")
        cls = CLASSES[value["name"]]
        institution.require(type(value["fields"]) is dict and
            set(value["fields"]) == {f.name for f in fields(cls)}, "exact evidence fields")
        result = cls(**{key: decode(v) for key, v in value["fields"].items()})
    else:
        raise ValueError("unknown evidence encoding")
    institution.require(canonical(encode(result)) == canonical(value), "noncanonical evidence encoding")
    return result


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            institution.require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("nonfinite JSON constant")
    return json.loads(Path(path).read_text(), object_pairs_hook=unique, parse_constant=nonfinite)


def _digest(path):
    return physical.t.sha(Path(path).read_bytes())


def _protocol(protocol):
    institution.require(type(protocol) is str and len(protocol) == 64 and
        all(c in "0123456789abcdef" for c in protocol), "exact protocol digest")


def _guard(verify, protocol):
    result = verify()
    institution.require(type(result) is tuple and len(result) == 2 and result[1] == protocol,
                        "source/protocol verification rejected")


def _reference(root, ref, protocol):
    identifier(ref.logical_id)
    identifier(ref.physical_id)
    _protocol(ref.sha256)
    path = Path(root) / "calls" / (ref.physical_id + ".json")
    institution.require(_digest(path) == ref.sha256, "physical reference hash changed")
    row = load(path)
    institution.require(row["id"] == ref.physical_id and row["protocol"] == protocol and
        row["context"]["logical_id"] == ref.logical_id, "physical reference provenance")
    return physical.normalized(row, path, ref.logical_id)


def compact(value, root, protocol):
    if type(value) is dict and "physical_reference" in value:
        ref = value["physical_reference"]
        institution.require(type(ref) is dict and set(ref) == {"id", "sha256"}, "physical reference fields")
        reference = EvidenceReference(value["id"], ref["id"], ref["sha256"])
        institution.require(canonical(encode(value)) == canonical(encode(_reference(root, reference, protocol))),
                            "logical copy differs from immutable physical evidence")
        return reference
    if type(value) is dict:
        return {key: compact(v, root, protocol) for key, v in value.items()}
    if type(value) in (tuple, list):
        return type(value)(compact(v, root, protocol) for v in value)
    if type(value) in CLASSES.values():
        return type(value)(**{f.name: compact(getattr(value, f.name), root, protocol) for f in fields(value)})
    return deepcopy(value)


def expand(value, root, protocol):
    if type(value) is EvidenceReference:
        return _reference(root, value, protocol)
    if type(value) is dict:
        return {key: expand(v, root, protocol) for key, v in value.items()}
    if type(value) in (tuple, list):
        return type(value)(expand(v, root, protocol) for v in value)
    if type(value) in CLASSES.values():
        return type(value)(**{f.name: expand(getattr(value, f.name), root, protocol) for f in fields(value)})
    return deepcopy(value)


def start_record(assignments, protocol):
    _protocol(protocol)
    institution.require(type(assignments) is tuple and 0 < len(assignments) <= 16,
                        "bounded complete assignment inventory")
    ids = [a["id"] for a in assignments]
    for key in ids:
        identifier(key)
    institution.require(len(set(ids)) == len(ids), "unique journal assignments")
    for a in assignments:
        institution.validate(a["game"])
        institution.rules(a["arm"])
        institution.require(type(a["seed_base"]) is int and a["seed_base"] >= 0, "assigned seed base")
    return dict(format=FORMAT, protocol=protocol, assignments=encode(assignments),
                maximum_events=2 + 123 * len(assignments))


class Journal:
    """Fresh append-only writer; close releases lock, never licenses resumption."""
    def __init__(self, root, assignments, protocol, *, verify):
        institution.require(callable(verify), "explicit source verification required")
        _guard(verify, protocol)
        self.root, self.protocol, self.verify = Path(root), protocol, verify
        self.start = start_record(assignments, protocol)
        self.root.mkdir(parents=True, exist_ok=True)
        self.writer = (self.root / "episode_writer.lock").open("a")
        self.serial, self.failed, self.terminal, self.index = Lock(), False, False, 0
        try:
            fcntl.flock(self.writer, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.directory = self.root / "episode_journal"
            self.directory.mkdir(exist_ok=False)  # Even an empty interrupted directory cannot restart.
            atomic(self.directory / "start.json", self.start)
            self.previous = _digest(self.directory / "start.json")
        except Exception:
            self.writer.close()
            raise

    def close(self):
        self.writer.close()

    def append(self, event):
        if not self.serial.acquire(blocking=False):
            self.failed = True
            raise ValueError("one journal writer only")
        try:
            institution.require(not self.failed and not self.terminal and not self.writer.closed,
                                "journal closed/interrupted; never resume")
            _guard(self.verify, self.protocol)
            institution.require(type(event) is dict and event.get("event") in KINDS and
                ((self.index == 0) == (event["event"] == "inventory")), "journal event declaration")
            institution.require(self.index < self.start["maximum_events"], "journal event ceiling")
            row = dict(format=FORMAT, protocol=self.protocol, index=self.index,
                previous_sha256=self.previous, payload=encode(compact(event, self.root, self.protocol)))
            path = self.directory / f"{self.index:06d}.json"
            institution.require(not path.exists(), "journal event already recorded")
            atomic(path, row)
            self.previous = _digest(path)
            self.index += 1
            self.terminal = event["event"] == "terminal"
        except Exception:
            self.failed = True
            raise
        finally:
            self.serial.release()


def inspect(root, assignments, protocol, *, verify):
    """Read-only prefix integrity; absence of terminal is explicitly incomplete."""
    _guard(verify, protocol)
    root = Path(root)
    directory = root / "episode_journal"
    expected = start_record(assignments, protocol)
    institution.require(canonical(load(directory / "start.json")) == canonical(expected),
                        "journal start/inventory changed")
    institution.require(not list(directory.glob("*.partial")), "interrupted partial journal write")
    paths = sorted(p for p in directory.glob("*.json") if p.name != "start.json")
    institution.require(len(paths) <= expected["maximum_events"], "journal event ceiling")
    previous, events = _digest(directory / "start.json"), []
    for index, path in enumerate(paths):
        institution.require(path.name == f"{index:06d}.json", "journal gap/filename changed")
        row = load(path)
        institution.require(set(row) == {"format", "protocol", "index", "previous_sha256", "payload"} and
            row["format"] == FORMAT and row["protocol"] == protocol and type(row["index"]) is int and
            row["index"] == index and row["previous_sha256"] == previous, "journal hash chain changed")
        event = expand(decode(row["payload"]), root, protocol)
        institution.require(type(event) is dict and event.get("event") in KINDS and
            ((index == 0) == (event["event"] == "inventory")) and
            (event["event"] != "terminal" or index == len(paths) - 1), "journal event order")
        events.append(event)
        previous = _digest(path)
    _guard(verify, protocol)
    return dict(protocol=protocol, events=tuple(events), events_recorded=len(events),
        complete=bool(events) and events[-1]["event"] == "terminal", chain_sha256=previous,
        allocation_authorized=False, publication_evidence=False)


def replay(root, assignments, protocol, *, verify, transport_report):
    """Exact controller reconstruction after external physical/financial audit.

No backend hooks exist here. Only audited logical evidence is consumed; every
emitted event must match the durable event, including failure prefixes, complete
terms, all unexecuted slots and joint missingness. Never trust saved summaries.
"""
    journal = inspect(root, assignments, protocol, verify=verify)
    institution.require(journal["complete"], "incomplete journal; preserve prefix, do not resume")
    institution.require(transport_report["protocol"] == protocol, "physical audit protocol")
    by_id = {r["case"]["id"]: r for r in transport_report["logicals"]}
    institution.require(len(by_id) == len(transport_report["logicals"]), "physical audit duplicate logicals")
    used, emitted = set(), []
    def respond(request, key):
        institution.require(key in by_id and key not in used, "missing/reused audited logical evidence")
        record = by_id[key]
        institution.require(canonical(encode(record["case"]["request"])) == canonical(encode(request)),
                            "replayed request differs from physical audit")
        institution.require(record["status"] in ("recorded_valid", "content_failed", "unsafe_failed") and
            record["returned_evidence"] is not None, "unfinished physical/logical evidence")
        used.add(key)
        return deepcopy(record["returned_evidence"])
    def persist(event):
        index = len(emitted)
        institution.require(index < len(journal["events"]) and
            canonical(encode(event)) == canonical(encode(journal["events"][index])),
            "recomputed journal event/report differs")
        emitted.append(event["event"])
    result = execution.execute(assignments, respond=respond,
        verify=lambda: _guard(verify, protocol), persist=persist)
    institution.require(len(emitted) == len(journal["events"]) and used == set(by_id),
                        "unmatched journal/physical evidence")
    return dict(protocol=protocol, report=result, events_replayed=len(emitted),
        journal_chain_sha256=journal["chain_sha256"], physical_accounted_usd=transport_report["accounted_usd"],
        allocation_authorized=False, publication_evidence=False,
        limitation="Exact offline controller/physical replay only. Caller must freeze "
                    "sources, prove qualification/authority and evaluate the prespecified science separately.")


def audit(root, ledger_root, stage, assignments, protocol, *, verify, maximum_reissues):
    """Public read-only path: recompute physical/cost evidence, THEN replay journal."""
    _guard(verify, protocol)
    start_record(assignments, protocol)
    slots = {a["id"] + f"-{i:02d}": a for a in assignments for i in range(30)}
    def classify(row, case):
        key = case["context"]["logical_id"]
        institution.require(key in slots, "physical logical slot not assigned")
        payload = json.loads(case["request"]["messages"][1]["content"])
        institution.require(payload["stage"] == case["context"]["stage"], "assigned physical phase")
        return execution.classify(row, case["request"], slots[key]["game"], payload["stage"])
    transport = physical.audit(root, ledger_root, stage, protocol, classify,
        maximum_logical=30 * len(assignments), maximum_reissues=maximum_reissues)
    _guard(verify, protocol)
    result = replay(root, assignments, protocol, verify=verify, transport_report=transport)
    result["physical_reissues"] = transport["reissues"]
    result["physical_attempts"] = len(transport["physical_reports"])
    return result
