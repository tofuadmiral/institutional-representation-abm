"""Offline fabricated pilot, including a mechanical-only negative control."""

from decimal import Decimal
import json
import subprocess
import sys
import time
import zipfile

import pytest

from experiments import paper3_mandate_release_pilot as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic


def metadata():
    return dict(data=dict(id=runner.gate.channel.MODEL, endpoints=[dict(
        tag=runner.gate.channel.TAG, provider_name=runner.gate.channel.PROVIDER,
        model_id=runner.gate.channel.MODEL, quantization="fp8",
        name=runner.gate.channel.PROVIDER + " | " + runner.gate.channel.MODELS[1],
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
                     archive_sha256="0" * 64, report_sha256="1" * 64)
    monkeypatch.setattr(runner, "prerequisite", lambda *args, **kwargs: inherited)
    monkeypatch.setattr(runner, "prerequisite_paths", lambda *args, **kwargs: [])
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(
        planned=sorted({row["seed_base"] + index for row in runner.assignments()
                        for index in range(29)}), overlap=[]))
    monkeypatch.setattr(runner.gate.prior_schema, "pending_inventory",
                        lambda root: [])
    runner.specification.cache_clear()
    root = tmp_path / "run"
    runner.prepare(root, metadata=metadata(), ledger_root=budget)
    return root, budget


def stream(answer, generation_id):
    frames = [dict(id=generation_id, model=runner.gate.channel.MODELS[1],
                   provider=runner.gate.channel.PROVIDER,
                   choices=[dict(index=0,
                                 delta=dict(reasoning="fabricated reasoning"),
                                 finish_reason=None)]),
              dict(choices=[dict(index=0, delta=dict(content=answer),
                                 finish_reason="stop")]),
              dict(choices=[], usage=dict(prompt_tokens=100,
                                          completion_tokens=100, cost=.0001,
                                          completion_tokens_details=dict(
                                              reasoning_tokens=80)))]
    lines = [part for frame in frames
             for part in ("data: " + json.dumps(frame), "")]
    lines += ["data: [DONE]", ""]
    return dict(started_unix=time.time(), ended_unix=time.time(),
                http_status=200, generation_header=None, lines=lines,
                line_count=len(lines), byte_count=sum(map(len, lines)),
                error_type=None, secret_redacted=False)


def fake(prepared, *, bad_first=False):
    root, budget = prepared
    sends = []

    def send(wire, secret):
        req = json.loads(wire)
        seed = req["seed"]
        assignment_index = (seed - runner.SEED_BASE) // 64
        assignment = runner.assignments()[assignment_index]
        case = runner.profiles()[assignment["case_id"]]
        stage = req["response_format"]["json_schema"]["name"].removeprefix(
            "paper3_release_")
        sends.append(seed)
        if stage in ("draft", "final"):
            answer = dict(second_project=case.display_projects[0],
                          coalition=[case.display_roles[actor]
                                     for actor in (0, 1, 2, 3)],
                          message="fabricated")
        elif stage == "response":
            answer = dict(support=True, counter_project=case.display_projects[0],
                          message="fabricated")
        elif stage == "consent":
            answer = dict(consent=True)
        else:
            answer = dict(vote=False)
        if bad_first and len(sends) == 1:
            answer["reason"] = "extra forbidden field"
        return stream(json.dumps(answer), "fabricated-" + str(len(sends)))

    def lookup(gid, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    started_unix=time.time(), ended_unix=time.time(),
                    data=dict(id=gid, model=runner.gate.channel.MODELS[1],
                              provider_name=runner.gate.channel.PROVIDER,
                              total_cost=.0001))

    terminal = runner.execute(root, budget, secret="fixture-secret",
                              send=send, lookup=lookup, sleep=lambda _: None)
    return terminal, sends


def test_inventory_and_worst_case_budget():
    assignments = runner.assignments()
    assert len(assignments) == 20
    assert len({row["seed_base"] + index for row in assignments
                for index in range(29)}) == runner.MAX_CALLS == 580
    assert {row["arm"] for row in assignments} == set(runner.institution.ARMS)
    preflight = runner.scripted_preflight()
    assert preflight["intended_calls"] == 580
    assert Decimal(preflight["full_output_scripted_reservations_usd"]) <= runner.CAP
    assert preflight["max_input_bound"] + runner.CONFIG["output_bound"] <= (
        runner.gate.channel.CONTEXT)


def test_first_invalid_action_stops_without_repair(prepared):
    terminal, sends = fake(prepared, bad_first=True)
    report = runner.audit(*prepared)
    assert len(sends) == report["calls"] == 1
    assert not terminal["interface_gate_passed"]
    assert not report["interface_gate_passed"]
    assert report["failed"] == 1 and report["not_started"] == 19
    assert report["selected_case_screen"]["classification"] == (
        "incomplete_or_control_missing")


def test_full_mechanical_difference_is_not_behavioral_lead(prepared, tmp_path):
    terminal, sends = fake(prepared)
    report = runner.audit(*prepared)
    assert terminal["interface_gate_passed"]
    assert report["completed"] == 20 and len(sends) == report["calls"] == 580
    assert report["selected_case_screen"]["classification"] == (
        "no_prespecified_behavioral_lead")
    assert report["selected_case_screen"]["pivotal_release_only"] == 0
    assert any(row["y_changed"] for row in
               report["selected_case_screen"]["rows"] if row["complete"])
    assert Decimal(report["accounted_usd"]) == Decimal("0.058")
    target, archive = tmp_path / "portable", tmp_path / "archive.zip"
    info = runner.export(*prepared, target, archive)
    fresh = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(fresh)
    result = subprocess.run([sys.executable, "-I", "-S",
                             str(fresh / "code/experiments/paper3_mandate_release_pilot.py"),
                             str(fresh), "--replay", "--expected-protocol",
                             info["protocol"]], env={}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    replay = json.loads(result.stdout)
    assert replay.pop("portable_replay")["exact_report_match"]
    assert runner.t.canonical(replay) == runner.t.canonical(report)
