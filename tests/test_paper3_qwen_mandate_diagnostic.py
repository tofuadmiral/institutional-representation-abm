"""Fabricated transport only; these are not agent observations."""
from copy import deepcopy
from decimal import Decimal
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from experiments import paper3_qwen_mandate_diagnostic as r
from paper3.pivot_b_budget import BUDGET_ID, atomic

support_spec = importlib.util.spec_from_file_location(
    "mandate_test_support", Path(__file__).with_name("test_paper3_qwen_channel_gate.py"))
support = importlib.util.module_from_spec(support_spec)
support_spec.loader.exec_module(support)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    class Public:
        def open(self, url, timeout):
            assert url == r.METADATA_URL
            return io.BytesIO(json.dumps(support.metadata()).encode())
    monkeypatch.setattr(r.t, "opener", lambda: Public())
    monkeypatch.setattr(r, "seed_audit", lambda: dict(
        planned=sorted({c["context"]["seed"] for c in r.cases()}), overlap=[]))
    root = tmp_path / "run"
    r.prepare(root)
    budget = tmp_path / "budget"
    budget.mkdir()
    atomic(budget / "authority.json", dict(budget_id=BUDGET_ID, cap_usd="10.00",
                                         credit_purchases_authorized=False))
    return root, budget


def fake(prepared, mode="valid"):
    contexts = {c["request_text"]: c["context"] for c in r.cases()}
    requests, lookups = [], []
    lock = threading.Lock()
    def send(wire, secret):
        with lock:
            requests.append(wire)
            gid = "fabricated-" + str(len(requests))
        if mode == "exception":
            raise RuntimeError("fabricated failure")
        context = contexts[wire]
        value = deepcopy(context["expected"])
        if mode == "wrong_facts":
            value["own_utilities"]["A0"] += 1
        answer = "bad JSON" if mode == "invalid" else json.dumps(value)
        trace_mode = "transport" if mode == "one_failure" and context["id"] == r.cases()[0]["id"] else mode
        return support.trace(answer, gid, trace_mode)
    def lookup(gid, secret):
        lookups.append(gid)
        missing = mode == "missing_receipt"
        return dict(http_status=404 if missing else 200,
                    error_type="HTTPError" if missing else None, secret_redacted=False,
                    started_unix=time.time(), ended_unix=time.time(),
                    data=None if missing else dict(id=gid, model=r.MODELS[1],
                        provider_name=r.PROVIDER, total_cost=.0002 if mode == "cost_mismatch" else .0001))
    terminal = r.execute(*prepared, secret="fixture-secret", send=send, lookup=lookup,
                         sleep=lambda _: None)
    return terminal, requests, lookups


@pytest.mark.parametrize("mode", ["valid", "bad_reasoning_count"])
def test_complete_factual_run_and_no_restart(prepared, mode):
    terminal, requests, lookups = fake(prepared, mode)
    report = r.audit(*prepared)
    assert len(requests) == len(lookups) == report["calls"] == 56
    assert report["both_presentations_passed"]
    assert len(report["assignments"]) == 56 and len(report["paired_comparisons"]) == 28
    assert all(x["correct"] == 28 and x["factual_correctness_bounds"] == ["1", "1"]
               for x in report["by_encoding"].values())
    assert Decimal(report["accounted_usd"]) == Decimal(".0056")
    with pytest.raises(ValueError, match="already started"):
        r.execute(*prepared)


@pytest.mark.parametrize("mode", ["wrong_facts", "invalid"])
def test_wrong_or_invalid_answers_retained_without_repair(prepared, mode):
    terminal, requests, _ = fake(prepared, mode)
    report = r.audit(*prepared)
    assert len(requests) == 56 and not terminal["global_safety_stop"]
    assert not report["both_presentations_passed"]
    for value in report["by_encoding"].values():
        assert value["correct"] == 0 and value["strict_all_assigned_accuracy"] == "0"
        assert value["factual_correctness_bounds"] == (["0", "0"] if mode == "wrong_facts" else ["0", "1"])


@pytest.mark.parametrize("mode", ["transport", "missing_receipt", "exception", "identity",
                                 "tokens_only", "length", "cost_mismatch"])
