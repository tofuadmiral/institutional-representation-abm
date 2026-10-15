from decimal import Decimal
import json
import subprocess
import sys
from threading import Lock
import time
import zipfile

import pytest

from experiments import paper3_retrospective_recovery_discovery as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic
from tests.test_paper3_retrospective_contract_gate_v2 import endpoint, fake as fake_gate


@pytest.fixture
def factory(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.gate, "seed_audit", lambda: dict(planned=[], overlap=[], historical_files=0))
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(planned=[], overlap=[], historical_files=0))

    def build(pending=".01"):
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        (ledger / "entries").mkdir()
        atomic(ledger / "authority.json", dict(budget_id=BUDGET_ID, cap_usd="10.00",
                                               credit_purchases_authorized=False))
        atomic(ledger / "entries/old-pending.json", dict(stage="old", status="reserved", reserved_usd=pending))
        atomic(ledger / "entries/old-uncertified.json", dict(stage="old", status="settled",
            reserved_usd=".01", accounted_usd=".01", certified=False))
        gate_root = tmp_path / "gate"
        gate_protocol = runner.gate.prepare(gate_root, metadata=endpoint(), ledger_root=ledger)
        fake_gate((gate_root, ledger, gate_protocol))
        gate_archive = tmp_path / "gate.zip"
        info = runner.gate.export(gate_root, ledger, tmp_path / "gate-portable", gate_archive)
        root = tmp_path / "plan"
        protocol = runner.prepare(root, gate_archive, gate_protocol, info["sha256"], endpoint(), ledger)
        return root, ledger, protocol
    return build


@pytest.fixture
def prepared(factory):
    return factory()


def fake(prepared, batch=0, bad_at=None, transport_at=None, native=True,
         certified=True, prose=False, policy=0, charge=".0001", transport_status=502, overloads=()):
    root, ledger, _ = prepared
    sends, guard = [], Lock()
    previous = runner.batch_root(root, 0) / "sessions/terminal.json"
    now = [max(time.time(), runner.t.load(previous)["ended_unix"] + 1 if previous.exists() else 0)]

    def sleep(seconds):
        now[0] += seconds

    def send(wire, secret):
        request = json.loads(wire)
        with guard:
            sends.append(request)
            n = len(sends)
        if n in overloads:
            from tests.test_paper3_retrospective_contract_recovery import rejection
            stream = rejection()["stream"]
            stream.update(started_unix=now[0], ended_unix=now[0])
            return stream
        if n == transport_at:
            return dict(http_status=transport_status, error_type="HTTPError", secret_redacted=False, lines=[],
                        started_unix=now[0], ended_unix=now[0])
        value = json.loads(request["messages"][1]["content"])
        assert "hypothetical_assumptions" not in value
        stage = value["stage"]
        action = (dict(policy=policy, message="fabricated") if stage in ("draft", "final") else
                  dict(support=True, counter_policy=policy, message="fabricated")
                  if stage == "response" else dict(vote=policy != 0))
        if n == bad_at:
            action["extra"] = True
        gid = f"fixture-b{batch}-{n}"
        frames = [dict(id=gid, model=runner.route.MODEL_ALIAS, provider=runner.route.PROVIDER,
            choices=[dict(index=0, delta=dict(reasoning="fabricated" if native else ""), finish_reason=None)]),
            dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0, id="one", type="function",
                function=dict(name="submit_decision", arguments=json.dumps(action)))]), finish_reason="tool_calls")]),
            dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=100, cost=float(charge),
                                       completion_tokens_details=dict(reasoning_tokens=80)))]
        if prose:
            frames[1] = dict(choices=[dict(index=0, delta=dict(content=json.dumps(action)), finish_reason="stop")])
        return dict(http_status=200, error_type=None, secret_redacted=False,
            lines=[line for f in frames for line in ("data: " + json.dumps(f), "")] + ["data: [DONE]", ""],
            started_unix=now[0], ended_unix=now[0])

    def lookup(gid, secret):
        if not certified:
            return dict(http_status=404, error_type="HTTPError", secret_redacted=False, data=None)
        return dict(http_status=200, error_type=None, secret_redacted=False,
            data=dict(id=gid, model=runner.route.MODEL_ALIAS,
                      provider_name=runner.route.PROVIDER, total_cost=float(charge)))

    terminal = runner.execute(root, batch, ledger, metadata=endpoint(), secret="fixture-secret",
                              send=send, lookup=lookup, clock=lambda: now[0], sleep=sleep)
    return terminal, sends


