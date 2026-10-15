"""Fabricated transport only: freeze, full path, failure, and portable replay."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from experiments import paper3_agenda_sponsorship_pilot as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic


def _fixture_secret():
    # Keep the exact fake token out of the source-closure credential scan.
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
                              "response_format"],
        pricing=dict(prompt="0.00000008", completion="0.00000028"))]))


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    budget = tmp_path / "budget"
    budget.mkdir()
    atomic(budget / "authority.json", dict(
        budget_id=BUDGET_ID, cap_usd="10.00",
        credit_purchases_authorized=False))
    gate_report = dict(gate_passed=True, calls=10)
    inherited = dict(
        protocol=runner.GATE_PROTOCOL,
        report_sha256=runner.t.sha(runner.t.canonical(gate_report).encode()),
        native_template=runner.request([], 0))
    monkeypatch.setattr(runner, "prerequisite",
                        lambda gate_root=runner.GATE_ROOT,
                        archive_root=runner.GATE_ARCHIVE: inherited)
    monkeypatch.setattr(runner, "prerequisite_paths", lambda *args: [])
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(
        planned_unique=sorted({a["seed_base"] + i for a in runner.assignments()
                               for i in range(runner.design.CALLS_PER_EPISODE)}),
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


def fake(prepared, invalid_first=False):
    root, budget = prepared
    sent = []
    guard = threading.Lock()
    first_seed = runner.assignments()[0]["seed_base"]

    def send(wire, secret):
        request = json.loads(wire)
        seed = request["seed"]
        with guard:
            gid = "fabricated-sponsorship-" + str(len(sent) + 1)
            sent.append(seed)
        task = request["messages"][-1]["content"].split("\n", 1)[1]
        if invalid_first and seed == first_seed:
            answer = '{"policy":"INVALID"}'
        elif task.startswith("Advocate publicly"):
            answer = '{"message":"test"}'
        elif task.startswith("Sponsor exactly"):
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


def test_preflight_and_inherited_endpoint():
    result = runner.scripted_preflight()
    assert result["intended_calls"] == 240
    assert float(result["full_output_scripted_reservations_usd"]) < float(runner.CAP)
    assert result["max_input_bound"] + runner.CONFIG["output_bound"] < (
        runner.gate.channel.CONTEXT)
    assert runner.check_endpoint(metadata())["uptime_last_5m"] == 100


def test_full_fabricated_path_and_exact_isolated_replay(prepared, tmp_path):
    root, budget = prepared
    terminal, sent = fake(prepared)
    assert terminal["interface_gate_passed"] is True
    assert len(sent) == 240
    assert len(set(sent)) == 240
    report = runner.audit(root, budget)
    assert report["completed_episodes"] == 12
    assert report["usable_actions"] == 240
    assert report["all_episodes_complete"] is True
    assert report["selected_case_readout"]["classification"] == (
        "no_prespecified_action_lead")
    export_root = tmp_path / "export"
    archive = tmp_path / "pilot.zip"
    result = runner.export(root, budget, export_root, archive,
                           secret=_fixture_secret())
    assert result["protocol"] == report["protocol"]
    extracted = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extracted)
    command = [sys.executable, "-I", "-S",
               str(extracted / "code/experiments/paper3_agenda_sponsorship_pilot.py"),
               str(extracted), "--replay", "--expected-protocol",
               report["protocol"]]
    completed = subprocess.run(command, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"},
                               capture_output=True, text=True, timeout=90,
                               check=False)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["portable_replay"]["exact_report_match"]


def test_invalid_first_action_stops_all_further_admissions(prepared):
    root, budget = prepared
    terminal, sent = fake(prepared, invalid_first=True)
    assert terminal["interface_gate_passed"] is False
    assert len(sent) == 1
    assert len(terminal["episodes"]) == 12
    assert all(row["status"] == "not_started"
               for row in terminal["episodes"][1:])
    report = runner.audit(root, budget)
    assert report["completed_episodes"] == 0
    assert report["selected_case_readout"]["classification"] == (
        "incomplete_or_control_failed")


def test_pending_predecessor_whitelist(tmp_path):
    budget = tmp_path / "budget"
    (budget / "entries").mkdir(parents=True)
    atomic(budget / "entries/unknown.json", dict(
        request_id="unknown", stage="other-stage", status="reserved",
        reserved_usd="0.01"))
    with pytest.raises(ValueError, match="unknown pending"):
        runner.pending_inventory(budget)
