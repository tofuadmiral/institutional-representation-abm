"""Private operating guards and synthetic account observations; zero API calls."""
from copy import deepcopy
from pathlib import Path
import shutil

import pytest

from experiments import paper3_retrospective_anticipation_recovery_v2 as runner
from paper3 import retrospective_recovery_freeze_v2 as freeze
from paper3.pivot_b_budget import atomic

PROTOCOL = "a" * 64
REPO = Path(__file__).resolve().parents[1]
ORIGINAL_INSPECT = runner.inspect


@pytest.fixture
def private(tmp_path, monkeypatch):
    repo = tmp_path / "code"
    repo.mkdir()
    monkeypatch.setattr(runner, "ROOT", repo)
    paths = runner.locations()
    paths["root"].parent.mkdir(parents=True)
    events = []
    authority = dict(path=freeze.AUTHORIZATION_FILE, sha256="c" * 64)
    monkeypatch.setattr(runner.operating, "readiness_check", lambda *a: events.append("readiness"))
    monkeypatch.setattr(runner.freeze, "authorization_check", lambda *a: authority)
    monkeypatch.setattr(runner.operating, "resolve_default_transport", lambda: events.append("transport"))
    monkeypatch.setattr(runner, "full_funding", lambda *a: events.append("funding"))
    def observe():
        events.append("metadata")
        return dict(fabricated=True), 1
    def account(*args):
        events.append("account")
        return dict(fabricated=True, account_funded=True)
    monkeypatch.setattr(runner, "observe_metadata", observe)
    monkeypatch.setattr(runner, "account_funding", account)
    monkeypatch.setattr(runner, "read_secret", lambda repo: events.append("key"))
    manifest = dict(operating_readiness=dict(path=freeze.READINESS_FILE, sha256="b" * 64),
        operating_authorization=authority, prior_entries={}, pre_stage_accounted_usd="0",
        pre_stage_unused_commitments_usd="0")
    monkeypatch.setattr(runner, "inspect", lambda *a: (paths, manifest))
    monkeypatch.setattr(runner.freeze, "verify", lambda *a: (manifest, PROTOCOL))
    monkeypatch.setattr(runner, "_own_source", lambda *a: None)
    def prepare(*args, **kwargs):
        events.append("prepare")
        paths["root"].mkdir()
        manifest["sources"] = {"fabricated.py": "d" * 64}
        return PROTOCOL
    monkeypatch.setattr(runner.freeze, "prepare", prepare)
    return paths, manifest, events


def prepare(private):
    return runner.prepare(private[0]["root"], readiness_sha256="b" * 64, authorization_sha256="c" * 64)


def test_prepare_checks_authority_research_funds_defaults_and_account_before_one_metadata_get(private):
    result = prepare(private)
    assert private[2] == ["readiness", "funding", "transport", "key", "account", "metadata", "prepare"]
    assert result["protocol"] == PROTOCOL and not result["launch_authorized"]
    assert not result["actual_model_calls"]


@pytest.mark.parametrize("failure", ("full_funding", "account_funding"))
def test_denied_research_or_account_funding_cannot_fetch_metadata_or_create_root(private, monkeypatch, failure):
    def denied(*args):
        raise ValueError("fabricated denied funding")
    monkeypatch.setattr(runner, failure, denied)
    with pytest.raises(ValueError, match="denied funding"):
        prepare(private)
    assert "metadata" not in private[2] and "prepare" not in private[2] and not private[0]["root"].exists()


@pytest.mark.parametrize("name", ("arbitrary", "pivot_b_retrospective_anticipation_v1"))
def test_wrong_or_old_root_refused_before_readiness_key_or_account(private, name):
    with pytest.raises(ValueError, match="exact fresh operating root"):
        runner.prepare(private[0]["root"].parent / name,
            readiness_sha256="b" * 64, authorization_sha256="c" * 64)
    assert not private[2]


def test_existing_root_never_reprepared(private):
    private[0]["root"].mkdir()
    with pytest.raises(ValueError, match="never reprepare"):
        prepare(private)
    assert not private[2]


@pytest.mark.parametrize("batch", (True, -1, 2, "0", None))
def test_invalid_batch_never_reads_key_or_account(private, batch):
    with pytest.raises(ValueError, match="explicit batch"):
        runner.run(private[0]["root"], PROTOCOL, batch)
    assert not private[2]


@pytest.mark.parametrize("marker", ("block-0", "sessions/block-0-start.json", "sessions/start.json"))
def test_started_or_ambiguous_first_block_cannot_be_reissued(private, marker):
    path = private[0]["root"] / marker
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    with pytest.raises(ValueError, match="already started"):
        runner.run(private[0]["root"], PROTOCOL, 0)
    assert private[2] == ["transport"]


