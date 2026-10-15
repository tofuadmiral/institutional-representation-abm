"""Offline route-gate semantics, stopping and exact archive replay."""
import json
import os
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from experiments import paper3_route_qwen_gate_v2 as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic


def metadata():
    channel = runner.channel.gate.channel
    return dict(data=dict(id=channel.MODEL, endpoints=[dict(
        tag=channel.TAG, provider_name=channel.PROVIDER, model_id=channel.MODEL,
        quantization="fp8", name=channel.PROVIDER + " | " + channel.MODELS[1],
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
    prior = dict(prior_protocol=runner.PRIOR_PROTOCOL,
                 prior_report_sha256="0" * 64,
                 failed_route_protocol=runner.FAILED_ROUTE_PROTOCOL,
                 failed_route_report_sha256="1" * 64)
    inherited = dict(protocol=runner.channel.GATE_PROTOCOL,
                     report_sha256="2" * 64,
                     native_template=runner.channel.request([], 0))
    monkeypatch.setattr(runner, "prior_done", lambda: prior)
    monkeypatch.setattr(runner.channel, "prerequisite", lambda: inherited)
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(
        planned_unique=list(range(runner.SEED_BASE,
                                  runner.SEED_BASE + runner.MAX_CALLS)),
        overlap=[]))
    root = tmp_path / "run"
    runner.prepare(root, metadata=metadata(), ledger_root=budget)
    return root, budget


def trace(answer, gid):
    frames = [dict(id=gid, model=runner.channel.gate.channel.MODELS[1],
                   provider=runner.channel.gate.channel.PROVIDER,
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


def fake(prepared, mode="exact"):
    root, budget = prepared
    sent = []
    lock = threading.Lock()
    cases = {runner.SEED_BASE + i: case for i, case in
             enumerate(runner.gate.cases())}

    def send(wire, secret):
        request = json.loads(wire)
        seed = request["seed"]
        case = cases[seed]
        with lock:
            gid = "fabricated-" + str(len(sent) + 1)
            sent.append(case["name"])
        if case["kind"] == "rule":
            answer = dict(case["expected"], optional_reason="fixture")
            if mode == "wrong" and case["name"] == "rule-00":
                answer["review_veto_applies"] = not answer["review_veto_applies"]
        else:
            answer = dict(case["expected"], optional_reason="fixture")
            if case["stage"] == "offer":
                answer["route"] = "floor"
        return trace(json.dumps(answer), gid)

    def lookup(gid, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    started_unix=time.time(), ended_unix=time.time(),
                    data=dict(id=gid, model=runner.channel.gate.channel.MODELS[1],
                              provider_name=runner.channel.gate.channel.PROVIDER,
                              total_cost=.0001))

    terminal = runner.execute(root, budget,
                              secret="-".join(("fixture", "secret")),
                              send=send, lookup=lookup, sleep=lambda _: None)
    return terminal, sent


def replay_archive(prepared, tmp_path, report):
    root, budget = prepared
    export_dir, archive = tmp_path / "export", tmp_path / "archive.zip"
    bundle = runner.export(root, budget, export_dir, archive,
                           "-".join(("fixture", "secret")))
    assert bundle["protocol"] == report["protocol"]
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(fresh)
    completed = subprocess.run(
        [sys.executable, "-I", "-S",
         "code/experiments/paper3_route_qwen_gate_v2.py", ".",
         "--replay", "--expected-protocol", report["protocol"]],
        cwd=fresh, env={"PATH": os.environ.get("PATH", "")},
        text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout)["portable_replay"]["exact_report_match"]


def test_clarified_gate_and_reservation():
    cases = runner.gate.cases()
    assert len(cases) == runner.MAX_CALLS == 12
    assert float(runner.preflight()["full_case_reservation_usd"]) < .15
    for case in cases[:8]:
        assert "review_veto_applies" in case["expected"]
        assert "legal authority" in case["messages"][1]["content"]
        assert runner.gate.score(json.dumps(case["expected"]), case)["exact"]
    assert cases[1]["expected"]["review_veto_applies"] is True
    assert cases[1]["expected"]["outcome"] == "q"
    for case in cases[8:]:
        value = dict(case["expected"])
        if case["stage"] == "offer":
            value["route"] = "floor"
        value["incidental_explanation"] = "ignored by prospective projection"
        assert runner.gate.score(json.dumps(value), case)["exact"]


def test_complete_fabricated_gate_and_archive(prepared, tmp_path):
    terminal, sent = fake(prepared)
    assert len(sent) == 12 and terminal["global_safety_stop"] is False
    report = runner.audit(*prepared)
    assert report["recorded"] == report["exact"] == 12
    assert report["gate_passed"] is True
    replay_archive(prepared, tmp_path, report)


def test_wrong_factual_answer_stops_and_replays(prepared, tmp_path):
    terminal, sent = fake(prepared, mode="wrong")
    assert len(sent) <= 3 and terminal["global_safety_stop"] is True
    report = runner.audit(*prepared)
    assert report["gate_passed"] is False
    assert len(report["assignments"]) == 12
    assert report["assignments"][0]["result"]["exact"] is False
    replay_archive(prepared, tmp_path, report)
