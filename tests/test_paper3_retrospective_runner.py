from copy import deepcopy
from decimal import Decimal
import json
import subprocess
import sys
from threading import Lock
import time
import zipfile

import pytest

from experiments import paper3_retrospective_accountability as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic
from paper3.retrospective_execution import StopLedger
from tests.test_paper3_retrospective_requests import endpoint


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    budget = tmp_path / "budget"
    budget.mkdir()
    (budget / "entries").mkdir()
    atomic(budget / "authority.json", dict(budget_id=BUDGET_ID, cap_usd="10.00",
                                          credit_purchases_authorized=False))
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(planned=[], overlap=[], historical_files=0))
    root = tmp_path / "run"
    protocol = runner.prepare(root, metadata=endpoint(), ledger_root=budget)
    return root, budget, protocol


def stream(action, gid, native=True):
    frames = [dict(id=gid, model=runner.requests.MODEL_ALIAS, provider=runner.requests.PROVIDER,
        choices=[dict(index=0, delta=dict(reasoning="fabricated reasoning" if native else ""), finish_reason=None)]),
        dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0, id="one", type="function",
            function=dict(name="submit_decision", arguments=json.dumps(action)))]), finish_reason="tool_calls")]),
        dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=100, cost=.0001,
                                  completion_tokens_details=dict(reasoning_tokens=80)))]
    return dict(http_status=200, error_type=None, secret_redacted=False,
                lines=[item for frame in frames for item in ("data: " + json.dumps(frame), "")] +
                      ["data: [DONE]", ""], started_unix=time.time(), ended_unix=time.time())


def fake(prepared, bad_at=None, native=True, transport_at=None, certified=True, prose=False):
    root, budget, _ = prepared
    sends = []
    guard = Lock()
    facts = {case["request"]["seed"]: case["context"] for case in runner.requests.gate_requests()}

    def send(wire, secret):
        req = json.loads(wire)
        with guard:
            sends.append(req)
            sequence = len(sends)
        case = facts.get(req["seed"])
        if transport_at == sequence:
            return dict(http_status=502, error_type="HTTPError", secret_redacted=False,
                        generation_header=None, lines=[], started_unix=time.time(), ended_unix=time.time())
        if case and case["kind"] == "fact":
            action = deepcopy(case["expected"])
            if bad_at == sequence:
                action[next(key for key, value in action.items() if type(value) is int)] += 1
        else:
            stage = case["stage"] if case else json.loads(req["messages"][1]["content"])["stage"]
            if stage in ("draft", "final"):
                action = dict(policy=0, message="fabricated")
            elif stage == "response":
                action = dict(support=False, counter_policy=0, message="fabricated")
            else:
                action = dict(vote=False)
            if bad_at == sequence:
                action["extra"] = True
        result = stream(action, "fixture-" + str(sequence), native)
        if prose:
            frame = dict(choices=[dict(index=0, delta=dict(content=json.dumps(action)), finish_reason="stop")])
            result["lines"][2:4] = ["data: " + json.dumps(frame), ""]
        return result

    def lookup(gid, secret):
        if not certified:
            return dict(http_status=503, error_type="HTTPError", secret_redacted=False, data=None)
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    data=dict(id=gid, model=runner.requests.MODEL_ALIAS,
                              provider_name=runner.requests.PROVIDER, total_cost=.0001))

    terminal = runner.execute(root, budget, secret="fixture-secret", send=send,
                              lookup=lookup, sleep=lambda _: None)
    return terminal, sends


def test_failed_factual_gate_retains_all_assignments_and_blocks_discovery(prepared):
    terminal, sends = fake(prepared, bad_at=1)
    report = runner.audit(*prepared[:2])
    assert len(sends) == report["calls"] == 1
    assert not terminal["qualified"] and report["completed"] == 0
    assert len(report["qualification"]) == 18 and len(report["assignments"]) == 16
    assert report["selected_case_screen"]["verdict"] == "qualification_failed"


@pytest.mark.parametrize("options", [dict(native=False), dict(transport_at=1),
                                     dict(certified=False), dict(prose=True)])
def test_interface_or_transport_failure_does_not_become_a_scientific_null(prepared, options):
    terminal, sends = fake(prepared, **options)
    report = runner.audit(*prepared[:2])
    assert len(sends) == 1 and not terminal["qualified"]
    assert report["selected_case_screen"]["verdict"] == "qualification_failed"
    if not options.get("certified", True) or options.get("transport_at"):
        assert Decimal(report["accounted_usd"]) > Decimal(".0001")
        assert not report["call_reports"][0]["result"]["usable"]


def test_first_term_survives_second_term_failure_and_no_restart(prepared):
    terminal, sends = fake(prepared, bad_at=34)
    report = runner.audit(*prepared[:2])
    assert terminal["qualified"] and not terminal["serial_episode_passed"]
    assert len(sends) == 34 and report["completed"] == 0
    assert report["assignments"][0]["terms"][0] is not None
    assert report["assignments"][0]["terms"][1] is None
    assert report["selected_case_screen"]["first_terms_available"] == 1
    assert report["selected_case_screen"]["verdict"] == "incomplete"
    with pytest.raises(ValueError, match="restart"):
        runner.execute(*prepared[:2], secret="fixture-secret")


def test_complete_fabricated_run_is_not_scientific_success_and_replays_isolated(prepared, tmp_path):
    terminal, sends = fake(prepared)
    report = runner.audit(*prepared[:2])
    assert terminal["qualified"] and terminal["serial_episode_passed"]
    assert len(sends) == report["calls"] == 498 and report["completed"] == 16
    assert report["selected_case_screen"]["verdict"] == "no_selected_case_lead"
    assert Decimal(report["accounted_usd"]) == Decimal("0.0498")
    export = runner.offline_module("analysis/paper3_retrospective_accountability_audit.py").export
    target, destination = tmp_path / "portable", tmp_path / "archive.zip"
    info = export(*prepared[:2], target, destination)
    fresh = tmp_path / "fresh"
    with zipfile.ZipFile(destination) as bundle:
        bundle.extractall(fresh)
    command = [sys.executable, "-I", "-S", str(fresh / "code/experiments/paper3_retrospective_accountability.py"),
               str(fresh), "--replay", "--expected-protocol", info["protocol"]]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["portable_replay"]["exact_report_match"]


def test_locked_admission_preserves_pending_and_enforces_eight_not_ten(tmp_path):
    (tmp_path / "entries").mkdir()
    atomic(tmp_path / "authority.json", dict(budget_id=BUDGET_ID, cap_usd="10.00",
                                            credit_purchases_authorized=False))
    atomic(tmp_path / "entries/old.json", dict(stage="old", status="reserved", reserved_usd="7.99"))
    ledger = StopLedger(tmp_path)
    ledger.allocate("new", Decimal("1"))
    before = (tmp_path / "entries/old.json").read_bytes()
    with pytest.raises(ValueError, match="eight-dollar"):
        ledger.reserve("new", "new-one", Decimal(".02"), "0" * 64)
    assert (tmp_path / "entries/old.json").read_bytes() == before
    assert not (tmp_path / "entries/new-one.json").exists()