def second_paths(private):
    paths, _, _ = private
    terminal = paths["root"] / "sessions/block-0-terminal.json"
    terminal.parent.mkdir(parents=True)
    terminal.touch()
    directory, zipped = runner.destinations(paths, 0)
    directory.mkdir(parents=True)
    zipped.touch()  # PRIVATE placeholder; no actual archive claim.
    return directory, zipped


def test_second_block_defers_account_and_single_route_observation_until_after_replay(private, monkeypatch):
    directory, zipped = second_paths(private)
    def operate(*args, **kwargs):
        assert private[2] == ["transport", "key"]
        assert kwargs["partial_directory"] == directory and kwargs["partial_zip"] == zipped
        private[2].append("coordinator-after-replay")
        result = kwargs["observe_metadata"]()
        assert result == (dict(fabricated=True), 1)
        return dict(fabricated=True)
    monkeypatch.setattr(runner.operating, "run_block", operate)
    runner.run(private[0]["root"], PROTOCOL, 1)
    assert private[2] == ["transport", "key", "coordinator-after-replay", "account", "metadata"]
    assert (private[0]["root"] / "sessions/funding-block-1.json").is_file()


def test_prior_funding_start_attempt_cannot_silently_launch_again(private, monkeypatch):
    second_paths(private)
    atomic(private[0]["root"] / "sessions/funding-block-1.json", dict(fabricated=True))
    monkeypatch.setattr(runner.operating, "run_block", lambda *a, **k: pytest.fail("ambiguous prior attempt"))
    with pytest.raises(ValueError, match="prior funding/start attempt"):
        runner.run(private[0]["root"], PROTOCOL, 1)


@pytest.mark.parametrize("operation", ("audit", "close", "export"))
def test_offline_operations_never_read_key_or_account_or_route(private, monkeypatch, operation):
    report = dict(blocks=[dict(evidence=dict(fabricated=True)), dict(evidence=None)])
    monkeypatch.setattr(runner.coordinator, "audit", lambda *a: deepcopy(report))
    monkeypatch.setattr(runner.coordinator, "close_terminal_block", lambda *a: dict(fake_close=True))
    monkeypatch.setattr(runner.archive, "export", lambda *a: dict(fake_export=True))
    result = runner.offline(private[0]["root"], PROTOCOL, operation, None if operation == "audit" else 0)
    assert result and not private[2]


def test_source_inspection_does_not_load_key_or_fetch(private):
    private[0]["root"].mkdir()
    ORIGINAL_INSPECT(private[0]["root"], PROTOCOL)
    assert private[2] == ["readiness"]


def test_total17_real_copied_financial_history_funds_full_inventory_without_writes(tmp_path):
    ledger = tmp_path / "ledger"
    shutil.copytree(REPO / "results/paper3/pivot_b_budget", ledger)
    before = freeze.inventory(ledger)
    result = runner.full_funding(dict(ledger=ledger))
    assert result["accounted_usd"] == "6.828589091" and result["total_cap_usd"] == "17.00"
    assert result["full_bound_usd"] == "8.78449118" and freeze.inventory(ledger) == before
    assert not (ledger / runner.budget.GROUPS).exists()


def test_nonsecret_account_observation_includes_every_unresolved_reservation(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger"
    shutil.copytree(REPO / "results/paper3/pivot_b_budget", ledger)
    seen = []
    def observe(secret, required):
        assert secret == "private-fake-not-real"
        seen.append(required)
        return dict(account_funded=True)
    monkeypatch.setattr(runner.funding, "observe", observe)
    result = runner.account_funding(dict(ledger=ledger), "private-fake-not-real")
    assert str(seen[0]) == "10.402212691" and result["preserved_unresolved_usd"] == "1.617721511"
    assert "private-fake-not-real" not in str(result)


def test_secret_loader_owner_only_regular_and_gitignored(tmp_path, monkeypatch):
    path = tmp_path / ".env.local"
    path.write_text("OPENROUTER_API_KEY=fake-unit-token\n")
    path.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        runner.read_secret(tmp_path)
    path.chmod(0o600)
    class Result:
        returncode = 1
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: Result())
    with pytest.raises(ValueError, match="git ignored"):
        runner.read_secret(tmp_path)
    Result.returncode = 0
    assert runner.read_secret(tmp_path) == "fake-unit-token"


def test_help_performs_no_checks_or_execution(private):
    with pytest.raises(SystemExit) as raised:
        runner.main(["--help"])
    assert raised.value.code == 0 and not private[2]
