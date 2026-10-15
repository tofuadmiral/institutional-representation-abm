"""Operating CLI guards with PRIVATE fabricated evidence; no model/key/network."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from experiments import paper3_retrospective_anticipation_v1 as runner
from paper3 import retrospective_anticipation_freeze as freeze
from paper3 import retrospective_extended_budget as budget
from paper3.pivot_b_budget import atomic

PROTOCOL = "a" * 64


@pytest.fixture
def private(tmp_path, monkeypatch):
    repo = tmp_path / "code"
    repo.mkdir()
    monkeypatch.setattr(runner, "ROOT", repo)
    paths = runner.locations()
    paths["root"].parent.mkdir(parents=True)
    events = []
    approval = dict(scope={name:True for name in freeze.APPROVAL_FIELDS})
    monkeypatch.setattr(runner.operating, "readiness_check", lambda *a: events.append("readiness"))
    monkeypatch.setattr(runner.freeze, "authorization_check", lambda *a: approval)
    monkeypatch.setattr(runner.operating, "resolve_default_transport", lambda: events.append("transport"))
    monkeypatch.setattr(runner, "full_funding", lambda p: events.append("funding"))
    def observe():
        events.append("metadata")
        return {"fabricated":True}, 1
    monkeypatch.setattr(runner, "observe_metadata", observe)
    monkeypatch.setattr(runner, "read_secret", lambda repo: events.append("key"))
    manifest = dict(operating_readiness=dict(path=freeze.READINESS_FILE, sha256="b"*64),
        operating_authorization=dict(path=freeze.AUTHORIZATION_FILE, sha256="c"*64),
        prior_entries={}, pre_stage_accounted_usd="0", pre_stage_unused_commitments_usd="0")
    monkeypatch.setattr(runner, "inspect", lambda *a: (paths, manifest))
    monkeypatch.setattr(runner.freeze, "verify", lambda *a: (manifest, PROTOCOL))
    monkeypatch.setattr(runner, "_own_source", lambda *a: None)
    def prepare(*args, **kwargs):
        events.append("prepare")
        manifest["sources"] = {"fabricated.py":"d"*64}
        return PROTOCOL
    monkeypatch.setattr(runner.freeze, "prepare", prepare)
    return paths, manifest, events


def test_prepare_resolves_defaults_and_funding_before_single_get_no_key(private):
    paths, manifest, events = private
    result = runner.prepare(paths["root"], readiness_sha256="b"*64, authorization_sha256="c"*64)
    assert events == ["readiness", "funding", "transport", "metadata", "prepare"]
    assert result["protocol"] == PROTOCOL and not result["launch_authorized"]
    assert not result["actual_model_calls"]


def test_insufficient_total15_balance_cannot_fund_full_design_before_fetch_or_key(tmp_path, monkeypatch):
    # Real admission implementation; PRIVATE ledger with copied immutable authority.
    import shutil
    repo = Path(__file__).resolve().parents[1]
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "entries").mkdir()
    for name in budget.AUTHORITY_FILES:
        shutil.copy2(repo / "results/paper3/pivot_b_budget" / name, ledger / name)
    atomic(ledger / "entries/old.json", dict(stage="old", status="reserved", reserved_usd="9.608958611"))
    before = (ledger / "entries/old.json").read_bytes()
    with pytest.raises(ValueError, match="full16-assignment budget"):
        runner.full_funding(dict(ledger=ledger))
    assert (ledger / "entries/old.json").read_bytes() == before
    assert not (ledger / "stages").exists()


def test_prepare_budget_failure_cannot_fetch_or_create(private, monkeypatch):
    paths, _, events = private
    def denied(*args):
        raise ValueError("full16-assignment budget")
    monkeypatch.setattr(runner, "full_funding", denied)
    with pytest.raises(ValueError, match="budget"):
        runner.prepare(paths["root"], readiness_sha256="b"*64, authorization_sha256="c"*64)
    assert events == ["readiness"] and not paths["root"].exists()


def test_total15_funds_unchanged_full_pilot_without_spending(tmp_path):
    import shutil
    repo = Path(__file__).resolve().parents[1]
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "entries").mkdir()
    for name in budget.AUTHORITY_FILES:
        shutil.copy2(repo / "results/paper3/pivot_b_budget" / name, ledger / name)
    atomic(ledger / "entries/old.json", dict(stage="old", status="reserved", reserved_usd="6.608958611"))
    before = (ledger / "entries/old.json").read_bytes()
    result = runner.full_funding(dict(ledger=ledger))
    assert result["full_bound_usd"] == "7.52973222"
    assert result["accounted_usd"] == "6.608958611"
    assert budget.TOTAL_CAP == 15
    assert (ledger / "entries/old.json").read_bytes() == before
    assert not (ledger / "stages").exists()
    assert runner.journal.load(ledger / budget.PREVIOUS_EXTENSION_FILE)["new_total_cap_usd"] == "12.00"


def test_prepare_readiness_failure_cannot_fetch_or_allocate(private, monkeypatch):
    def failed(*args):
        raise ValueError("fabricated stale readiness")
    monkeypatch.setattr(runner.operating, "readiness_check", failed)
    with pytest.raises(ValueError, match="stale readiness"):
        runner.prepare(private[0]["root"], readiness_sha256="b"*64, authorization_sha256="c"*64)
    assert not private[2]


@pytest.mark.parametrize("name", ["arbitrary", "pivot_b_retrospective_billing_discovery_v1"])
def test_wrong_or_old_root_refused_before_checks(private, name):
    paths, _, events = private
    with pytest.raises(ValueError, match="exact fresh operating root"):
        runner.prepare(paths["root"].parent / name, readiness_sha256="b"*64, authorization_sha256="c"*64)
    assert not events


def test_existing_root_never_reprepared(private):
    paths, _, events = private
    paths["root"].mkdir()
    with pytest.raises(ValueError, match="never reprepare"):
        runner.prepare(paths["root"], readiness_sha256="b"*64, authorization_sha256="c"*64)
    assert not events


@pytest.mark.parametrize("batch", [True, -1, 2, "0", None])
def test_invalid_run_batch_never_reads_key(private, batch):
    with pytest.raises(ValueError, match="explicit batch"):
        runner.run(private[0]["root"], PROTOCOL, batch)
    assert not private[2]


@pytest.mark.parametrize("marker", ["block-0", "sessions/block-0-start.json", "sessions/start.json"])
def test_ambiguous_or_started_first_block_never_reads_key(private, marker):
    paths, _, events = private
    path = paths["root"] / marker
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    with pytest.raises(ValueError, match="already started"):
        runner.run(paths["root"], PROTOCOL, 0)
    assert events == ["transport"]


def test_second_block_needs_terminal_and_archive_before_key(private):
    paths, _, events = private
    with pytest.raises(ValueError, match="terminal first block"):
        runner.run(paths["root"], PROTOCOL, 1)
    terminal = paths["root"] / "sessions/block-0-terminal.json"
    terminal.parent.mkdir(parents=True)
    terminal.touch()
    with pytest.raises(ValueError, match="partial archive"):
        runner.run(paths["root"], PROTOCOL, 1)
    assert "key" not in events and "metadata" not in events


def test_second_block_defers_single_get_until_coordinator_after_replay(private, monkeypatch):
    paths, _, events = private
    terminal = paths["root"] / "sessions/block-0-terminal.json"
    terminal.parent.mkdir(parents=True)
    terminal.touch()
    directory, zipped = runner.destinations(paths, 0)
    directory.mkdir(parents=True)
    zipped.touch()  # PRIVATE placeholder; no valid replay certificate implied.
    def operate(*args, **kwargs):
        assert "metadata" not in events
        assert kwargs["partial_directory"] == directory and kwargs["partial_zip"] == zipped
        assert kwargs["observe_metadata"] is runner.observe_metadata
        events.append("coordinator-with-deferred-observer")
        return {"fabricated":True}
    monkeypatch.setattr(runner.operating, "run_block", operate)
    runner.run(paths["root"], PROTOCOL, 1)
    assert events == ["transport", "key", "coordinator-with-deferred-observer"]


@pytest.mark.parametrize("operation", ["audit", "close", "export"])
def test_offline_operations_never_read_key_or_fetch_metadata(private, monkeypatch, operation):
    paths, _, events = private
    report = dict(blocks=[dict(evidence={"fabricated":True}), dict(evidence=None)])
    monkeypatch.setattr(runner.coordinator, "audit", lambda *a: deepcopy(report))
    monkeypatch.setattr(runner.coordinator, "close_terminal_block", lambda *a: {"fake-close":True})
    monkeypatch.setattr(runner.archive, "export", lambda *a: {"fake-export":True})
    result = runner.offline(paths["root"], PROTOCOL, operation, None if operation == "audit" else 0)
    assert result and not events


def test_source_inspection_is_not_key_loading_or_launch(private, monkeypatch):
    # Restore actual inspect (fixture replacement retained via module globals below).
    paths, manifest, events = private
    paths["root"].mkdir()
    actual_inspect = ORIGINAL_INSPECT
    actual_inspect(paths["root"], PROTOCOL)
    assert events == ["readiness"]


ORIGINAL_INSPECT = runner.inspect


@pytest.mark.parametrize("argv", [
    ["--run"], ["--run", "--expected-protocol", PROTOCOL],
    ["--audit", "--expected-protocol", PROTOCOL, "--batch", "0"],
    ["--prepare", "--readiness-sha256", "b"*64],
    ["--prepare", "--readiness-sha256", "b"*64, "--authorization-sha256", "c"*64, "--batch", "0"],
    ["--run", "--audit", "--expected-protocol", PROTOCOL, "--batch", "0"],
])
def test_cli_refuses_incomplete_or_mixed_commands_without_launch(private, argv):
    with pytest.raises(SystemExit) as raised:
        runner.main([str(private[0]["root"]), *argv])
    assert raised.value.code == 2 and not private[2]


def test_help_is_read_only(private):
    with pytest.raises(SystemExit) as raised:
        runner.main(["--help"])
    assert raised.value.code == 0 and not private[2]


def test_secret_loader_owner_only_regular_and_gitignore(tmp_path, monkeypatch):
    # Fake credential in PRIVATE directory; real .env.local is never opened.
    secret = tmp_path / ".env.local"
    secret.write_text("OPENROUTER_API_KEY=fake-unit-token\n")
    secret.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        runner.read_secret(tmp_path)
    secret.chmod(0o600)
    class Result:
        returncode = 1
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: Result())
    with pytest.raises(ValueError, match="git ignored"):
        runner.read_secret(tmp_path)
    Result.returncode = 0
    assert runner.read_secret(tmp_path) == "fake-unit-token"


def test_authorization_grammar_pin_and_scope(tmp_path):
    path = tmp_path / freeze.AUTHORIZATION_FILE
    path.parent.mkdir(parents=True)
    value = dict(format="paper3-anticipation-authorization-v1", human_statement="FABRICATED UNIT TEST",
        source_thread_id="private", approved_at="private", scope={n:True for n in freeze.APPROVAL_FIELDS},
        both_blocks_approved=True, credit_purchases_authorized=False)
    path.write_text(json.dumps(value))
    pin = dict(path=freeze.AUTHORIZATION_FILE, sha256=runner.journal._digest(path))
    assert freeze.authorization_check(tmp_path, pin) == value
    value["both_blocks_approved"] = False
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="external authorization"):
        freeze.authorization_check(tmp_path, pin)
    pin["sha256"] = runner.journal._digest(path)
    with pytest.raises(ValueError, match="full-pilot human evidence"):
        freeze.authorization_check(tmp_path, pin)


def test_public_metadata_entry_is_one_unauthenticated_get(private, monkeypatch):
    opened = []
    class Response:
        def __enter__(self):
            import io
            return io.StringIO('{"fabricated":true}')
        def __exit__(self, *args):
            pass
    class Opener:
        def open(self, url, timeout):
            opened.append((url, timeout))
            return Response()
    monkeypatch.setattr(runner.diagnostic, "opener", lambda: Opener())
    monkeypatch.setattr(runner.route, "check_endpoint", lambda m: None)
    result = ORIGINAL_OBSERVER()
    assert result[0] == {"fabricated":True} and type(result[1]) is float
    assert opened == [(runner.route.METADATA_URL, 20)] and not private[2]


ORIGINAL_OBSERVER = runner.observe_metadata
