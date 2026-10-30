"""Fabricated streams test the frozen runner, never scientific outcomes."""
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

import pytest

from experiments import paper3_direct_ratification_gate as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic


def metadata():
    return dict(data=dict(id=runner.channel.MODEL, endpoints=[dict(
        tag=runner.channel.TAG, provider_name=runner.channel.PROVIDER,
        model_id=runner.channel.MODEL, quantization="fp8",
        name=runner.channel.PROVIDER + " | " + runner.channel.MODELS[1],
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
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(
        planned=list(range(runner.SEED, runner.SEED + 10)), overlap=[]))
    root = tmp_path / "run"
    runner.prepare(root, metadata=metadata(), ledger_root=budget)
    return root, budget


def stream(answer, generation_id, mode="valid"):
    frames = [dict(id=generation_id, model=runner.channel.MODELS[1],
                   provider=runner.channel.PROVIDER,
                   choices=[dict(index=0, delta=dict(reasoning="fabricated reasoning"),
                                 finish_reason=None)]),
              dict(choices=[dict(index=0, delta=dict(content=answer),
                                 finish_reason="stop")]),
              dict(choices=[], usage=dict(prompt_tokens=100,
                                          completion_tokens=100, cost=.0001,
                                          completion_tokens_details=dict(
                                              reasoning_tokens=80)))]
    if mode == "missing_reasoning":
        frames[0]["choices"][0]["delta"] = {}
    lines = [part for frame in frames
             for part in ("data: " + json.dumps(frame), "")]
    lines += ["data: [DONE]", ""]
    return dict(started_unix=time.time(), ended_unix=time.time(),
                http_status=200, generation_header=None, lines=lines,
                line_count=len(lines), byte_count=sum(map(len, lines)),
                error_type=None, secret_redacted=False)


def fake(prepared, mode="valid"):
    root, budget = prepared
    cases = {case["request"]["seed"]: case
             for case in runner.cases()}
    sends = []

    def send(wire, secret):
        request = json.loads(wire)
        case = cases[request["seed"]]
        sends.append(case["id"])
        gid = "fabricated-" + str(len(sends))
        context = case["context"]
        if context["kind"] == "factual":
            answer = dict(context["expected"])
            if mode == "wrong_fact" and len(sends) == 1:
                answer[next(iter(answer))] = "wrong" if isinstance(
                    next(iter(answer.values())), str) else 999
        elif context["stage"] in ("draft", "final"):
            answer = dict(policy="C", message="fixture")
        elif context["stage"] == "response":
            answer = dict(support=True, preferred_policy="C", message="fixture")
        else:
            answer = dict(vote=True)
        raw = json.dumps(answer)
        if mode == "invalid_action" and len(sends) == 7:
            raw = '{"policy":"INVALID","message":"fixture"}'
        return stream(raw, gid, "missing_reasoning" if mode == "missing_reasoning" else "valid")

    def lookup(gid, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    started_unix=time.time(), ended_unix=time.time(),
                    data=dict(id=gid, model=runner.channel.MODELS[1],
                              provider_name=runner.channel.PROVIDER,
                              total_cost=.0001))

    terminal = runner.execute(root, budget, secret="fixture-secret",
                              send=send, lookup=lookup, sleep=lambda _: None)
    return terminal, sends


def test_case_inventory_context_bound_and_no_expected_leak():
    cases = runner.cases()
    assert len(cases) == 10
    assert sum(Decimal(c["reserved_usd"]) for c in cases) <= runner.CAP
    assert [c["context"]["kind"] for c in cases] == ["factual"] * 6 + ["action"] * 4
    for case in cases:
        assert case["request"]["response_format"] == dict(type="json_object")
        assert case["request"]["reasoning"] == dict(enabled=True, exclude=False)
        assert case["request"]["provider"]["only"] == [runner.channel.TAG]
        assert not case["request"]["provider"]["allow_fallbacks"]
        assert case["input_token_bound"] + runner.CONFIG["output_bound"] <= runner.channel.CONTEXT
        assert "expected" not in json.dumps(case["request"])


def test_complete_gate_and_exact_portable_replay(prepared, tmp_path):
    terminal, sends = fake(prepared)
    report = runner.audit(*prepared)
    assert not terminal["global_safety_stop"]
    assert report["gate_passed"] and report["correct_and_valid"] == 10
    assert report["calls"] == len(sends) == 10
    assert Decimal(report["accounted_usd"]) == Decimal("0.0010")
    with pytest.raises(ValueError, match="already started"):
        runner.execute(*prepared)
    target, archive = tmp_path / "portable", tmp_path / "archive.zip"
    info = runner.export(*prepared, target, archive)
    fresh = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(fresh)
    result = subprocess.run([sys.executable, "-I", "-S",
                             str(fresh / "code/experiments/paper3_direct_ratification_gate.py"),
                             str(fresh), "--replay", "--expected-protocol",
                             info["protocol"]], env={}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    replay = json.loads(result.stdout)
    assert replay.pop("portable_replay")["exact_report_match"]
    assert replay == report


@pytest.mark.parametrize("mode,expected", [("wrong_fact", 1),
                                            ("invalid_action", 7),
                                            ("missing_reasoning", 1)])
def test_first_failure_stops_without_repair(prepared, mode, expected):
    terminal, sends = fake(prepared, mode)
    report = runner.audit(*prepared)
    assert not report["gate_passed"]
    assert len(sends) == expected
    assert all(row["status"] == "not_started"
               for row in report["assignments"][expected:])
    if mode == "missing_reasoning":
        assert terminal["global_safety_stop"]


def test_seed_overlap_detected(tmp_path):
    directory = tmp_path / "results/paper3/old"
    directory.mkdir(parents=True)
    atomic(directory / "manifest.json", dict(protocol=dict(seed=runner.SEED + 3)))
    with pytest.raises(ValueError, match="overlap"):
        runner.seed_audit(tmp_path)


def test_budget_guard(prepared):
    root, budget = prepared
    ledger = runner.Ledger(budget)
    ledger.allocate("earlier", "10")
    ledger.reserve("earlier", "old", "9.99", "0" * 64)
    with pytest.raises(ValueError, match="shared budget changed"):
        runner.execute(root, budget)


def test_frozen_source_tamper_rejected(prepared):
    root, budget = prepared
    path = root / "sources.json"
    source = runner.t.load(path)
    source[next(iter(source))] += "\n# tampered\n"
    atomic(path, source)
    with pytest.raises(ValueError, match="source changed"):
        runner.verify(root)
