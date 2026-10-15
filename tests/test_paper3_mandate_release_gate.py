"""Fabricated gate tests; no hosted calls or substantive model findings."""

from decimal import Decimal
import json
import subprocess
import sys
import time
import zipfile

import pytest

from experiments import paper3_mandate_release_gate as runner
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
                              "response_format", "structured_outputs"],
        pricing=dict(prompt="0.00000008", completion="0.00000028"))]))


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    budget = tmp_path / "budget"
    budget.mkdir()
    atomic(budget / "authority.json", dict(
        budget_id=BUDGET_ID, cap_usd="10.00",
        credit_purchases_authorized=False))
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(
        planned=list(range(runner.SEED_BASE, runner.SEED_BASE + runner.MAX_CALLS)),
        overlap=[]))
    root = tmp_path / "run"
    runner.prepare(root, metadata=metadata(), ledger_root=budget)
    return root, budget


def stream(answer, generation_id, *, reasoning=True):
    frames = [dict(id=generation_id, model=runner.channel.MODELS[1],
                   provider=runner.channel.PROVIDER,
                   choices=[dict(index=0,
                                 delta=dict(reasoning="fabricated private reasoning")
                                 if reasoning else {}, finish_reason=None)]),
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


def fake(prepared, mode="valid"):
    root, budget = prepared
    cases = {case["request"]["seed"]: case for case in runner.cases()}
    sends = []

    def send(wire, secret):
        case = cases[json.loads(wire)["seed"]]
        sends.append(case["id"])
        stage = case["context"]["stage"]
        if stage in ("draft", "final"):
            answer = dict(second_project="Cedar", coalition=[6, 5, 4, 3],
                          message="scripted")
        elif stage == "response":
            answer = dict(support=True, counter_project="Cedar", message="scripted")
        elif stage == "consent":
            answer = dict(consent=True)
        else:
            answer = dict(vote=True)
        if mode == "extra_reason" and stage == "y_vote":
            answer["reason"] = "extra forbidden field"
        return stream(json.dumps(answer), "fabricated-" + str(len(sends)),
                      reasoning=mode != "missing_reasoning")

    def lookup(gid, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    started_unix=time.time(), ended_unix=time.time(),
                    data=dict(id=gid, model=runner.channel.MODELS[1],
                              provider_name=runner.channel.PROVIDER,
                              total_cost=.0001))

    terminal = runner.execute(root, budget, secret="fixture-secret",
                              send=send, lookup=lookup, sleep=lambda _: None)
    return terminal, sends


def test_gate_inventory_and_strict_schema():
    cases = runner.cases()
    assert len(cases) == runner.MAX_CALLS == 12
    assert sum(Decimal(row["reserved_usd"]) for row in cases) <= runner.CAP
    assert len({row["request"]["seed"] for row in cases}) == 12
    for arm in runner.institution.ARMS:
        assert {row["context"]["stage"] for row in cases
                if row["context"]["arm"] == arm} == {
                    "draft", "response", "final", "consent", "x_vote", "y_vote",
                }
    for row in cases:
        request = row["request"]
        shape = request["response_format"]["json_schema"]["schema"]
        assert request["response_format"]["type"] == "json_schema"
        assert request["response_format"]["json_schema"]["strict"] is True
        assert shape["additionalProperties"] is False
        assert request["reasoning"] == dict(enabled=True, exclude=False)
        assert request["provider"]["only"] == [runner.channel.TAG]
        assert request["provider"]["allow_fallbacks"] is False
        assert row["input_token_bound"] + runner.CONFIG["output_bound"] <= runner.channel.CONTEXT


def test_complete_gate_and_isolated_replay(prepared, tmp_path):
    terminal, sends = fake(prepared)
    report = runner.audit(*prepared)
    assert not terminal["global_safety_stop"]
    assert report["gate_passed"] and report["valid"] == len(sends) == 12
    assert Decimal(report["accounted_usd"]) == Decimal("0.0012")
    with pytest.raises(ValueError, match="already started"):
        runner.execute(*prepared)
    target, archive = tmp_path / "portable", tmp_path / "archive.zip"
    info = runner.export(*prepared, target, archive)
    fresh = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(fresh)
    result = subprocess.run([sys.executable, "-I", "-S",
                             str(fresh / "code/experiments/paper3_mandate_release_gate.py"),
                             str(fresh), "--replay", "--expected-protocol",
                             info["protocol"]], env={}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    replay = json.loads(result.stdout)
    assert replay.pop("portable_replay")["exact_report_match"]
    assert replay == report


@pytest.mark.parametrize("mode,expected", [("extra_reason", 6),
                                             ("missing_reasoning", 1)])
def test_failure_preserves_unstarted_calls(prepared, mode, expected):
    terminal, sends = fake(prepared, mode)
    report = runner.audit(*prepared)
    assert not report["gate_passed"] and len(sends) == expected
    assert all(row["status"] == "not_started"
               for row in report["assignments"][expected:])
    if mode == "missing_reasoning":
        assert terminal["global_safety_stop"]


def test_seed_overlap_detected(tmp_path):
    directory = tmp_path / "results/paper3/old"
    directory.mkdir(parents=True)
    atomic(directory / "manifest.json", dict(protocol=dict(seed=runner.SEED_BASE + 3)))
    with pytest.raises(ValueError, match="overlap"):
        runner.seed_audit(tmp_path)


def test_budget_guard(prepared):
    root, budget = prepared
    ledger = runner.Ledger(budget)
    ledger.allocate("earlier", "10")
    ledger.reserve("earlier", "old", "9.99", "0" * 64)
    with pytest.raises(ValueError, match="shared budget changed"):
        runner.execute(root, budget)
