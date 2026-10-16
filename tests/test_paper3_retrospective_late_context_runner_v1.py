"""Genuine authority copies, FABRICATED calls/money and actual isolated replay.

No live key is read, no real stage is allocated, and no provider-performance or
strategic evidence is supplied by these fixtures. Private copied ledger only.
"""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

import pytest

from experiments import paper3_retrospective_late_context_gate_v1 as runner
from paper3.pivot_b_budget import atomic
from tests import test_paper3_retrospective_score_ledger_gate_v1 as template


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "entries").mkdir()
    for name in (*runner.budget17.AUTHORITY_FILES, runner.EXTENSION_FILE):
        (ledger / name).write_bytes((runner.BUDGET / name).read_bytes())
    atomic(ledger / "entries/old-pending.json", dict(stage="old", status="reserved", reserved_usd=".01"))
    atomic(ledger / "entries/old-uncertified.json", dict(stage="old", status="settled",
        reserved_usd=".01", accounted_usd=".01", certified=False))
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(planned=[], overlap=[], historical_files=0))
    monkeypatch.setattr(template, "runner", runner)
    monkeypatch.setattr(template.fixtures, "runner", runner)
    monkeypatch.setattr(runner.t, "opener", lambda: pytest.fail("network forbidden in fixture"))
    root = tmp_path / "run"
    protocol = runner.prepare(root, metadata=template.endpoint(), ledger_root=ledger)
    return root, ledger, protocol


def isolated(prepared, tmp_path):
    root, ledger, protocol = prepared
    target, archive = tmp_path / "portable", tmp_path / "archive.zip"
    runner.export(root, ledger, target, archive)
    fresh = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(fresh)
    process = subprocess.run([sys.executable, "-I", "-S",
        str(fresh / "code/experiments/paper3_retrospective_late_context_gate_v1.py"), str(fresh),
        "--replay", "--expected-protocol", protocol], capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["portable_replay"]["exact_report_match"]
    return report


def test_all_sixteen_tasks_exact_isolated_replay_and_no_restart(prepared, tmp_path):
    root, ledger, _ = prepared
    before = {p.name: p.read_bytes() for p in (ledger / "entries").glob("*.json")}
    assert len(template.fake(prepared)) == 16
    report = runner.audit(root, ledger)
    assert report["gate_passed"] and report["calls"] == 16
    assert len(report["assignments"]) == 16 and not report["publication_evidence"]
    assert Decimal(report["accounted_usd"]) == Decimal(".0016")
    assert isolated(prepared, tmp_path)["gate_passed"]
    for name, value in before.items():
        assert (ledger / "entries" / name).read_bytes() == value
    with pytest.raises(ValueError, match="restart"):
        runner.execute(root, ledger, secret="fixture-not-a-live-key")


@pytest.mark.parametrize("channel", ("json", "labelled_json", "fenced_json", "labelled_fenced_json"))
def test_exact_legal_channels_and_full_raw_executed_replay(prepared, tmp_path, channel):
    assert len(template.fake(prepared, channel=channel)) == 16
    report = isolated(prepared, tmp_path)
    assert report["gate_passed"]
    assert all(a["result"]["channel"] == channel for a in report["assignments"])


@pytest.mark.parametrize("options", (dict(native=False), dict(inconsistent_count=True),
    dict(certified=False), dict(channel="both")))
def test_unknown_or_unsafe_evidence_stops_with_all_assignments_retained(prepared, tmp_path, options):
    assert len(template.fake(prepared, **options)) == 1
    report = isolated(prepared, tmp_path)
    assert not report["gate_passed"] and report["global_safety_stop"]
    assert len(report["assignments"]) == 16
    assert sum(r["status"] == "not_started" for r in report["assignments"]) == 15


def test_illegal_typed_votes_fail_gate_without_any_action_coercion(prepared, tmp_path):
    assert len(template.fake(prepared, illegal_vote=True)) == 16
    report = isolated(prepared, tmp_path)
    assert not report["gate_passed"] and not report["global_safety_stop"]
    assert sum(r["failure_scope"] == "episode_failure" for r in report["assignments"]) == 4


def test_single_exact_429_reissue_after_full_cooldown_and_full_reservations(prepared, tmp_path):
    assert len(template.fake(prepared, rate_at=(1,), certified="absent")) == 17
    assert template.fake.times[1] - template.fake.times[0] >= 300
    report = isolated(prepared, tmp_path)
    assert report["gate_passed"] and report["calls"] == 17 and len(report["reissues"]) == 1
    root, _, _ = prepared
    expected = sum(Decimal(json.loads(p.read_text())["reserved_usd"])
                   for p in (root / "calls").glob("*.json"))
    assert Decimal(report["accounted_usd"]) == expected


def test_second_429_is_terminal_and_no_replacement_task(prepared, tmp_path):
    assert len(template.fake(prepared, rate_at=(1, 2))) == 2
    report = isolated(prepared, tmp_path)
    assert not report["gate_passed"] and report["global_safety_stop"]
    assert report["calls"] == 2 and len(report["reissues"]) == 1


def test_output_limit_is_a_gate_failure_not_institution_authority(prepared, tmp_path):
    root, ledger, _ = prepared
    frames = [dict(id="fabricated-length-gate", model=runner.route.MODEL_ALIAS,
        provider=runner.route.PROVIDER, choices=[dict(index=0,
        delta=dict(reasoning="fabricated native channel"), finish_reason=None)]),
        dict(choices=[dict(index=0, delta=dict(content='{"policy":'), finish_reason="length")]),
        dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=14000,
             cost=.0001, completion_tokens_details=dict(reasoning_tokens=14002)))]
    trace = dict(http_status=200, error_type=None, secret_redacted=False,
        lines=[line for frame in frames for line in ("data: " + json.dumps(frame), "")]
              + ["data: [DONE]", ""])
    now = [time.time()]
    def clock():
        return now[0]
    def sleep(seconds):
        now[0] += seconds
    def send(wire, secret):
        value = deepcopy(trace)
        value.update(started_unix=clock(), ended_unix=clock())
        return value
    def lookup(gid, secret):
        return dict(http_status=404, error_type="HTTPError", data=None, secret_redacted=False)
    runner.execute(root, ledger, secret="fixture-not-a-live-key", send=send,
                   lookup=lookup, clock=clock, sleep=sleep)
    report = isolated(prepared, tmp_path)
    assert not report["gate_passed"] and report["calls"] == 1
    assert report["global_safety_stop"]
    assert all(a["result"] is None for a in report["assignments"][1:])


