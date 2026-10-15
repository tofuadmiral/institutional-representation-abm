"""Fabricated transport only: not provider performance or agent findings."""
from copy import deepcopy
from decimal import Decimal
import json
import subprocess
import sys
import time
import zipfile

import pytest

from experiments import paper3_retrospective_atlas_nullable_gate as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic
from tests import test_paper3_retrospective_deepseek_gate as fixtures


def endpoint():
    value = deepcopy(fixtures.endpoint())
    row = value["data"]["endpoints"][0]
    row.update(tag=runner.route.TAG, provider_name=runner.route.PROVIDER,
               name=runner.route.PROVIDER + " | " + runner.route.MODEL_ALIAS,
               quantization="fp8", max_completion_tokens=147456)
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
    monkeypatch.setattr(fixtures, "runner", runner)
    root = tmp_path / "run"
    protocol = runner.prepare(root, metadata=endpoint(), ledger_root=ledger)
    return root, ledger, protocol


def replay(prepared, tmp_path):
    root, ledger, protocol = prepared
    target, archive = tmp_path / "portable", tmp_path / "archive.zip"
    runner.export(root, ledger, target, archive)
    fresh = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(fresh)
    process = subprocess.run([sys.executable, "-I", "-S",
        str(fresh / "code/experiments/paper3_retrospective_atlas_nullable_gate.py"), str(fresh),
        "--replay", "--expected-protocol", protocol], capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["portable_replay"]["exact_report_match"]
    return report


def test_complete_all_tasks_and_isolated_replay(prepared, tmp_path):
    assert len(fixtures.fake(prepared)) == 18
    report = runner.audit(*prepared[:2])
    assert report["gate_passed"] and report["calls"] == 18
    assert len(report["assignments"]) == 18 and not report["publication_evidence"]
    assert Decimal(report["accounted_usd"]) == Decimal(".0018")
    assert replay(prepared, tmp_path)["gate_passed"]
    with pytest.raises(ValueError, match="restart"):
        runner.execute(*prepared[:2], secret="fixture-secret")


@pytest.mark.parametrize("options,expected", [(dict(bad_at=2), 2), (dict(native=False), 1),
                                             (dict(certified=False), 1)])
def test_stop_without_retries_and_preserve_reservations(prepared, options, expected):
    root, ledger, _ = prepared
    old = {p.name: p.read_bytes() for p in (ledger / "entries").glob("old-*.json")}
    assert len(fixtures.fake(prepared, **options)) == expected
    report = runner.audit(root, ledger)
    assert not report["gate_passed"] and report["calls"] == expected
    assert all(a["status"] == "not_started" for a in report["assignments"][expected:])
    assert old == {p.name: p.read_bytes() for p in (ledger / "entries").glob("old-*.json")}


def test_failed_gate_isolated_replay(prepared, tmp_path):
    fixtures.fake(prepared, bad_at=2)
    assert not replay(prepared, tmp_path)["gate_passed"]


@pytest.mark.parametrize("status", [200, 429])
def test_partial_stream_and_http429_never_reissued(prepared, tmp_path, status):
    sent = []
    def send(wire, secret):
        sent.append(wire)
        head = dict(id="fabricated-partial", model=runner.route.MODEL_ALIAS,
            provider=runner.route.PROVIDER, choices=[dict(index=0,
                delta=dict(reasoning="fabricated"), finish_reason=None)])
        return dict(http_status=status, error_type="HTTPError" if status == 429 else None,
            secret_redacted=False, lines=[] if status == 429 else ["data: " + json.dumps(head), ""],
            started_unix=time.time(), ended_unix=time.time())
    def lookup(gid, secret):
        return dict(http_status=404, error_type="HTTPError", secret_redacted=False, data=None)
    runner.execute(*prepared[:2], secret="fixture-secret", send=send, lookup=lookup, sleep=lambda _: None)
    assert len(sent) == 1
    report = runner.audit(*prepared[:2])
    assert not report["gate_passed"] and report["calls"] == 1
    assert all(a["status"] == "not_started" for a in report["assignments"][1:])
    assert Decimal(report["accounted_usd"]) == Decimal(runner.cases()[0]["reserved_usd"])
    assert not replay(prepared, tmp_path)["gate_passed"]


def test_route_cap_and_no_fallback():
    spec = runner.specification()
    assert Decimal(spec["full_reservation_usd"]) <= runner.CAP == Decimal(".25")
    assert spec["max_calls"] == 18 and spec["workers"] == 1
    assert len(runner.qualification.cases()) == 18
    assert sum(c["kind"] == "fact" for c in runner.qualification.cases()) == 12
    assert all(c["id"].endswith("-terminal") for c in runner.qualification.cases()[:4])
    assert sum("anyOf" in c["request"]["tools"][0]["function"]["parameters"]
               ["properties"].get("successor_score", {}) for c in runner.cases()) == 4
    assert runner.qualification.FRAME_SEED == 3510001 and runner.route.SEED_BASE == 3520000
    for case in runner.cases():
        request = case["request"]
        assert request["provider"]["only"] == ["atlas-cloud/fp8"]
        assert request["provider"]["quantizations"] == ["fp8"]
        assert request["provider"]["require_parameters"]
        assert request["provider"]["allow_fallbacks"] is False
        assert request["reasoning"] == dict(enabled=True, exclude=False)
        assert request["tool_choice"] == "auto" and request["max_tokens"] == 14000


@pytest.mark.parametrize("field,bad", [("status", -2), ("quantization", "fp4"),
                                      ("provider_name", "DeepInfra"), ("supported_parameters", [])])
def test_metadata_rejects_incompatible_route(field, bad):
    metadata = endpoint()
    metadata["data"]["endpoints"][0][field] = bad
    with pytest.raises(ValueError):
        runner.route.check_endpoint(metadata)
