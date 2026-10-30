"""Full institution/replay tests with fabricated transport and temporary ledgers."""
from decimal import Decimal
import json
import subprocess
import sys
from threading import Lock
import time
import zipfile

import pytest

from experiments import paper3_retrospective_serial_discovery as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic
from tests.test_paper3_retrospective_deepseek_gate import endpoint
from tests.test_paper3_retrospective_serial_recovery import rejection


@pytest.fixture
def factory(tmp_path, monkeypatch):
    # Collision checking has its own read-only tests; avoid scanning the real
    # 10,000-record history repeatedly in fabricated integration fixtures.
    monkeypatch.setattr(runner.requests, "seed_audit", lambda _: dict(overlap=[], historical_files=0))

    def build(pending=".01"):
        ledger = tmp_path / "ledger"
        (ledger / "entries").mkdir(parents=True)
        atomic(ledger / "authority.json", dict(budget_id=BUDGET_ID, cap_usd="10.00",
                                               credit_purchases_authorized=False))
        atomic(ledger / "entries/old-pending.json", dict(stage="old", status="reserved", reserved_usd=pending))
        atomic(ledger / "entries/old-uncertified.json", dict(stage="old", status="settled",
            reserved_usd=".01", accounted_usd=".01", certified=False))
        root = tmp_path / "run"
        protocol = runner.prepare(root, ledger, endpoint())
        return root, ledger, protocol
    return build


@pytest.fixture
def prepared(factory):
    return factory()


def fake(prepared, batch=0, faults=None, policy=0, charge=".0001"):
    root, ledger, _ = prepared
    now, sent = [time.time()], []
    guard = Lock()
    faults = faults or {}

    def sleep(seconds):
        now[0] += seconds

    def send(wire, secret):
        request = json.loads(wire)
        with guard:
            sent.append(request)
            number = len(sent)
        fault = faults.get(number)
        if fault in ("429", "quota", "502"):
            stream = rejection()["stream"]
            stream.update(started_unix=now[0], ended_unix=now[0])
            if fault == "502":
                stream["http_status"] = 502
            if fault == "quota":
                error = json.loads(stream["http_error_body"])
                error["error"]["metadata"]["limit_source"] = "account"
                stream["http_error_body"] = json.dumps(error)
            return stream
        value = json.loads(request["messages"][1]["content"])
        stage = value["stage"]
        action = (dict(policy=policy, message="fabricated") if stage in ("draft", "final") else
                  dict(support=True, counter_policy=policy, message="fabricated") if stage == "response" else
                  dict(vote=policy != 0))
        if fault == "bad":
            action["extra"] = True
        frames = [dict(id=f"fixture-b{batch}-{number}", model=runner.route.MODEL_ALIAS,
            provider=runner.route.PROVIDER, choices=[dict(index=0,
            delta=dict(reasoning="" if fault == "no_native" else "fabricated"), finish_reason=None)]),
            dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0, id="one", type="function",
                function=dict(name="submit_decision", arguments=json.dumps(action)))]), finish_reason="tool_calls")]),
            dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=100, cost=float(charge)))]
        return dict(http_status=200, error_type=None, secret_redacted=False,
            lines=[line for frame in frames for line in ("data: " + json.dumps(frame), "")] + ["data: [DONE]", ""],
            started_unix=now[0], ended_unix=now[0])

    def lookup(gid, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
            data=dict(id=gid, model=runner.route.MODEL_ALIAS, provider_name=runner.route.PROVIDER,
                      total_cost=float(charge)))

    result = runner.execute(root, batch, ledger, send=send, lookup=lookup, secret="fixture-secret",
                            metadata=endpoint(), metadata_observed_unix=now[0],
                            clock=lambda: now[0], sleep=sleep)
    return result, sent


