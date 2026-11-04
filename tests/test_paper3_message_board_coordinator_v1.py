"""PRIVATE coordinator fixtures; never user authority, readiness or model data."""
from pathlib import Path
import shutil

import pytest

from experiments import paper3_message_board_handoff_v1 as w
from tests.test_paper3_message_board_runtime_v1 import response
from tests.test_paper3_graceful_continuation import FakeLedger
from tests.test_paper3_retrospective_independent_calls import Clock

SOURCE_REPO = Path(__file__).resolve().parents[1]


def private(tmp_path, monkeypatch):
    files = w.sources()
    for name in files:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE_REPO / name, target)
    old_manifest = tmp_path / w.OLD_MANIFEST
    old_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE_REPO / w.OLD_MANIFEST, old_manifest)
    shutil.copyfile(SOURCE_REPO / w.OLD_ROOT / "report.json", tmp_path / w.OLD_ROOT / "report.json")
    shutil.copytree(SOURCE_REPO / w.LEDGER, tmp_path / w.LEDGER, dirs_exist_ok=True)
    marker = tmp_path / "private_historical_evidence.json"
    marker.write_text('{"PRIVATE_FIXTURE": true}')
    monkeypatch.setattr(w, "REPO", tmp_path)
    # Scaled coordinator flow; the separate runtime check covers all352calls.
    monkeypatch.setattr(w, "N", 4)
    monkeypatch.setattr(w, "protected_inventory", lambda: {marker.name: w.digest(marker)})
    spec = w.specification()
    authority = dict(fixture_only="PRIVATE, not real approval; four-case test scope cannot launch the16-case cohort",
        approved=True, approved_by="Fuad",
        direct_user_instructions=["PRIVATE TEST FIXTURE, NOT A HUMAN INSTRUCTION"],
        scope=w.VERSION, specification_sha256=w.value_sha(spec),
        total_cumulative_cap_usd="21.31",
        new_allocation_cap_usd=spec["request_bound"]["full_bound_usd"],
        maximum_physical_requests=spec["request_bound"]["maximum_physical_calls"],
        credit_purchase=False, new_paid_qualification=False,
        automatic_successor=False, historical_runs_modified=False)
    readiness = dict(fixture_only="PRIVATE fabricated readiness for coordinator checks only",
        kind="PRIVATE_SOFTWARE_ONLY_NOT_MODEL_OBSERVATIONS", sources_before=files,
        sources_after=files, test_files=w.TESTS, new_model_calls=0,
        actual_ledger_mutations=0, network_process_denial_selftests=True,
        checks=[dict(returncode=0, stdout="PRIVATE fixture passed", stderr=""),
                dict(returncode=0, stdout="PRIVATE fixture passed", stderr="")])
    w.atomic(tmp_path / w.AUTHORITY, authority)
    w.atomic(tmp_path / w.READINESS, readiness)
    return authority, readiness


def test_scope_freeze_history_and_interrupted_allocation_are_exact(tmp_path, monkeypatch):
    authority, readiness = private(tmp_path, monkeypatch)
    authority_path, readiness_path = tmp_path / w.AUTHORITY, tmp_path / w.READINESS
    original_entries = w.history()
    authority["approved"] = False
    w.atomic(authority_path, authority)
    with pytest.raises(ValueError, match="scope authority"):
        w.prepare(w.digest(authority_path), w.digest(readiness_path))
    assert not (tmp_path / w.ROOT_NAME).exists()
    authority["approved"] = True
    w.atomic(authority_path, authority)
    readiness["sources_after"] = {}
    w.atomic(readiness_path, readiness)
    with pytest.raises(ValueError, match="current checks"):
        w.prepare(w.digest(authority_path), w.digest(readiness_path))
    readiness["sources_after"] = readiness["sources_before"]
    w.atomic(readiness_path, readiness)
    result = w.prepare(w.digest(authority_path), w.digest(readiness_path))
    protocol = result["protocol"]
    assert not result["allocated"] and result["model_calls"] == 0
    assert w.history() == original_entries
    assert not list((tmp_path / w.LEDGER / w.budget.GROUPS).glob("*.json"))
    with pytest.raises(ValueError, match="never prepare"):
        w.prepare(w.digest(authority_path), w.digest(readiness_path))
    source = tmp_path / "paper3/message_board_runtime_v1.py"
    original = source.read_bytes()
    source.write_bytes(original + b"\n# PRIVATE source tamper\n")
    with pytest.raises(ValueError, match="source closure"):
        w.verify(protocol)
    source.write_bytes(original)
    old = next((tmp_path / w.LEDGER / "entries").glob("*.json"))
    before = old.read_bytes()
    old.write_bytes(before + b"\n")
    with pytest.raises(ValueError, match="prior charge"):
        w.verify(protocol, full=True)
    old.write_bytes(before)
    m, _ = w.verify(protocol, full=True)
    original_atomic = w.atomic

    def crash(path, value):
        if Path(path).name == "allocation.json":
            raise KeyboardInterrupt()
        original_atomic(path, value)

    monkeypatch.setattr(w, "atomic", crash)
    with pytest.raises(KeyboardInterrupt):
        w.allocate(protocol, m)
    group_files = list((tmp_path / w.LEDGER / w.budget.GROUPS).glob("*.json"))
    assert len(group_files) == 1
    group_bytes = group_files[0].read_bytes()
    monkeypatch.setattr(w, "atomic", original_atomic)
    book, stage = w.allocate(protocol, m)
    assert group_files[0].read_bytes() == group_bytes and w.history() == original_entries
    with book.locked():
        assert book._stage(stage)["cap_usd"] == m["specification"]["request_bound"]["full_bound_usd"]
    assert w.allocate(protocol, m)[1] == stage
    assert len(list((tmp_path / w.LEDGER / w.budget.GROUPS).glob("*.json"))) == 1


