from decimal import Decimal
import json
import subprocess
import sys
import time
import zipfile

import pytest

from experiments import paper3_retrospective_labeled_gate as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic
from tests.test_paper3_retrospective_requests import endpoint


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "entries").mkdir()
    atomic(ledger / "authority.json", dict(budget_id=BUDGET_ID, cap_usd="10.00",
                                           credit_purchases_authorized=False))
    atomic(ledger / "entries/old-pending.json", dict(stage="old", status="reserved", reserved_usd=".01"))
    atomic(ledger / "entries/old-uncertified.json", dict(stage="old", status="settled",
        reserved_usd=".01", accounted_usd=".01", certified=False))
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(planned=[], overlap=[], historical_files=0))
    root = tmp_path / "run"
    protocol = runner.prepare(root, metadata=endpoint(), ledger_root=ledger)
    return root, ledger, protocol


def fake(prepared, bad_at=None, native=True, certified=True):
    lookup_case = {runner.qualification.SEED_BASE + index: case
                   for index, case in enumerate(runner.qualification.cases())}
    sends = []

    def send(wire, secret):
        request = json.loads(wire)
        sends.append(request)
        case = lookup_case[request["seed"]]
        if case["kind"] == "fact":
            action = dict(case["expected"])
            if len(sends) == bad_at:
                field = next(key for key, value in action.items() if type(value) is int)
                action[field] += 1
        elif case["stage"] in ("draft", "final"):
            action = dict(policy=0, message="fabricated")
        elif case["stage"] == "response":
            action = dict(support=False, counter_policy=0, message="fabricated")
        else:
            action = dict(vote=False)
        gid = "fabricated-" + str(len(sends))
        frames = [dict(id=gid, model=runner.route.MODEL_ALIAS, provider=runner.route.PROVIDER,
            choices=[dict(index=0, delta=dict(reasoning="fabricated" if native else ""), finish_reason=None)]),
            dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0, id="one", type="function",
                function=dict(name="submit_decision", arguments=json.dumps(action)))]), finish_reason="tool_calls")]),
            dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=100, cost=.0001,
                                       completion_tokens_details=dict(reasoning_tokens=80)))]
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    lines=[item for frame in frames for item in ("data: " + json.dumps(frame), "")] +
                          ["data: [DONE]", ""], started_unix=time.time(), ended_unix=time.time())

    def lookup(gid, secret):
        if not certified:
            return dict(http_status=503, error_type="HTTPError", secret_redacted=False, data=None)
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    data=dict(id=gid, model=runner.route.MODEL_ALIAS,
                              provider_name=runner.route.PROVIDER, total_cost=.0001))

    runner.execute(*prepared[:2], secret="fixture-secret", send=send, lookup=lookup, sleep=lambda _: None)
    return sends


@pytest.mark.parametrize("options,calls", [(dict(bad_at=2), 2), (dict(native=False), 1),
                                         (dict(certified=False), 1)])
def test_serial_failure_preserves_all_assignments_and_old_unsettled(prepared, options, calls):
    root, ledger, _ = prepared
    before = {p.name: p.read_bytes() for p in (ledger / "entries").glob("old-*.json")}
    assert len(fake(prepared, **options)) == calls
    report = runner.audit(root, ledger)
    assert not report["gate_passed"] and report["calls"] == calls
    assert len(report["assignments"]) == 18
    assert all(row["status"] == "not_started" for row in report["assignments"][calls:])
    assert before == {p.name: p.read_bytes() for p in (ledger / "entries").glob("old-*.json")}
    with pytest.raises(ValueError, match="restart"):
        runner.execute(root, ledger, secret="fixture-secret")


def test_all_eighteen_fabricated_and_fresh_isolated_replay(prepared, tmp_path):
    root, ledger, protocol = prepared
    assert len(fake(prepared)) == 18
    report = runner.audit(root, ledger)
    assert report["gate_passed"] and not report["publication_evidence"]
    assert Decimal(report["accounted_usd"]) == Decimal(".0018")
    assert not (root / "episodes").exists()
    target, archive = tmp_path / "portable", tmp_path / "archive.zip"
    runner.export(root, ledger, target, archive)
    fresh = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(fresh)
    command = [sys.executable, "-I", "-S", str(fresh / "code/experiments/paper3_retrospective_labeled_gate.py"),
               str(fresh), "--replay", "--expected-protocol", protocol]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["portable_replay"]["exact_report_match"]


def test_stale_metadata_blocks_all_admission(prepared):
    root, ledger, _ = prepared
    with pytest.raises(ValueError, match="stale"):
        runner.execute(root, ledger, secret="fixture-secret", clock=lambda: time.time() + 3601)
    assert not (root / "sessions/start.json").exists()
    assert len(list((ledger / "entries").glob("*.json"))) == 2
