"""Offline fixed-opportunity protocol, failure and archive tests; no paid calls."""
import json
import os
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from experiments import paper3_electoral_controlled_opportunity as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic


def metadata():
    channel = runner.base.gate.channel
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
    prior = dict(protocol=runner.PRIOR_PROTOCOL, report_sha256="0" * 64)
    prerequisite = dict(protocol=runner.base.GATE_PROTOCOL,
                        report_sha256="1" * 64,
                        native_template=runner.base.request([], 0))
    monkeypatch.setattr(runner, "prior_done", lambda: prior)
    monkeypatch.setattr(runner.base, "prerequisite", lambda: prerequisite)
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(
        planned_unique=[runner.SEED_BASE + index for index in range(4)],
        overlap=[]))
    root = tmp_path / "run"
    runner.prepare(root, metadata=metadata(), ledger_root=budget)
    return root, budget


def trace(answer, gid):
    frames = [dict(id=gid, model=runner.base.gate.channel.MODELS[1],
                   provider=runner.base.gate.channel.PROVIDER,
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


def fake(prepared, mode="lead"):
    root, budget = prepared
    sent = []
    lock = threading.Lock()
    index = {runner.SEED_BASE + i: row for i, row in
             enumerate(runner.design.inventory())}

    def send(wire, secret):
        request = json.loads(wire)
        item = index[request["seed"]]
        system = request["messages"][0]["content"]
        binding = "The coalition contract is BINDING" in system
        requested = "Citizens see only your REQUESTED ballot." in system
        with lock:
            gid = "fabricated-" + str(len(sent) + 1)
            sent.append((item["id"], binding, requested))
        if mode == "invalid" and item["id"] == "controlled-conflict-c" and binding and requested:
            answer = '{"consent":"bad"}'
        else:
            control = item["id"] in ("controlled-aligned",
                                     "controlled-no-office")
            if binding:
                value = True if control else requested
                answer = json.dumps(dict(consent=value, explanation="fixture"))
            else:
                answer = json.dumps(dict(vote=control, explanation="fixture"))
        return trace(answer, gid)

    def lookup(gid, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    started_unix=time.time(), ended_unix=time.time(),
                    data=dict(id=gid, model=runner.base.gate.channel.MODELS[1],
                              provider_name=runner.base.gate.channel.PROVIDER,
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
    result = subprocess.run(
        [sys.executable, "-I", "-S",
         "code/experiments/paper3_electoral_controlled_opportunity.py", ".",
         "--replay", "--expected-protocol", report["protocol"]],
        cwd=fresh, env={"PATH": os.environ.get("PATH", "")},
        text=True, capture_output=True, check=True)
    assert json.loads(result.stdout)["portable_replay"]["exact_report_match"]


def test_fixed_early_opportunity_and_fresh_profiles():
    assert len(runner.cases()) == 16
    assert float(runner.preflight()["full_case_reservation_usd"]) < .15
    for item in runner.design.inventory():
        assert sum(item["early_consents"].values()) == 3
        assert item["focal_majority_yes"] in (4, 5)
        cases = [row for row in runner.cases()
                 if row["context"]["profile_id"] == item["id"]]
        assert len(cases) == 4
        assert len({row["context"]["seed"] for row in cases}) == 1
        records = {row["context"]["arm"]:
                   json.loads(row["request"]["messages"][1]["content"].split("\n")[0])
                   for row in cases}
        assert (records["binding_requested_record"]["events"] ==
                records["binding_executed_record"]["events"])
        assert (records["promise_requested_record"]["events"] ==
                records["promise_executed_record"]["events"])
        assert all(record["events"][0] == records["binding_requested_record"]["events"][0]
                   for record in records.values())
    table = runner.design.opportunity_audit()
    for profile in ("controlled-conflict-c", "controlled-conflict-d"):
        requested = table[profile]["binding_requested_record"]
        executed = table[profile]["binding_executed_record"]
        best_yes_requested = max(v["payoff"] for key, v in requested.items()
                                 if key.startswith("consent=True"))
        best_no_requested = max(v["payoff"] for key, v in requested.items()
                                if key.startswith("consent=False"))
        best_yes_executed = max(v["payoff"] for key, v in executed.items()
                                if key.startswith("consent=True"))
        best_no_executed = max(v["payoff"] for key, v in executed.items()
                               if key.startswith("consent=False"))
        assert best_yes_requested > best_no_requested
        assert best_no_executed > best_yes_executed
        for arm in ("promise_requested_record", "promise_executed_record"):
            assert (table[profile][arm]["consent=True,requested=False"]["payoff"] >
                    table[profile][arm]["consent=True,requested=True"]["payoff"])
    for profile in ("controlled-aligned", "controlled-no-office"):
        for arm in ("promise_requested_record", "promise_executed_record"):
            assert (table[profile][arm]["consent=True,requested=True"]["payoff"] >
                    table[profile][arm]["consent=True,requested=False"]["payoff"])


def test_complete_selected_case_lead_replays(prepared, tmp_path):
    terminal, sent = fake(prepared)
    assert len(sent) == 16 and terminal["global_safety_stop"] is False
    report = runner.audit(*prepared)
    assert report["all_16_usable"] is True
    assert report["discovery_screen"]["selected_case_lead"] is True
    replay_archive(prepared, tmp_path, report)


def test_invalid_action_remains_missing_and_replays(prepared, tmp_path):
    terminal, sent = fake(prepared, mode="invalid")
    assert len(sent) == 16 and terminal["global_safety_stop"] is False
    report = runner.audit(*prepared)
    assert report["scored_actions"] == 15
    assert report["actions"]["controlled-conflict-c--binding_requested_record"] is None
    assert report["discovery_screen"]["classification"] == "incomplete_not_identified"
    replay_archive(prepared, tmp_path, report)
