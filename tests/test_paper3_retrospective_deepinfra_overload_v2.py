"""Prospective overload regressions; fabricated transport, no hosted calls."""
from copy import deepcopy
from datetime import datetime, timezone
from email.message import Message
from email.utils import format_datetime
from functools import cache
import io
import json
from pathlib import Path
import shutil
import urllib.error

import pytest

from paper3 import hosted_reasoning_transport_v2 as transmitter
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_deepinfra_budget_v1 as budget
from paper3 import retrospective_deepinfra_calls_v2 as transport
from paper3 import retrospective_deepinfra_failure_v1 as failure
from paper3 import retrospective_deepinfra_freeze_v1 as old_freeze
from paper3 import retrospective_deepinfra_recovery_evidence_v1 as old_evidence
from paper3 import retrospective_deepinfra_recovery_evidence_v2 as evidence
from paper3 import retrospective_deepinfra_recovery_policy_v2 as policy
from paper3 import retrospective_deepinfra_requests_v1 as requests
from paper3 import retrospective_deepinfra_route_v1 as route
from tests.test_paper3_retrospective_deepinfra_core_v1 import evidence as answered
from tests.test_paper3_retrospective_independent_calls import Clock, answerless
from tests.test_paper3_retrospective_independent_execution import action
from tests.test_paper3_retrospective_score_ledger import fixture

REPO = Path(__file__).resolve().parents[1]


@cache
def first_request():
    seen = []
    def respond(actor, identity, term, stage, context, index):
        request = requests.action_request(fixture(2), "binding_sum", 1,
            actor, identity, term, stage, context, index)
        seen.append(request)
        return action(request)
    institution.episode(fixture(2), "binding_sum", respond)
    return seen[0]


def overload(**metadata):
    row = answered(first_request(), "fabricated-overload")
    row["stream"] = answerless(Clock())
    body = json.loads(row["stream"]["http_error_body"])
    body["error"]["metadata"].update(provider_name=route.PROVIDER,
        provider_error_code="engine_overloaded", **metadata)
    row["stream"]["http_error_body"] = json.dumps(body)
    row["receipts"] = []
    return row


def plan(row, attempt=1, used=0, start=1000, now=1000):
    return policy.eligibility(row, physical_attempt=attempt, block_reissues_used=used,
        block_started_unix=start, detected_unix=now)


def test_observed_overload_variant_is_retryable_only_under_new_policy():
    row = overload()
    original = deepcopy(row)
    assert not old_evidence.eligibility(row, logical_attempt=1, recoveries_used=0)["eligible"]
    assert evidence.eligibility(row)["eligible"]
    assert plan(row)["eligible"] and plan(row)["delay_seconds"] == 300
    assert row == original


@pytest.mark.parametrize("extra", [
    {"error_type": "provider_overloaded"},
    {"error_type": None},
    {"error_type": "rate_limit_exceeded", "provider_code": "rate_limited"},
    {"provider_code": "diagnostic-revision-123", "request_trace": "not-a-generation"},
    {"raw": "Different harmless provider prose", "remedy_hint": "untrusted text"},
])
def test_semantic_rate_limit_does_not_depend_on_diagnostic_message_whitelist(extra):
    assert plan(overload(**extra))["eligible"]


@pytest.mark.parametrize("mutation", [
    lambda r: r["stream"].update(http_status=402),
    lambda r: r["stream"].update(http_status=403),
    lambda r: r["stream"].update(http_status=503),
    lambda r: r["stream"].update(lines=["data: {}"], line_count=1, byte_count=8),
    lambda r: r["stream"].update(generation_header="gen-answer"),
    lambda r: r["stream"].update(first_line_unix=1000),
    lambda r: r["stream"].update(secret_redacted=True),
    lambda r: r["stream"].update(error_body_redacted=True),
    lambda r: r["stream"].update(http_error_body_truncated=True),
    lambda r: r.update(receipts=[{"http_status": 200}]),
    lambda r: r["request"]["provider"].update(allow_fallbacks=True),
    lambda r: r["request"]["reasoning"].update(enabled=False),
    lambda r: r.update(reserved_usd="NaN"),
    lambda r: r["stream"].update(http_error_body='{"error":{},"error":{}}'),
])
def test_answers_billing_authentication_and_provenance_still_not_retryable(mutation):
    row = deepcopy(overload())
    mutation(row)
    assert not plan(row)["eligible"]


@pytest.mark.parametrize("extra", [
    {"provider_name": "AtlasCloud"}, {"is_byok": True},
    {"limit_source": "openrouter_key_limit"},
    {"error_type": "payment_required"}, {"error_type": "content_policy_violation"},
    {"generation_id": "some-generation"}, {"request_id": "gen-answer"},
])
def test_conflicting_error_metadata_cannot_be_smuggled_as_overload(extra):
    row = overload()
    body = json.loads(row["stream"]["http_error_body"])
    body["error"]["metadata"].update(extra)
    row["stream"]["http_error_body"] = json.dumps(body)
    assert not plan(row)["eligible"]


