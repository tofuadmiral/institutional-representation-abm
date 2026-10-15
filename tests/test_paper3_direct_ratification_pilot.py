"""Offline fabricated full-path/failure/replay tests; no research observations."""
import json
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from experiments import paper3_direct_ratification_pilot as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic


def metadata():
    c = runner.gate.channel
    return dict(data=dict(id=c.MODEL, endpoints=[dict(
        tag=c.TAG, provider_name=c.PROVIDER, model_id=c.MODEL,
        quantization="fp8", name=c.PROVIDER + " | " + c.MODELS[1],
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
    prerequisite = dict(protocol=runner.GATE_PROTOCOL,
                        report=dict(gate_passed=True, calls=10))
    prerequisite["report_sha256"] = runner.t.sha(
        runner.t.canonical(prerequisite["report"]).encode())
    prerequisite["native_template"] = runner.requests.request([], 0)
    monkeypatch.setattr(runner, "prerequisite", lambda gate_root=runner.GATE_ROOT: prerequisite)
    monkeypatch.setattr(runner, "prerequisite_paths", lambda *args: [])
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(
        planned_unique=sorted({a["seed_base"] + i for a in runner.assignments()
                               for i in range(16)}), overlap=[]))
    root = tmp_path / "run"
    runner.prepare(root, metadata=metadata(), ledger_root=budget)
    return root, budget


def trace(answer, gid, mode="valid"):
    frames = [dict(id=gid, model=runner.gate.channel.MODELS[1],
                   provider=runner.gate.channel.PROVIDER,
                   choices=[dict(index=0, delta=dict(reasoning="fabricated reasoning"),
                                 finish_reason=None)]),
              dict(choices=[dict(index=0, delta=dict(content=answer),
                                 finish_reason="stop")]),
              dict(choices=[], usage=dict(prompt_tokens=100,
                                          completion_tokens=100,
                                          cost=.0001,
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
    sent = []
    lock = threading.Lock()
    first_seeds = {a["seed_base"] for a in runner.assignments()}

    def send(wire, secret):
        request = json.loads(wire)
        seed = request["seed"]
        with lock:
            gid = "fabricated-" + str(len(sent) + 1)
            sent.append(seed)
        if mode == "invalid_first_action" and seed in first_seeds:
            answer = '{"policy":"INVALID","message":""}'
        else:
            task = request["messages"][-1]["content"].split("\n", 1)[1]
            if task.startswith("Choose an opening") or task.startswith("Choose the final"):
                answer = '{"policy":"C","message":"fixture"}'
            elif task.startswith("Respond"):
                answer = '{"support":true,"preferred_policy":"C","message":"fixture"}'
            else:
                answer = '{"vote":true}'
        return trace(answer, gid,
                     "missing_reasoning" if mode == "missing_reasoning" else "valid")

    def lookup(gid, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    started_unix=time.time(), ended_unix=time.time(),
                    data=dict(id=gid, model=runner.gate.channel.MODELS[1],
                              provider_name=runner.gate.channel.PROVIDER,
                              total_cost=.0001))

    terminal = runner.execute(root, budget, secret="fixture-secret",
                              send=send, lookup=lookup, sleep=lambda _: None)
    return terminal, sent


def test_preflight_and_unique_seeds():
    spec = runner.specification()
    assert spec["max_calls"] == 256
    assert spec["scripted_preflight"]["intended_calls"] == 256
    assert spec["scripted_preflight"]["distinct_request_seeds"] == 256
    assert float(spec["scripted_preflight"]["full_output_scripted_reservations_usd"]) < float(runner.CAP)
    assert len({a["seed_base"] + i for a in runner.assignments() for i in range(16)}) == 256


def test_prerequisite_freezes_bundle_manifest_not_every_duplicate_payload():
    paths = runner.prerequisite_paths()
    assert len(paths) == 16
    assert runner.GATE_ARCHIVE / "bundle.json" in paths
    assert runner.GATE_ARCHIVE / "expected_report.json" in paths
    assert runner.GATE_ROOT / "sources.json" in paths
    assert all(path.is_file() for path in paths)


def test_fabricated_full_path_archive_and_replay(prepared, tmp_path):
    terminal, sent = fake(prepared)
    report = runner.audit(*prepared)
    assert not terminal["global_safety_stop"]
    assert report["feasibility_passed"]
    assert report["completed_episodes"] == 16
    assert report["usable_actions"] == len(sent) == 256
    assert report["readout"]["completed_pairs"] == 8
    assert not report["discovery_triage"]["triage"]
    assert all(x["outcome"]["enacted_policy"] == "C"
               for p in report["readout"]["profiles"]
               for x in p["arms"].values())
    target, archive = tmp_path / "portable", tmp_path / "archive.zip"
    info = runner.export(*prepared, target, archive)
    fresh = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(fresh)
    result = subprocess.run([sys.executable, "-I", "-S",
                             str(fresh / "code/experiments/paper3_direct_ratification_pilot.py"),
                             str(fresh), "--replay", "--expected-protocol",
                             info["protocol"]], env={}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    replay = json.loads(result.stdout)
    assert replay.pop("portable_replay")["exact_report_match"]
    assert replay == report


def test_invalid_first_actions_retained_without_repair(prepared):
    terminal, sent = fake(prepared, "invalid_first_action")
    report = runner.audit(*prepared)
    assert not report["feasibility_passed"]
    assert report["completed_episodes"] == 0
    assert len(sent) == 16
    assert report["readout"]["completed_pairs"] == 0
    assert not report["discovery_triage"]["triage"]
    assert not terminal["global_safety_stop"]
    assert all(p["arms"][arm]["status"] == "failed"
               for p in report["readout"]["profiles"] for arm in runner.game.ARMS)


def test_reasoning_channel_failure_stops_and_preserves_inventory(prepared):
    terminal, sent = fake(prepared, "missing_reasoning")
    report = runner.audit(*prepared)
    assert terminal["global_safety_stop"]
    assert not report["feasibility_passed"]
    assert report["completed_episodes"] == 0
    assert report["readout"]["assignments"] == 16
    assert 0 < len(sent) <= 4


def test_shared_budget_not_reset(prepared):
    root, budget = prepared
    ledger = runner.Ledger(budget)
    ledger.allocate("earlier", "10")
    ledger.reserve("earlier", "old", "9.99", "0" * 64)
    with pytest.raises(ValueError, match="pre-stage budget changed"):
        runner.execute(root, budget)


def test_source_tamper_rejected(prepared):
    root, budget = prepared
    source = runner.t.load(root / "sources.json")
    source[next(iter(source))] += "\n# tampered\n"
    atomic(root / "sources.json", source)
    with pytest.raises(ValueError, match="source changed"):
        runner.verify(root)