def test_partial_allocation_can_never_restart_even_without_a_start_record(prepared):
    root, ledger, _ = prepared
    value = runner._ledger(ledger, root).allocate(runner.STAGE, runner.CAP)
    atomic(root / "allocation.json", value)
    with pytest.raises(ValueError):
        runner.execute(root, ledger, secret="fixture-not-a-live-key")
    assert not (root / "sessions/start.json").exists()


def test_unhealthy_route_never_creates_root_or_allocation(tmp_path, prepared):
    _, ledger, _ = prepared
    root = tmp_path / "unhealthy"
    metadata = template.endpoint()
    metadata["data"]["endpoints"][0]["status"] = -2
    with pytest.raises(ValueError, match="identity/status"):
        runner.prepare(root, metadata=metadata, ledger_root=ledger)
    assert not root.exists()


def test_actual_root_guard_is_not_a_fabricated_test_bypass():
    with pytest.raises(ValueError, match="only approved"):
        runner._actual_root_guard(Path("/tmp/not-the-approved-run"), runner.BUDGET)


def test_post_response_integrity_failure_prevents_acceptance_and_next_request(prepared, monkeypatch):
    original = runner.verify
    observed = [0]
    def verify(root):
        observed[0] += 1
        if observed[0] == 4:
            raise ValueError("fabricated post-response source divergence")
        return original(root)
    monkeypatch.setattr(runner, "verify", verify)
    assert len(template.fake(prepared)) == 1
    report = runner.audit(*prepared[:2])
    assert not report["gate_passed"] and report["global_safety_stop"]
    assert report["assignments"][0]["result"]["action"] is None