def replay(prepared, tmp_path, label):
    root, ledger, protocol = prepared
    target, archive = tmp_path / (label + "-portable"), tmp_path / (label + ".zip")
    runner.auditor().export(root, ledger, target, archive)
    fresh = tmp_path / (label + "-fresh")
    with zipfile.ZipFile(archive) as z:
        z.extractall(fresh)
    p = subprocess.run([sys.executable, "-I", "-S",
        str(fresh / "code/experiments/paper3_retrospective_recovery_discovery.py"), str(fresh),
        "--replay", "--expected-protocol", protocol], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    v = json.loads(p.stdout)
    assert v["portable_replay"]["exact_report_match"]
    return v


def test_all16_assignments_frozen_zero_new_gate_calls_and_complete_staging(prepared, tmp_path):
    root, ledger, _ = prepared
    before = {p.name: p.read_bytes() for p in (ledger / "entries").glob("*.json")}
    first, sends = fake(prepared)
    report = runner.audit(root, ledger)
    assert first["serial_episode_passed"] and len(sends) == report["calls"] == 240
    assert report["completed"] == 8 and len(report["assignments"]) == 16
    assert report["selected_case_screen"]["verdict"] == "incomplete"
    assert report["new_gate_calls"] == 0
    assert all(r["status"] == "not_started" for r in report["batches"][1]["assignments"])
    assert replay(prepared, tmp_path, "first")["completed"] == 8
    # Continue prospectively assigned block1 regardless of first-block outcomes.
    fake(prepared, batch=1)
    final = runner.audit(root, ledger)
    assert final["calls"] == 480 and final["completed"] == 16
    assert final["selected_case_screen"]["verdict"] == "no_selected_case_lead"
    assert not final["publication_evidence"]
    assert Decimal(final["accounted_usd"]) == Decimal(".048")
    assert before == {n: (ledger / "entries" / n).read_bytes() for n in before}
    assert replay(prepared, tmp_path, "complete")["completed"] == 16


@pytest.mark.parametrize("options", [dict(bad_at=1), dict(transport_at=1),
                                     dict(transport_at=1, transport_status=429), dict(native=False),
                                     dict(certified=False)])
def test_first_action_fault_blocks_workers_second_batch_and_is_not_null(prepared, options):
    terminal, sends = fake(prepared, **options)
    report = runner.audit(*prepared[:2])
    assert len(sends) == report["calls"] == 1
    assert not terminal["serial_episode_passed"] and terminal["global_safety_stop"]
    assert report["completed"] == 0 and len(report["assignments"]) == 16
    assert report["selected_case_screen"]["verdict"] == "incomplete"
    with pytest.raises(ValueError, match="previous batch incomplete or failed"):
        fake(prepared, batch=1)
    with pytest.raises(ValueError, match="restart"):
        fake(prepared)


def test_partial_first_term_preserved_and_failed_run_replays(prepared, tmp_path):
    _, sends = fake(prepared, bad_at=16)
    report = runner.audit(*prepared[:2])
    assert len(sends) == 16 and report["completed"] == 0
    assert report["assignments"][0]["terms"][0] is not None
    assert report["assignments"][0]["terms"][1] is None
    assert report["selected_case_screen"]["first_terms_available"] == 1
    assert report["selected_case_screen"]["verdict"] == "incomplete"
    assert replay(prepared, tmp_path, "partial")["completed"] == 0


def test_real_handover_all_principal_outcomes_replayed(prepared):
    fake(prepared, policy=4)
    report = runner.audit(*prepared[:2])
    assert report["completed"] == 8
    outcomes = [r["outcome"] for r in report["assignments"] if r["outcome"] is not None]
    assert all(len(o["cumulative_citizen_utilities"]) == 7 and
               all(len(row) == 9 for row in o["cumulative_citizen_utilities"]) for o in outcomes)
    assert any(any(x.startswith("successor") for x in o["terms"][1]["occupants"]) for o in outcomes)


def test_full_first_batch_admission_required_before_allocation(factory):
    with pytest.raises(ValueError, match="ten-dollar"):
        factory(pending="6.81")


def test_qualification_archive_tamper_blocks_before_requests(prepared):
    root, ledger, _ = prepared
    p = root / "qualification.zip"
    p.write_bytes(p.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="qualification archive changed"):
        fake(prepared)
    assert not list((runner.batch_root(root, 0) / "calls").iterdir())


def test_reconstructed_request_and_metrics_tampering_rejected(prepared):
    fake(prepared)
    root, ledger, _ = prepared
    p = next((runner.batch_root(root, 0) / "decisions").glob("*.json"))
    value = runner.t.load(p)
    value["case"]["context"]["actor"] = 99
    atomic(p, value)
    with pytest.raises(ValueError):
        runner.audit(root, ledger)


def test_source_closure_and_bounds_are_complete_before_first_call():
    specification = runner.specification()
    assert len(specification["assignments"]) == 16 and specification["new_gate_calls"] == 0
    assert specification["total_maximum_calls"] == 480
    assert [r["maximum_calls"] for r in specification["batches"]] == [240, 240]
    assert all(Decimal(r["full_reservation_usd"]) <= runner.CAP for r in specification["batches"])
    assert runner.CAP == Decimal("3.30") and runner.route.OUTPUT_BOUND == 14000
    assert {r["seed"] for r in runner.requests.assignments()} == {3711001, 3711002}


def test_worker_failure_retains_inflight_and_stops_new_admissions(prepared, tmp_path):
    terminal, sends = fake(prepared, bad_at=31)
    report = runner.audit(*prepared[:2])
    assert terminal["serial_episode_passed"] and terminal["global_safety_stop"]
    assert len(sends) == report["calls"] == 31
    assert report["completed"] == 1 and report["selected_case_screen"]["verdict"] == "incomplete"
    assert len(report["assignments"]) == 16
    assert replay(prepared, tmp_path, "worker-failure")["calls"] == 31


def test_controller_fault_retains_prefix_without_claiming_cause(prepared, monkeypatch, tmp_path):
    original = runner.action_call

    def fault(assignment, actor, identity, term, stage, context, index):
        if index == 16:
            raise RuntimeError("fabricated controller interruption")
        return original(assignment, actor, identity, term, stage, context, index)

    with monkeypatch.context() as patch:
        patch.setattr(runner, "action_call", fault)
        terminal, sends = fake(prepared)
    report = runner.audit(*prepared[:2])
    assert terminal["global_safety_stop"] and len(sends) == 16
    assert report["assignments"][0]["status"] == "instrument_error"
    assert report["assignments"][0]["controller_failure_cause_verified"] is False
    assert report["assignments"][0]["terms"][0] is not None
    assert report["selected_case_screen"]["verdict"] == "incomplete"
    assert replay(prepared, tmp_path, "controller-failure")["completed"] == 0


@pytest.mark.parametrize("kind", ["citizens", "safety_time"])
def test_saved_principal_or_stop_timing_tamper_rejected(prepared, kind):
    fake(prepared, bad_at=16)
    root, ledger, _ = prepared
    local = runner.batch_root(root, 0)
    if kind == "citizens":
        p = local / "episodes" / (runner.scheduled(0)[0]["id"] + ".json")
        value = runner.t.load(p)
        value["terms"][0]["citizen_utilities"][0][0] += 1
    else:
        p = local / "sessions/safety_stop.json"
        value = runner.t.load(p)
        value["detected_unix"] = 0
    atomic(p, value)
    with pytest.raises(ValueError):
        runner.audit(root, ledger)


@pytest.mark.parametrize("prose", [False, True])
def test_bargaining_full_text_is_valid_not_channel_failure(prepared, prose):
    terminal, sends = fake(prepared, prose=prose)
    report = runner.audit(*prepared[:2])
    assert len(sends) == 240 and terminal["serial_episode_passed"]
    assert report["completed"] == 8


def test_second_block_requires_full_budget_admission(factory):
    prepared = factory(pending="5.50")
    fake(prepared, charge=".007")
    with pytest.raises(ValueError, match="ten-dollar stop"):
        fake(prepared, batch=1)
    assert not list((runner.batch_root(prepared[0], 1) / "calls").iterdir())


def test_answerless429_recovers_without_discarding_failed_attempt_or_changing_wire(prepared, tmp_path):
    terminal, sends = fake(prepared, overloads=(1,))
    root, ledger, _ = prepared
    local = runner.batch_root(root, 0)
    report = runner.audit(root, ledger)
    assert terminal["serial_episode_passed"] and terminal["recoveries"] == 1
    assert len(sends) == report["calls"] == 241 and report["completed"] == 8
    assert sends[0] == sends[1]
    assert report["batches"][0]["logical_actions"] == 240
    first = next(p for p in (local / "calls").glob("*-00-a1.json"))
    # Select the failed entry rather than infer failure from assignment order.
    failed = [runner.t.load(p) for p in (local / "calls").glob("*.json")
              if runner.t.load(p)["stream"]["http_status"] == 429]
    assert len(failed) == 1 and failed[0]["assessment"]["receipt_certified"] is False
    assert Decimal(report["accounted_usd"]) == Decimal(".024") + Decimal(failed[0]["reserved_usd"])
    assert first.exists() and len(list((local / "recoveries").glob("*.json"))) == 1
    assert replay(prepared, tmp_path, "recovered")["calls"] == 241


def test_second429_stops_institution_no_third_attempt_and_replays(prepared, tmp_path):
    terminal, sends = fake(prepared, overloads=(1, 2))
    report = runner.audit(*prepared[:2])
    assert len(sends) == report["calls"] == 2
    assert not terminal["serial_episode_passed"] and terminal["global_safety_stop"]
    assert report["completed"] == 0 and report["batches"][0]["recoveries"] == 1
    assert report["selected_case_screen"]["verdict"] == "incomplete"
    assert len(report["assignments"]) == 16
    assert replay(prepared, tmp_path, "second429")["completed"] == 0


@pytest.mark.parametrize("kind", ["reserve", "delay", "vote", "physical_wire"])
def test_recovered_institution_audit_rejects_tampered_evidence(prepared, kind):
    fake(prepared, overloads=(1,))
    root, ledger, _ = prepared
    local = runner.batch_root(root, 0)
    if kind == "reserve":
        p = next(p for p in (ledger / "entries").glob("*.json")
                 if runner.t.load(p).get("certified") is False and
                 runner.t.load(p)["stage"] == runner.batch_stage(0))
        row = runner.t.load(p)
        row["accounted_usd"] = "0"
    elif kind == "delay":
        p = next((local / "recoveries").glob("*.json"))
        row = runner.t.load(p)
        row["not_before_unix"] -= 1
    elif kind == "physical_wire":
        p = next((local / "attempts").glob("*-a2.json"))
        row = runner.t.load(p)
        row["case"]["request"]["seed"] += 1
    else:
        p = local / "episodes" / (runner.scheduled(0)[0]["id"] + ".json")
        row = runner.t.load(p)
        row["terms"][0]["requested"][0] = not row["terms"][0]["requested"][0]
    atomic(p, row)
    with pytest.raises((ValueError, KeyError)):
        runner.audit(root, ledger)