def test_failures_stop_and_preserve_every_assignment(prepared, mode):
    terminal, requests, _ = fake(prepared, mode)
    report = r.audit(*prepared)
    assert terminal["global_safety_stop"] and 0 < len(requests) < 56
    assert len(report["assignments"]) == 56 and len(report["paired_comparisons"]) == 28
    assert not report["both_presentations_passed"]
    if mode in ("missing_receipt", "exception", "cost_mismatch"):
        budget = r.Ledger(prepared[1]).snapshot()
        assert budget["pending"] + budget["uncertified"] > 0


def test_budget_is_shared_not_reset(prepared):
    ledger = r.Ledger(prepared[1]); ledger.allocate("earlier", "10")
    ledger.reserve("earlier", "old", "9.999", "0" * 64)
    terminal, requests, _ = fake(prepared)
    assert not requests and terminal["global_safety_stop"]
    assert r.audit(*prepared)["accounted_usd"] == "0"


def test_single_transport_failure_does_not_replace_or_stop_independent_cases(prepared):
    terminal, requests, _ = fake(prepared, "one_failure")
    report = r.audit(*prepared)
    assert len(requests) == 56 and terminal["transport_failures"] == 1
    assert not terminal["global_safety_stop"] and not report["both_presentations_passed"]
    assert sum(v["unscored"] for v in report["by_encoding"].values()) == 1


def test_stale_metadata_refuses_before_admission(prepared):
    observed = r.t.load(prepared[0] / "manifest.json")["protocol"]["metadata_observed_unix"]
    with pytest.raises(ValueError, match="stale metadata"):
        r.execute(*prepared, clock=lambda: observed + 3601)
    assert not list((prepared[0] / "sessions").iterdir())


def test_request_bounds_and_no_oracle_leak():
    cases = r.cases()
    assert len(cases) == 56 and len({c["id"] for c in cases}) == 56
    assert sum(Decimal(c["reserved_usd"]) for c in cases) == Decimal(".28541440")
    assert r.CAP == Decimal(".30")
    for case in cases:
        request = case["request"]
        assert "expected" not in request and request["messages"] == case["context"]["messages"]
        assert request["reasoning"] == dict(enabled=True, exclude=False)
        assert request["provider"]["allow_fallbacks"] is False
        assert case["input_token_bound"] + r.CONFIG["output_bound"] <= r.CONTEXT


@pytest.mark.parametrize("field", ["request", "oracle", "cost"])
def test_evidence_tamper_rejected(prepared, field):
    fake(prepared)
    root, budget = prepared
    path = next((root / "calls").glob("*.json")); row = r.t.load(path)
    if field == "request":
        row["request"]["reasoning"]["enabled"] = False
    elif field == "oracle":
        row["context"]["expected"]["package_utility"] = 1234
    else:
        path = budget / "entries" / (r.STAGE + "-" + row["id"] + ".json")
        row = r.t.load(path); row["accounted_usd"] = "0"
    atomic(path, row)
    with pytest.raises(ValueError):
        r.audit(*prepared)


def test_seed_audit_includes_unexecuted_plans(tmp_path):
    path = tmp_path / "results/paper3/old"; path.mkdir(parents=True)
    atomic(path / "manifest.json", dict(seed_audit=dict(planned=[324113])))
    with pytest.raises(ValueError, match="overlap"):
        r.seed_audit(tmp_path)


@pytest.mark.parametrize("mode", ["valid", "invalid", "exception", "missing_receipt"])
def test_actual_isolated_archive_replay(prepared, tmp_path, mode):
    fake(prepared, mode)
    archive = tmp_path / "archive.zip"
    exported = r.export(*prepared, tmp_path / "bundle", archive)
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(archive) as stream:
        stream.extractall(extracted)
    assert "All56 factual assignments" in (extracted / "README.md").read_text()
    result = subprocess.run([sys.executable, "-I", "-S",
        str(extracted / "code/experiments/paper3_qwen_mandate_diagnostic.py"), str(extracted),
        "--replay", "--expected-protocol", exported["protocol"]], env={}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    replay = json.loads(result.stdout)
    assert replay.pop("portable_replay")["exact_report_match"]
    assert replay == r.audit(*prepared)
