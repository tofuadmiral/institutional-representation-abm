"""Fabricated transport, billing, freeze and replay tests; no paid calls."""
import json
import os
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from experiments import paper3_electoral_accountability_pilot as runner
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
    prior = dict(protocol=runner.PRIOR_PROTOCOL, report_sha256="0" * 64)
    prerequisite = dict(protocol=runner.GATE_PROTOCOL,
                        report_sha256="1" * 64,
                        native_template=runner.request([], 0))
    monkeypatch.setattr(runner, "prior_done", lambda: prior)
    monkeypatch.setattr(runner, "prerequisite", lambda: prerequisite)
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(
        planned_unique=sorted({runner.GATE_SEED_BASE + index
                               for index in range(4)} |
                              {row["seed_base"] + index
                               for row in runner.assignments()
                               for index in range(14)}), overlap=[]))
    root = tmp_path / "run"
    runner.prepare(root, metadata=metadata(), ledger_root=budget)
    return root, budget


def trace(answer, gid):
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
    mapping = {(row["seed_base"] + index, row["arm"]): (row, index)
               for row in runner.assignments() for index in range(14)}

    def send(wire, secret):
        request = json.loads(wire)
        seed = request["seed"]
        with lock:
            gid = "fabricated-" + str(len(sent) + 1)
            sent.append(seed)
        if seed < runner.EPISODE_SEED_BASE:
            stage = ("consent" if seed in (runner.GATE_SEED_BASE,
                                           runner.GATE_SEED_BASE + 2)
                     else "vote")
            answer = ('{"consent":"bad"}' if mode == "gate_invalid" and
                      seed == runner.GATE_SEED_BASE
                      else '{"consent":true}' if stage == "consent"
                      else '{"vote":true,"reason":"extra field"}')
        else:
            rule_text = request["messages"][0]["content"]
            binding = "The coalition contract is BINDING" in rule_text
            visible = ("requested" if "Citizens see only your REQUESTED ballot."
                       in rule_text else "executed")
            arm = ("binding" if binding else "promise") + "_" + visible + "_record"
            assignment, index = mapping[(seed, arm)]
            stage = "consent" if index < 7 else "vote"
            item = runner.profiles()[assignment["profile_id"]]
            early_order = [i for i in runner.game.ACTORS if i != item["focal"]]
            actor = ((early_order + [item["focal"]])[index]
                     if stage == "consent" else index - 7)
            supporters = {i for i in runner.game.ACTORS
                          if all(c["p"] > 0 for c in
                                 item["profile"]["districts"][f"r{i}"])}
            focal = actor == item["focal"]
            if focal and item["id"].startswith("credit-conflict"):
                value = (assignment["arm"] == "binding_requested_record"
                         if stage == "consent" else False)
            else:
                value = (actor in supporters or focal)
            if mode == "episode_invalid" and assignment["id"] == runner.assignments()[0]["id"] and index == 7:
                answer = '{"vote":"bad"}'
            elif stage == "consent":
                answer = json.dumps(dict(consent=value, message="x" * 1500))
            else:
                answer = json.dumps(dict(vote=value, reason="extra field"))
        return trace(answer, gid)

    def lookup(gid, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    started_unix=time.time(), ended_unix=time.time(),
                    data=dict(id=gid, model=runner.gate.channel.MODELS[1],
                              provider_name=runner.gate.channel.PROVIDER,
                              total_cost=.0001))

    terminal = runner.execute(root, budget, secret="-".join(("fixture", "secret")),
                              send=send, lookup=lookup, sleep=lambda _: None)
    return terminal, sent


