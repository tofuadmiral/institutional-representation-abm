"""Fabricated full-path safeguards for holdout batch 1; no model data."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from experiments import paper3_ratification_population_validation_batch1 as runner
from paper3 import direct_ratification as base
from paper3 import ratification_population_design as population
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
    gate_report = dict(gate_passed=True, calls=10)
    prerequisite = dict(
        protocol=runner.GATE_PROTOCOL,
        report_sha256=runner.t.sha(runner.t.canonical(gate_report).encode()),
        native_template=runner.request([], 0))
    monkeypatch.setattr(runner, "prerequisite",
                        lambda gate_root=runner.GATE_ROOT,
                        archive_root=runner.GATE_ARCHIVE: prerequisite)
    monkeypatch.setattr(runner, "prerequisite_paths", lambda *args: [])
    monkeypatch.setattr(runner, "discovery_prerequisite", lambda: dict(
        protocol=runner.DISCOVERY_PROTOCOL,
        report_sha256="f" * 64))
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
    assignments = runner.assignments()
    seed_map = {a["seed_base"] + i: a for a in assignments for i in range(16)}
    first_seeds = {a["seed_base"] for a in assignments}

    def send(wire, secret):
        request = json.loads(wire)
        seed = request["seed"]
        assignment = seed_map[seed]
        with lock:
            gid = "fabricated-" + str(len(sent) + 1)
            sent.append(seed)
        if mode == "invalid_first_action" and seed in first_seeds:
            answer = '{"policy":"INVALID","message":""}'
        else:
            chosen = (assignment["alternative_a"] if
                      mode == "all_alternative" or
                      (assignment["arm"] == "binding_ratification" and
                       assignment["distribution"] == "veto") else
                      assignment["favorite"])
            task = request["messages"][-1]["content"].split("\n", 1)[1]
            if task.startswith("Choose an opening") or task.startswith("Choose the final"):
                answer = json.dumps(dict(policy=chosen, message="x" * 600))
            elif task.startswith("Respond"):
                answer = json.dumps(dict(support=True, preferred_policy=chosen,
                                         message="x" * 600))
            else:
                answer = '{"vote":true}'
        return trace(answer, gid, mode)

    def lookup(gid, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    started_unix=time.time(), ended_unix=time.time(),
                    data=dict(id=gid, model=runner.gate.channel.MODELS[1],
                              provider_name=runner.gate.channel.PROVIDER,
                              total_cost=.0001))

    terminal = runner.execute(root, budget, secret="fixture-secret",
                              send=send, lookup=lookup, sleep=lambda _: None)
    return terminal, sent


def test_offline_opportunity_and_interface():
    assert len(runner.assignments()) == 32
    assert len(runner.profiles()) == 30
    assert runner.scripted_preflight()["intended_calls"] == 512
    assert float(runner.scripted_preflight()[
        "full_output_scripted_reservations_usd"]) < float(runner.CAP)
    for item in (population.game_pair(i) for i in range(9, 17)):
        veto, approve = item["veto"], item["approve"]
        assert base.district_totals(veto) == base.district_totals(approve)
        for profile in (veto, approve):
            messages = {arm: runner.game.messages(
                profile, arm, profile["proposer"], "draft", [])
                for arm in base.ARMS}
            assert messages["advisory_poll"][1] == messages["binding_ratification"][1]
            record = json.loads(messages["advisory_poll"][1]["content"].split("\n", 1)[0])
            assert record["exact_district_utility_sums"] == base.district_totals(profile)
    assert runner.game.parse_action(
        json.dumps(dict(policy="C", message="x" * 1000)), "final")["policy"] == "C"


def test_gate_and_endpoint_inventory():
    paths = runner.prerequisite_paths()
    assert runner.GATE_ARCHIVE / "bundle.json" in paths
    assert runner.DISCOVERY_ARCHIVE / "bundle.json" in paths
    assert runner.check_endpoint(metadata())["uptime_last_5m"] == 100
    degraded = metadata()
    degraded["data"]["endpoints"][0]["uptime_last_5m"] = 80
    with pytest.raises(ValueError, match="uptime"):
        runner.check_endpoint(degraded)


def test_real_discovery_prerequisite_rejects_failed_behavioral_gate(monkeypatch):
    from experiments import paper3_ratification_population_discovery as discovery

    class FakeArchive:
        def verify_bundle(self, root, protocol):
            assert protocol == runner.DISCOVERY_PROTOCOL
            return dict(experiment_family=discovery.STAGE)

    monkeypatch.setattr(runner.archive_source, "archive_helpers",
                        lambda: FakeArchive())
    monkeypatch.setattr(runner.t, "load", lambda path: dict(
        protocol=runner.DISCOVERY_PROTOCOL, feasibility_passed=True,
        discovery_triage=False))
    with pytest.raises(ValueError, match="discovery action gate"):
        runner.discovery_prerequisite("fabricated", "fabricated-archive")


def test_fabricated_complete_path_and_isolated_replay(prepared, tmp_path):
    terminal, sent = fake(prepared)
    report = runner.audit(*prepared)
    assert not terminal["global_safety_stop"]
    assert report["feasibility_passed"]
    assert report["completed_episodes"] == 32
    assert report["usable_actions"] == len(sent) == 512
    assert report["behavioral_readout"] == "withheld_until_both_validation_batches_terminal"
    target, archive = tmp_path / "portable", tmp_path / "archive.zip"
    info = runner.export(*prepared, target, archive)
    fresh = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(fresh)
    result = subprocess.run(
        [sys.executable, "-I", "-S",
         str(fresh / "code/experiments/paper3_ratification_population_validation_batch1.py"),
         str(fresh), "--replay", "--expected-protocol", info["protocol"]],
        env={}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    replay = json.loads(result.stdout)
    assert replay.pop("portable_replay")["exact_report_match"]
    assert replay == report


def test_no_interim_behavioral_report_for_a_different_fabricated_policy(prepared):
    fake(prepared, "all_alternative")
    report = runner.audit(*prepared)
    assert report["feasibility_passed"]
    assert report["behavioral_readout"] == "withheld_until_both_validation_batches_terminal"
    assert "discovery_triage" not in report
    assert "readout" not in report


def test_invalid_actions_keep_all_assignments(prepared):
    terminal, sent = fake(prepared, "invalid_first_action")
    report = runner.audit(*prepared)
    assert not terminal["global_safety_stop"]
    assert not report["feasibility_passed"]
    assert report["completed_episodes"] == 0
    assert len(sent) == 32
    assert report["behavioral_readout"] == "withheld_until_both_validation_batches_terminal"


def test_budget_and_source_tamper_guard(prepared):
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