def test_coordinator_real_first_charge_then_scripted_resume_and_entire_audit(tmp_path, monkeypatch):
    private(tmp_path, monkeypatch)
    old = w.history()
    protocol = w.prepare(w.digest(tmp_path / w.AUTHORITY), w.digest(tmp_path / w.READINESS))["protocol"]
    clock, sent = Clock(), []
    metadata = w.load(SOURCE_REPO / "results/paper3/pivot_b_independent_validation_v1/admissions/1793205286757644000.json")["metadata"]

    def send(wire, secret):
        assert secret is None
        sent.append(wire)
        stream = response(w.previous.json.loads(wire), "gen-private-coordinator-" + str(len(sent)))["stream"]
        stream.update(started_unix=clock(), ended_unix=clock())
        return stream

    def lookup(identifier, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
            data=dict(id=identifier, model=w.runtime.route.MODEL_ALIAS,
                      provider_name=w.runtime.route.PROVIDER, total_cost=.0001))

    def admit(root, protocol, book, stage, secret):
        w.atomic(root / "admissions" / "private.json", dict(protocol=protocol,
            metadata=metadata, metadata_observed_unix=clock(),
            account=dict(account_funded=True, research_authority_extended=False)))
        return clock()

    # Exercise the real pinned allocation and financial adapter for one complete
    # physical response. Crash after its durable transition. Repeated traversal
    # of every historical allocation on all88 simulated calls adds no coverage;
    # the budget test separately exercises reserve/settle/close on the real copy.
    original_saved = w.runtime.saved

    def interrupted(root, folder, key, value, **kwargs):
        original_saved(root, folder, key, value, **kwargs)
        if folder == "transitions":
            raise KeyboardInterrupt()

    monkeypatch.setattr(w.runtime, "saved", interrupted)
    with pytest.raises(KeyboardInterrupt):
        w.run(protocol, send=send, lookup=lookup, admit=admit, clock=clock, sleep=clock.sleep)
    assert len(sent) == 1
    raw = next((tmp_path / w.ROOT_NAME / "calls").glob("*.json"))
    raw_bytes = raw.read_bytes()
    current = w.history()
    new_entries = set(current) - set(old)
    assert len(new_entries) == 1
    first_entry = w.load(tmp_path / w.LEDGER / "entries" / new_entries.pop())
    assert first_entry["status"] == "settled" and first_entry["certified"] is True
    monkeypatch.setattr(w.runtime, "saved", original_saved)
    m, _ = w.verify(protocol, full=True)
    real_book, stage = w.allocated_book(protocol, m)
    scripted_book = FakeLedger(real_book.root)
    scripted_book._entries = lambda: [w.load(p) for p in (real_book.root / "entries").glob("*.json")]
    monkeypatch.setattr(w, "allocated_book", lambda pin, manifest: (scripted_book, stage))
    terminal = w.run(protocol, send=send, lookup=lookup, admit=admit, clock=clock, sleep=clock.sleep)
    assert terminal["status"] == "complete", terminal
    assert len(sent) == 88
    assert raw.read_bytes() == raw_bytes
    result = w.audit(protocol)
    assert result["logical"] == result["physical"] == 88
    assert result["entire_report_matched"] and result["entire_ledger_matched"]
    assert result["identity_private"]["complete_mean"] == result["identity_board"]["complete_mean"] == "0"
    assert result["controls"]["score"]["correct"] == result["controls"]["factual"]["correct"] == 4
    report = w.load(tmp_path / w.ROOT_NAME / "report.json")
    better = {c.index for c in w.design.cases(4) if c.better_successor}
    for c in w.design.cases(4):
        if c.index in better:
            main = [r for r in report["results"] if r["case"] == c.index]
            score = next(r for r in report["controls"] if r["case"] == c.index and r["kind"] == "score")
            assert all(r["replacement"] is True for r in main)
            assert score["observed"] == {"decision": c.retain_code}
    current_entries = w.history()
    assert all(current_entries[name] == sha for name, sha in old.items())
    with pytest.raises(ValueError, match="complete root"):
        w.run(protocol, send=send, lookup=lookup, admit=admit, clock=clock, sleep=clock.sleep)
    assert len(sent) == 88
