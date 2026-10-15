from decimal import Decimal
import json
import subprocess
import sys
import time
import zipfile

import pytest

from experiments import paper3_retrospective_deepseek_gate as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic
from tests.test_paper3_retrospective_requests import endpoint as qwen_endpoint


def endpoint():
    value = qwen_endpoint()
    value["data"]["id"] = runner.route.MODEL
    row = value["data"]["endpoints"][0]
    row.update(tag=runner.route.TAG, model_id=runner.route.MODEL,
               name="DeepInfra | " + runner.route.MODEL_ALIAS, quantization="fp4",
               context_length=runner.route.CONTEXT, max_completion_tokens=16384,
               pricing=dict(prompt=".00000026", completion=".00000038"))
    return value


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
    lookup_case = {runner.route.SEED_BASE + index: case
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
    command = [sys.executable, "-I", "-S", str(fresh / "code/experiments/paper3_retrospective_deepseek_gate.py"),
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


def test_fixed_messages_schemas_sampling_and_cost_bound():
    from copy import deepcopy
    from paper3 import retrospective_labeled_qualification as original
    from paper3.retrospective_requests import request as qwen_request
    cases = runner.cases()
    assert len(cases) == 18
    for index, row in enumerate(cases):
        request = row["request"]
        expected = qwen_request(original.structured(original.cases()[index]), runner.route.SEED_BASE + index)
        expected["model"] = runner.route.MODEL
        expected["provider"] = deepcopy(request["provider"])
        assert expected == request
    assert sum(Decimal(row["reserved_usd"]) for row in cases) <= runner.CAP
    assert runner.specification()["case_reuse"]["all_eighteen_reused"]
    assert "not fresh held-out" in runner.specification()["limitations"]


def test_reasoning_markup_is_not_a_client_tool():
    row = runner.cases()[0]
    stream = dict(http_status=200, error_type=None, secret_redacted=False,
        lines=['data: ' + json.dumps(dict(id="dsml-only", model=runner.route.MODEL_ALIAS,
            provider=runner.route.PROVIDER, choices=[dict(index=0,
            delta=dict(reasoning='<DSML submit_decision>' + json.dumps(
                runner.qualification.cases()[0]["expected"]) + '</DSML>'), finish_reason="stop")])), "",
            "data: " + json.dumps(dict(choices=[], usage=dict(prompt_tokens=100,
                completion_tokens=100, cost=.0001))), "", "data: [DONE]", ""])
    observed = dict(**row, stream=stream, receipts=[dict(http_status=200, data=dict(
        id="dsml-only", model=runner.route.MODEL_ALIAS, provider_name=runner.route.PROVIDER,
        total_cost=.0001))])
    assessed = runner.service.assess(observed, runner.CONFIG)
    assert assessed["passed"]
    result = runner.score(dict(**observed, assessment=assessed), row)
    assert not result["usable"] and not result["valid_action"] and not result["exact"]


def test_pinned_endpoint_rejects_wrong_quantization_or_tools():
    from copy import deepcopy
    for change in (dict(quantization="fp8"), dict(status=-2),
                   dict(supports_tool_choice=dict(auto=False, function=True)),
                   dict(pricing=dict(prompt=".000001", completion=".000001"))):
        bad = deepcopy(endpoint())
        bad["data"]["endpoints"][0].update(change)
        with pytest.raises(ValueError):
            runner.route.check_endpoint(bad)