def replay(prepared, tmp_path, label):
    root, ledger, protocol = prepared
    target, archive = tmp_path / (label + "-portable"), tmp_path / (label + ".zip")
    runner.auditor().export(root, ledger, target, archive)
    fresh = tmp_path / (label + "-fresh")
    with zipfile.ZipFile(archive) as z:
        z.extractall(fresh)
    process = subprocess.run([sys.executable, "-I", "-S",
        str(fresh / "code/experiments/paper3_retrospective_serial_discovery.py"), str(fresh),
        "--replay", "--expected-protocol", protocol], capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["portable_replay"]["exact_report_match"]
    return report


def test_both_frames_all16_episodes_and_retained_overload_replay(prepared, tmp_path):
    root, ledger, _ = prepared
    before = {p.name: p.read_bytes() for p in (ledger / "entries").glob("old-*.json")}
    first, sent = fake(prepared, faults={1: "429"})
    assert first["serial_episode_passed"] and len(sent) == 241 and sent[0] == sent[1]
    partial = runner.audit(root, ledger)
    assert partial["completed"] == 8 and len(partial["assignments"]) == 16
    assert partial["selected_case_screen"]["verdict"] == "incomplete" and partial["recoveries"] == 1
    assert replay(prepared, tmp_path, "first")["completed"] == 8
    second, more = fake(prepared, batch=1)
    assert second["serial_episode_passed"] and len(more) == 240
    report = runner.audit(root, ledger)
    assert report["completed"] == 16 and report["calls"] == 481 and report["new_gate_calls"] == 0
    assert report["selected_case_screen"]["verdict"] == "no_selected_case_lead"
    assert not report["publication_evidence"] and not report["paid_launch_authorized"]
    first_case = runner.t.load(next((runner.batch_root(root, 0) / "recoveries").glob("*.json")))
    failed = runner.t.load(runner.batch_root(root, 0) / "calls" / (first_case["id"] + ".json"))
    assert Decimal(report["accounted_usd"]) == Decimal(".048") + Decimal(failed["reserved_usd"])
    assert before == {name: (ledger / "entries" / name).read_bytes() for name in before}
    assert replay(prepared, tmp_path, "both")["completed"] == 16


@pytest.mark.parametrize("faults", [{1: "bad"}, {1: "no_native"}, {1: "quota"},
                                  {1: "502"}, {1: "429", 2: "429"}])
def test_serial_faults_stop_workers_keep16_and_do_not_become_scientific_null(prepared, faults):
    terminal, sent = fake(prepared, faults=faults)
    report = runner.audit(*prepared[:2])
    assert len(sent) == len(faults) and report["completed"] == 0 and len(report["assignments"]) == 16
    assert not terminal["serial_episode_passed"] and terminal["global_safety_stop"]
    assert report["selected_case_screen"]["verdict"] == "incomplete"
    assert all(a["status"] == "not_started" for a in report["assignments"][1:])
    with pytest.raises(ValueError, match="previous batch"):
        fake(prepared, batch=1)
    with pytest.raises(ValueError, match="restart"):
        fake(prepared)


def test_failed_second_term_preserves_first_term_and_isolated_missingness(prepared, tmp_path):
    _, sent = fake(prepared, faults={16: "bad"})
    report = runner.audit(*prepared[:2])
    assert len(sent) == 16 and report["assignments"][0]["terms"][0] is not None
    assert report["assignments"][0]["terms"][1] is None and report["completed"] == 0
    assert report["selected_case_screen"]["first_terms_available"] == 1
    assert replay(prepared, tmp_path, "partial")["selected_case_screen"]["verdict"] == "incomplete"


def test_all_district_citizen_handover_and_scores_reconstructed(prepared):
    fake(prepared, policy=4)
    fake(prepared, batch=1, policy=4)
    report = runner.audit(*prepared[:2])
    outcomes = [a["outcome"] for a in report["assignments"]]
    assert report["completed"] == 16
    assert all(len(o["cumulative_citizen_utilities"]) == 7 and
               all(len(d) == 9 for d in o["cumulative_citizen_utilities"]) for o in outcomes)
    assert any(any(identity.startswith("successor") for identity in o["terms"][1]["occupants"]) for o in outcomes)


def test_second_full_block_budget_admission_stops_before_allocating(factory):
    prepared = factory(pending="6.77")
    fake(prepared, charge=".001")
    root, ledger, _ = prepared
    before = runner.Ledger(ledger).snapshot()
    assert Decimal(before["accounted_usd"]) + runner.CAP > 10
    with pytest.raises(ValueError, match="ten-dollar"):
        fake(prepared, batch=1)
    assert not list((runner.batch_root(root, 1) / "sessions").iterdir())
    assert runner.Ledger(ledger).snapshot() == before


def test_controller_exception_prefix_retained_but_cause_not_claimed_verified(prepared, tmp_path, monkeypatch):
    original = runner.institution.episode

    def broken(game, arm, ask, on_term=None):
        def checkpoint(term):
            on_term(term)
            raise RuntimeError("fabricated controller fault")
        return original(game, arm, ask, checkpoint)

    monkeypatch.setattr(runner.institution, "episode", broken)
    _, sent = fake(prepared)
    monkeypatch.setattr(runner.institution, "episode", original)
    report = runner.audit(*prepared[:2])
    assert len(sent) == 15 and report["assignments"][0]["status"] == "instrument_error"
    assert report["assignments"][0]["controller_failure_cause_verified"] is False
    assert replay(prepared, tmp_path, "controller")["completed"] == 0


def test_reconstructed_request_or_outcome_tamper_rejected(prepared):
    fake(prepared)
    root, ledger, _ = prepared
    path = next((runner.batch_root(root, 0) / "episodes").glob("*.json"))
    row = runner.t.load(path)
    row["outcome"]["cumulative_district_utilities"][0] += 1
    atomic(path, row)
    with pytest.raises(ValueError, match="outcome mismatch"):
        runner.audit(root, ledger)