@pytest.mark.parametrize("attempt,delay", [(1,300), (2,600), (3,1200), (4,None)])
def test_original_retry_ceiling_and_cooldowns_are_unchanged(attempt, delay):
    result = plan(overload(), attempt=attempt)
    assert result["eligible"] is (delay is not None)
    assert result["delay_seconds"] == delay
    assert not plan(overload(), used=40)["eligible"]


def test_retry_after_is_honored_without_removing_finite_deadline():
    row = overload()
    row["stream"].update(retry_after="900", ended_unix=1000)
    assert plan(row)["not_before_unix"] == 1900
    row["stream"]["retry_after"] = format_datetime(datetime.fromtimestamp(2000, timezone.utc), usegmt=True)
    assert plan(row)["not_before_unix"] == 2000
    row["stream"]["retry_after"] = "86400"
    assert not plan(row)["eligible"]
    row["stream"]["retry_after"] = "invalid-header"
    assert plan(row)["delay_seconds"] == 300


@pytest.mark.parametrize("typed,eligible", [("provider_overloaded", True), (None, False)])
def test_503_requires_positive_preanswer_provider_overload_semantics(typed, eligible):
    row = overload(error_type=typed)
    row["stream"]["http_status"] = 503
    body = json.loads(row["stream"]["http_error_body"])
    body["error"]["code"] = 503
    row["stream"]["http_error_body"] = json.dumps(body)
    assert plan(row)["eligible"] is eligible


def test_transmitter_captures_retry_and_generation_headers_without_retrying(monkeypatch):
    headers = Message()
    headers["Retry-After"] = "900"
    headers["X-Generation-Id"] = "gen-must-not-retry"
    body = overload()["stream"]["http_error_body"].encode()
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.data)
            raise urllib.error.HTTPError("https://example.invalid", 429, "busy", headers, io.BytesIO(body))
    monkeypatch.setattr(transmitter.t, "opener", lambda: Opener())
    result = transmitter.transmit("{}", "fabricated-secret-not-a-real-key")
    assert calls == [b"{}"]
    assert result["retry_after"] == "900"
    assert result["generation_header"] == "gen-must-not-retry"
    row = overload()
    row["stream"] = result
    assert not plan(row)["eligible"]


def test_real_transport_bridge_reissues_identical_wire_then_audits_all_costs(tmp_path):
    # Private COPY only: real authority is never modified or spent by this test.
    ledger_root = tmp_path / "ledger"
    shutil.copytree(REPO / "results/paper3/pivot_b_budget", ledger_root)
    ledger = budget.RecoveryLedger(ledger_root, retirement_pins=old_freeze.RETIREMENT_PINS)
    ledger.allocate("fabricated-overload-v2", "1.00")
    before = ledger.snapshot()
    clock, sent = Clock(), []
    request = deepcopy(first_request())
    def send(wire, secret):
        assert secret is None
        sent.append((wire, clock()))
        if len(sent) == 1:
            trace = overload()["stream"]
            trace["retry_after"] = "900"
        else:
            trace = answered(json.loads(wire), "fabricated-success")["stream"]
        trace.update(started_unix=clock(), ended_unix=clock())
        return trace
    def lookup(identifier, secret):
        assert secret is None
        return dict(http_status=200, error_type=None, secret_redacted=False,
            data=dict(id=identifier, model=route.MODEL_ALIAS,
                      provider_name=route.PROVIDER, total_cost=.0001))
    def classify(row, case):
        return failure.classify(row, case["request"], fixture(2), "draft")
    bound = route.reservation(request)
    case = dict(id="fabricated-action", request=request, **bound,
        request_sha256=transport.t.sha(bound["request_text"].encode()), context=dict(stage="draft"))
    bridge = transport.Calls(tmp_path / "run", ledger, "fabricated-overload-v2",
        lambda: ({}, "f" * 64), classify, send=send, lookup=lookup,
        maximum_logical=1, clock=clock, sleep=clock.sleep)
    try:
        result = bridge.one(case)
        assert result["result"]["status"] == "recorded_valid"
        assert len(sent) == 2 and sent[0][0] == sent[1][0]
        assert sent[1][1] - sent[0][1] >= 900
        report = transport.audit(bridge.root, ledger_root, bridge.stage,
            bridge.protocol, classify, maximum_logical=1)
        assert report["reissues"] == report["recovery_events"] == 1
        assert len(report["physical_reports"]) == 2
        after = ledger.snapshot()
        assert after["entries"] == before["entries"] + 2
        assert after["uncertified"] == before["uncertified"] + 1
        assert budget.amount(report["accounted_usd"]) == budget.amount(bound["reserved_usd"]) + budget.amount(".0001")
    finally:
        bridge.close()
