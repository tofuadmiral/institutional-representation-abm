"""Fabricated transport and exact replay for the amendment pilot; no paid calls."""
import json
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from experiments import paper3_amendment_pilot as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic


def metadata():
    channel = runner.gate.channel
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
    prior = dict(gate_passed=True, calls=10)
    prerequisite = dict(protocol=runner.GATE_PROTOCOL,
                        report_sha256=runner.t.sha(runner.t.canonical(prior).encode()),
                        native_template=runner.request([], 0))
    monkeypatch.setattr(runner, "prerequisite", lambda *args: prerequisite)
    monkeypatch.setattr(runner, "prerequisite_paths", lambda *args: [])
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(
        planned_unique=sorted({a["seed_base"] + i for a in runner.assignments()
                               for i in range(17)}), overlap=[]))
    root = tmp_path / "run"
    runner.prepare(root, metadata=metadata(), ledger_root=budget)
    return root, budget


def trace(answer, gid, mode="valid"):
    frames = [dict(id=gid, model=runner.gate.channel.MODELS[1],
                   provider=runner.gate.channel.PROVIDER,
                   choices=[dict(index=0, delta=dict(reasoning="fabricated reasoning")
                                 if mode == "valid" else {}, finish_reason=None)]),
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


def fake(prepared, mode="valid"):
    root, budget = prepared
    sent = []
    lock = threading.Lock()
    assignments = runner.assignments()
    seed_map = {a["seed_base"] + i: (a, i) for a in assignments for i in range(17)}

    def send(wire, secret):
        request = json.loads(wire)
        assignment, index = seed_map[request["seed"]]
        item = runner.profiles()[assignment["profile_id"]]
        with lock:
            gid = "fabricated-" + str(len(sent) + 1)
            sent.append(request["seed"])
        stage = ("draft" if index == 0 else "response" if index < 8 else
                 "amendment" if index == 8 else "final" if index == 9 else "vote")
        if mode == "invalid_first_action" and index == 0:
            answer = '{"policy":"INVALID","message":""}'
        elif stage in ("draft", "final"):
            policy = ("C" if stage == "final" and
                      assignment["arm"] == "citizen_veto" else item["favorite"])
            answer = json.dumps(dict(policy=policy, message="x" * 600))
        elif stage == "response":
            answer = json.dumps(dict(support=True, preferred_policy="C",
                                     message="x" * 600))
        elif stage == "amendment":
            policy = ("C" if mode == "valid" and
                      assignment["stratum"] == "mandate_aligned" and
                      assignment["arm"] == "open_amendment" else
                      item["outsider_ideal"])
            answer = json.dumps(dict(policy=policy, message="x" * 600))
        else:
            actor = index - 10
            amendment = ("C" if mode == "valid" and
                         assignment["stratum"] == "mandate_aligned" and
                         assignment["arm"] == "open_amendment" else
                         item["outsider_ideal"])
            votes = (item["compromise_over_favorite"] if amendment == "C"
                     else item["ideal_over_favorite"])
            answer = json.dumps(dict(amendment=actor in votes, final=True))
        return trace(answer, gid, "missing_reasoning" if mode == "missing_reasoning"
                     else "valid")

    def lookup(gid, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    started_unix=time.time(), ended_unix=time.time(),
                    data=dict(id=gid, model=runner.gate.channel.MODELS[1],
                              provider_name=runner.gate.channel.PROVIDER,
                              total_cost=.0001))

    terminal = runner.execute(root, budget, secret="fixture-secret",
                              send=send, lookup=lookup, sleep=lambda _: None)
    return terminal, sent


def test_preflight_and_endpoint():
    preflight = runner.scripted_preflight()
    assert preflight["intended_calls"] == 408
    assert float(preflight["full_output_scripted_reservations_usd"]) < float(runner.CAP)
    assert runner.check_endpoint(metadata())["uptime_last_5m"] == 100
    degraded = metadata()
    degraded["data"]["endpoints"][0]["uptime_last_5m"] = 80
    with pytest.raises(ValueError, match="uptime"):
        runner.check_endpoint(degraded)


def test_real_prerequisite_and_seed_inventory():
    assert runner.prerequisite()["protocol"] == runner.GATE_PROTOCOL
    assert not runner.seed_audit()["overlap"]


def test_fabricated_complete_archive_and_isolated_replay(prepared, tmp_path):
    terminal, sent = fake(prepared)
    report = runner.audit(*prepared)
    assert not terminal["global_safety_stop"]
    assert report["feasibility_passed"]
    assert report["completed_episodes"] == 24
    assert report["usable_actions"] == len(sent) == 408
    assert report["readout"]["triage"]["classification"] == "selected_action_lead"
    target, archive = tmp_path / "portable", tmp_path / "archive.zip"
    info = runner.export(*prepared, target, archive)
    fresh = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(fresh)
    result = subprocess.run([sys.executable, "-I", "-S",
                             str(fresh / "code/experiments/paper3_amendment_pilot.py"),
                             str(fresh), "--replay", "--expected-protocol",
                             info["protocol"]], env={}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    replay = json.loads(result.stdout)
    assert replay.pop("portable_replay")["exact_report_match"]
    assert replay == report


def test_invalid_actions_preserve_all_assignments(prepared):
    terminal, sent = fake(prepared, "invalid_first_action")
    report = runner.audit(*prepared)
    assert not terminal["global_safety_stop"]
    assert len(sent) == 24
    assert report["completed_episodes"] == 0
    assert not report["feasibility_passed"]
    assert report["readout"]["triage"]["classification"] == "not_identified_incomplete"
    assert len(report["readout"]["assignments"]) == 24


def test_reasoning_failure_stops_without_restart(prepared):
    terminal, sent = fake(prepared, "missing_reasoning")
    report = runner.audit(*prepared)
    assert terminal["global_safety_stop"]
    assert not report["feasibility_passed"]
    assert report["completed_episodes"] == 0
    assert 0 < len(sent) <= 4


def test_prelaunch_budget_and_source_guard(prepared):
    root, budget = prepared
    ledger = runner.Ledger(budget)
    ledger.allocate("earlier", "10")
    ledger.reserve("earlier", "old", "9.99", "0" * 64)
    with pytest.raises(ValueError, match="pre-stage budget changed"):
        runner.execute(root, budget)
    source = runner.t.load(root / "sources.json")
    source[next(iter(source))] += "\n# tampered\n"
    atomic(root / "sources.json", source)
    with pytest.raises(ValueError, match="source changed"):
        runner.verify(root)