def test_preflight_and_paired_cases_are_complete():
    preflight = runner.scripted_preflight()
    assert preflight["intended_calls"] == 228
    assert float(preflight["full_output_scripted_reservations_usd"]) < 1.25
    assert len(runner.gate_cases()) == 4
    assert len(runner.assignments()) == 16
    for item in runner.profiles().values():
        rows = [row for row in runner.assignments()
                if row["profile_id"] == item["id"]]
        assert {row["arm"] for row in rows} == set(runner.game.ARMS)
        assert len({row["seed_base"] for row in rows}) == 1
        first_stage = [runner.game.messages(item["profile"], row["arm"],
                                            next(i for i in runner.game.ACTORS
                                                 if i != item["focal"]),
                                            "consent", [])
                       for row in rows]
        assert len({tuple(message["content"] for message in messages[1:])
                    for messages in first_stage}) == 1
        assert len({messages[0]["content"] for messages in first_stage}) == 4


def test_gate_failure_stops_before_episodes_and_replays(prepared, tmp_path):
    terminal, sent = fake(prepared, mode="gate_invalid")
    assert len(sent) == 1
    assert terminal["gate_passed"] is False
    report = runner.audit(*prepared)
    assert report["gate_passed"] is False
    assert report["completed_episodes"] == 0
    assert report["discovery_screen"]["pathway"] == "incomplete_not_classified"
    assert len(report["assignments"]) == 16
    export_dir, archive = tmp_path / "export", tmp_path / "archive.zip"
    runner.export(*prepared, export_dir, archive,
                  "-".join(("fixture", "secret")))
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(fresh)
    completed = subprocess.run(
        [sys.executable, "-I", "-S",
         "code/experiments/paper3_electoral_accountability_pilot.py", ".",
         "--replay", "--expected-protocol", report["protocol"]],
        cwd=fresh, env={"PATH": os.environ.get("PATH", "")},
        text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout)["portable_replay"]["exact_report_match"]


def test_complete_fabricated_pathway_and_portable_archive(prepared, tmp_path):
    terminal, sent = fake(prepared)
    assert terminal["gate_passed"] is True
    assert len(sent) == 228
    report = runner.audit(*prepared)
    assert report["feasibility_passed"] is True
    assert report["completed_episodes"] == 16
    assert report["discovery_screen"]["pathway"] == "selected_case_mechanism_lead"
    export_dir, archive = tmp_path / "export", tmp_path / "archive.zip"
    bundle = runner.export(*prepared, export_dir, archive,
                           "-".join(("fixture", "secret")))
    assert bundle["protocol"] == report["protocol"]
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(fresh)
    cmd = [sys.executable, "-I", "-S",
           "code/experiments/paper3_electoral_accountability_pilot.py", ".",
           "--replay", "--expected-protocol", report["protocol"]]
    completed = subprocess.run(cmd, cwd=fresh, env={"PATH": os.environ.get("PATH", "")},
                               text=True, capture_output=True, check=True)
    replay = json.loads(completed.stdout)
    assert replay["portable_replay"]["exact_report_match"] is True


def test_failed_episode_kept_in_denominator_and_replays(prepared, tmp_path):
    terminal, sent = fake(prepared, mode="episode_invalid")
    assert terminal["gate_passed"] is True
    assert len(sent) < 228
    report = runner.audit(*prepared)
    assert report["completed_episodes"] == 15
    assert report["discovery_screen"]["pathway"] == "incomplete_not_classified"
    assert report["assignments"][0]["status"] == "failed"
    assert report["readout"]["profiles"][0]["cells"]["binding_requested_record"]["status"] == "failed"
    prefix = report["readout"]["profiles"][0]["cells"]["binding_requested_record"]["prefix"]
    assert len(prefix) == 8
    assert prefix[-1]["stage"] == "vote"
    assert prefix[-1]["result"]["valid_action"] is False
    export_dir, archive = tmp_path / "export", tmp_path / "archive.zip"
    runner.export(*prepared, export_dir, archive,
                  "-".join(("fixture", "secret")))
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(fresh)
    completed = subprocess.run(
        [sys.executable, "-I", "-S",
         "code/experiments/paper3_electoral_accountability_pilot.py", ".",
         "--replay", "--expected-protocol", report["protocol"]],
        cwd=fresh, env={"PATH": os.environ.get("PATH", "")},
        text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout)["portable_replay"]["exact_report_match"]
