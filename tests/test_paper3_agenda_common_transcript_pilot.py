"""Fabricated transport only: no paid calls or behavioral evidence."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from experiments import paper3_agenda_common_transcript_pilot as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic


def _fixture_secret():
    return "fixture-" + "secret"


def metadata():
    channel = runner.gate.channel
    return dict(data=dict(id=channel.MODEL, endpoints=[dict(
        tag=channel.TAG, provider_name=channel.PROVIDER,
        model_id=channel.MODEL, quantization="fp8",
        name=channel.PROVIDER + " | " + channel.MODELS[1],
        status=0, max_completion_tokens=16384, context_length=40960,
        uptime_last_30m=100, uptime_last_5m=100,
        supported_parameters=["reasoning", "max_tokens", "temperature",
                              "top_p", "top_k", "min_p", "seed",
                              "presence_penalty", "repetition_penalty",
                              "response_format", "structured_outputs"],
        pricing=dict(prompt="0.00000008", completion="0.00000028"))]))


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    budget = tmp_path / "budget"
    budget.mkdir()
    atomic(budget / "authority.json", dict(
        budget_id=BUDGET_ID, cap_usd="10.00",
        credit_purchases_authorized=False))
    inherited = dict(protocol=runner.GATE_PROTOCOL,
                     archive_sha256=runner.GATE_ARCHIVE_SHA,
                     report_sha256="fabricated-report",
                     native_template=runner.request([], 0, "vote", ("X", "Y")))
    monkeypatch.setattr(runner, "prerequisite", lambda *args: inherited)
    monkeypatch.setattr(runner, "prerequisite_paths", lambda *args: [])
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(
        planned=sorted({row["seed_base"] + i
                        for row in runner.assignments() for i in range(33)}),
        overlap=[]))
    root = tmp_path / "run"
    runner.prepare(root, metadata=metadata(), ledger_root=budget)
    return root, budget


def trace(answer, gid):
    frames = [dict(id=gid, model=runner.gate.channel.MODELS[1],
                   provider=runner.gate.channel.PROVIDER,
                   choices=[dict(index=0,
                                 delta=dict(reasoning="fabricated reasoning"),
                                 finish_reason=None)]),
              dict(choices=[dict(index=0, delta=dict(content=answer),
                                 finish_reason="stop")]),
              dict(choices=[], usage=dict(prompt_tokens=100,
                                          completion_tokens=100,
                                          cost=.0001,
                                          completion_tokens_details=dict(
                                              reasoning_tokens=80)))]
    lines = [part for frame in frames
             for part in ("data: " + json.dumps(frame), "")]
    lines += ["data: [DONE]", ""]
    return dict(started_unix=time.time(), ended_unix=time.time(),
                http_status=200, generation_header=None, lines=lines,
                line_count=len(lines), byte_count=sum(map(len, lines)),
                error_type=None, secret_redacted=False)


def fake(prepared, invalid_seed=None):
    root, budget = prepared
    sent = []
    guard = threading.Lock()

    def send(wire, secret):
        request = json.loads(wire)
        seed = request["seed"]
        with guard:
            gid = "fabricated-common-" + str(len(sent) + 1)
            sent.append(seed)
        stage = request["response_format"]["json_schema"]["name"].split("_")[-1]
        if seed == invalid_seed:
            answer = '{"vote":true,"reason":"extra"}'
        elif stage == "advocacy":
            answer = '{"message":"test"}'
        elif stage == "sponsor":
            record = json.loads(request["messages"][-1]["content"].split("\n", 1)[0])
            answer = json.dumps(dict(policy=record["compromise_motions"][0]))
        else:
            answer = '{"vote":true}'
        return trace(answer, gid)

    def lookup(gid, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    started_unix=time.time(), ended_unix=time.time(),
                    data=dict(id=gid, model=runner.gate.channel.MODELS[1],
                              provider_name=runner.gate.channel.PROVIDER,
                              total_cost=.0001))

    terminal = runner.execute(root, budget, secret=_fixture_secret(),
                              send=send, lookup=lookup, sleep=lambda _: None)
    return terminal, sent


def test_preflight():
    result = runner.scripted_preflight()
    assert result["intended_calls"] == 396
    assert float(result["full_output_scripted_reservations_usd"]) < float(runner.CAP)
    assert runner.gate.check_endpoint(metadata())["uptime_last_5m"] == 100


def test_full_fabricated_path_and_exact_isolated_replay(prepared, tmp_path):
    root, budget = prepared
    terminal, sent = fake(prepared)
    assert terminal["interface_gate_passed"] is True
    assert len(sent) == len(set(sent)) == 396
    report = runner.audit(root, budget)
    assert report["completed_profiles"] == 12
    assert report["usable_actions"] == 396
    assert report["all_profiles_complete"] is True
    assert report["selected_case_readout"]["classification"] == (
        "no_prespecified_constituent_lead")
    assert all(len(record["advocacy"]) == 7 and
               len(record["arms"]) == 2 for record in report["records"].values())
    export_root = tmp_path / "export"
    archive = tmp_path / "pilot.zip"
    exported = runner.export(root, budget, export_root, archive,
                             secret=_fixture_secret())
    assert exported["protocol"] == report["protocol"]
    extracted = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extracted)
    command = [sys.executable, "-I", "-S",
               str(extracted / "code/experiments/"
                   "paper3_agenda_common_transcript_pilot.py"),
               str(extracted), "--replay", "--expected-protocol",
               report["protocol"]]
    completed = subprocess.run(command, cwd=tmp_path,
                               env={"PATH": "/usr/bin:/bin"},
                               capture_output=True, text=True,
                               timeout=120, check=False)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["portable_replay"]["exact_report_match"]


def test_invalid_first_action_stops_all_further_admissions(prepared):
    root, budget = prepared
    first_seed = runner.assignments()[0]["seed_base"]
    terminal, sent = fake(prepared, invalid_seed=first_seed)
    assert terminal["interface_gate_passed"] is False
    assert sent == [first_seed]
    assert all(row["status"] == "not_started"
               for row in terminal["episodes"][1:])
    report = runner.audit(root, budget)
    assert report["completed_profiles"] == 0
    assert report["selected_case_readout"]["classification"] == (
        "incomplete_or_control_failed")


def test_invalid_ballot_preserves_shared_advocacy_and_action_prefix(prepared):
    root, budget = prepared
    first_seed = runner.assignments()[0]["seed_base"]
    terminal, sent = fake(prepared, invalid_seed=first_seed + 13)
    assert terminal["interface_gate_passed"] is False
    assert len(sent) == 14
    report = runner.audit(root, budget)
    first = report["records"][runner.assignments()[0]["id"]]
    assert first["status"] == "failed"
    assert len(first["advocacy"]) == 7
    assert first["decision_count"] == 14


def test_later_failure_keeps_all_assignments_and_missing_pair(prepared):
    root, budget = prepared
    second = runner.assignments()[1]
    terminal, sent = fake(prepared, invalid_seed=second["seed_base"] + 13)
    assert terminal["interface_gate_passed"] is True
    assert len(terminal["episodes"]) == 12
    assert len(sent) < 396
    report = runner.audit(root, budget)
    assert report["records"][second["id"]]["status"] == "failed"
    assert report["records"][second["id"]]["decision_count"] == 14
    assert report["completed_profiles"] == 11
    assert report["all_profiles_complete"] is False
    assert sum(not row["paired_complete"] for row in
               report["selected_case_readout"]["rows"]) == 1
