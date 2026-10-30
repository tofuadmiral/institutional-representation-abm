"""Offline recovery checks; fake transport never sends a hosted request."""

from copy import deepcopy
from pathlib import Path

import pytest

from paper3 import retrospective_graceful_recovery as recover
from paper3 import retrospective_billing_calls as service
from paper3 import retrospective_deepinfra_failure_v1 as classifier
from paper3 import retrospective_deepinfra_route_v1 as route
from paper3.pivot_b_budget import atomic
from tests.test_paper3_retrospective_deepinfra_core_v1 import evidence
from tests.test_paper3_retrospective_deepinfra_overload_v2 import (
    first_request,
    overload,
)
from tests.test_paper3_retrospective_independent_calls import Clock
from tests.test_paper3_retrospective_score_ledger import fixture


def overload_with_id(request=None):
    row = deepcopy(overload())
    if request is not None:
        bound = route.reservation(request)
        row.update(request=request, **bound)
        row["request_sha256"] = recover.hashlib.sha256(
            bound["request_text"].encode()
        ).hexdigest()
    row["stream"]["generation_header"] = "gen-fabricated-overload"
    row["receipts"] = [
        dict(
            http_status=404,
            error_type="HTTPError",
            data=None,
            secret_redacted=False,
            scheduled_offset_seconds=n,
        )
        for n in (0, 20, 40, 60)
    ]
    row["assessment"] = service.assess(row, classifier.previous.CONFIG)
    row["status"] = "recorded"
    row["ended_unix"] = 1000
    return row


def test_generation_header_and_four_missing_receipts_are_retryable_without_mutation():
    row = overload_with_id()
    before = deepcopy(row)
    assert recover.overload(row)["eligible"]
    assert row == before


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r["stream"].update(byte_count=1),
        lambda r: r["stream"].update(lines=["data: {}"], line_count=1),
        lambda r: r["stream"].update(http_status=402),
        lambda r: r["stream"].update(http_error_body_truncated=True),
        lambda r: r["stream"].update(secret_redacted=True),
        lambda r: r["receipts"][0].update(http_status=500),
        lambda r: r["receipts"][3].update(http_status=200),
        lambda r: r["assessment"].update(accounted_usd="0"),
        lambda r: r["assessment"]["stream"].update(usage={"completion_tokens": 1}),
        lambda r: r["request"]["provider"].update(allow_fallbacks=True),
    ],
)
def test_partial_answer_unknown_billing_auth_and_incomplete_reservation_never_retry(
    mutation,
):
    row = overload_with_id()
    mutation(row)
    assert not recover.overload(row)["eligible"]


def setup(tmp_path, *, bad_first=False, crashes=False, always_busy=False):
    clock, sent, costs = Clock(), [], []
    root = tmp_path / "run"
    request = first_request()

    def classify(row, req, key):
        return classifier.classify(row, req, fixture(2), "draft")

    def check(path, row):
        assert row["status"] == "recorded"
        assert row["id"] == path.stem

    def perform(req, key, physical):
        sent.append((route.reservation(req)["request_text"], clock()))
        if always_busy or len(sent) == 1 and not bad_first:
            row = overload_with_id(req)
            row["ended_unix"] = clock()
            row["stream"]["retry_after"] = "900"
            costs.append(row["reserved_usd"])
        else:
            row = evidence(req, physical, **({"raw": "not JSON"} if bad_first else {}))
            costs.append(".0001")
        row["id"] = physical
        path = root / "calls" / (physical + ".json")
        path.parent.mkdir(exist_ok=True)
        atomic(path, row)
        if crashes:
            raise KeyboardInterrupt()
        return path

    def build():
        return recover.DurableResponses(
            root,
            tmp_path,
            protocol="f" * 64,
            classify=classify,
            perform=perform,
            check_record=check,
            verify=lambda: None,
            clock=clock,
            sleep=clock.sleep,
        )

    return request, sent, costs, build, root, clock


def test_real_response_cache_retries_identical_wire_honors_delay_and_keeps_costs(
    tmp_path,
):
    request, sent, costs, build, root, clock = setup(tmp_path)
    b = build()
    try:
        result = b.respond(request, "logical")
        assert result["id"] == "logical" and len(sent) == 2
        assert sent[0][0] == sent[1][0] and sent[1][1] - sent[0][1] >= 900
        assert (
            len(costs) == 2 and costs[0] == route.reservation(request)["reserved_usd"]
        )
        assert len(list((root / "calls").glob("*.json"))) == 2
    finally:
        b.close()
    b = build()
    try:
        assert b.respond(request, "logical") == result
        assert len(sent) == 2  # Restart replays, never sends accepted work.
    finally:
        b.close()


def test_crash_after_overload_evidence_is_recovered_without_repeating_attempt(tmp_path):
    request, sent, _, build, root, _ = setup(tmp_path, crashes=True)
    b = build()
    with pytest.raises(KeyboardInterrupt):
        b.respond(request, "logical")
    b.close()
    b = build()
    with pytest.raises(KeyboardInterrupt):
        b.respond(request, "logical")
    b.close()
    assert len(sent) == 2 and len(list((root / "calls").glob("*.json"))) == 2
    b = build()
    try:
        b.respond(request, "logical")
        assert len(sent) == 2  # Adopts already completed second result.
    finally:
        b.close()


def test_no_duplicate_writer_and_replayed_wire_must_match(tmp_path):
    request, sent, _, build, _, _ = setup(tmp_path)
    b = build()
    try:
        with pytest.raises(BlockingIOError):
            build()
        b.respond(request, "logical")
        different = deepcopy(request)
        different["seed"] += 1
        with pytest.raises(recover.Paused):
            b.respond(different, "logical")
        assert len(sent) == 2
    finally:
        b.close()


def test_four_attempt_limit_pauses_without_discarding_completed_work(tmp_path):
    request, sent, _, build, _, _ = setup(tmp_path, always_busy=True)
    b = build()
    with pytest.raises(recover.Paused, match="per_action_retry_limit"):
        b.respond(request, "logical")
    b.close()
    b = build()
    with pytest.raises(recover.Paused, match="per_action_retry_limit"):
        b.respond(request, "logical")
    b.close()
    assert len(sent) == 4


def test_completed_bad_content_is_cached_never_regenerated(tmp_path):
    request, sent, _, build, _, _ = setup(tmp_path, bad_first=True)
    b = build()
    try:
        row = b.respond(request, "logical")
        assert (
            classifier.classify(row, request, fixture(2), "draft")["status"]
            == "content_failed"
        )
    finally:
        b.close()
    b = build()
    try:
        b.respond(request, "logical")
        assert len(sent) == 1
    finally:
        b.close()


def test_uncertain_inflight_request_is_not_blindly_resent(tmp_path):
    request, sent, _, build, root, _ = setup(tmp_path)
    b = build()
    bound = route.reservation(request)
    atomic(
        root / "attempts/logical-a1.json",
        dict(
            protocol="f" * 64,
            logical_id="logical",
            physical_id="logical-a1",
            attempt=1,
            request_sha256=recover.hashlib.sha256(
                bound["request_text"].encode()
            ).hexdigest(),
        ),
    )
    try:
        with pytest.raises(
            recover.Paused, match="admitted_request_without_durable_result"
        ):
            b.respond(request, "logical")
        assert sent == []
    finally:
        b.close()


def test_actual_archived_failure_is_recognized_read_only():
    p = Path(__file__).resolve().parents[1] / (
        "results/paper3/pivot_b_retrospective_deepinfra_pilot_v2/block-0/calls/"
        "overload-r2-0-conflict-binding_majority-21-a1.json"
    )
    before = recover.digest(p)
    assert recover.overload(recover.load(p))["eligible"]
    assert recover.digest(p) == before


@pytest.mark.parametrize("code", (500, 502, 503, 504))
def test_transient_gateway_failures_are_retryable_without_an_error_message_whitelist(
    code,
):
    row = overload_with_id()
    row["stream"].update(
        http_status=code, http_error_body="<html>temporarily unavailable</html>"
    )
    assert recover.overload(row)["eligible"]


@pytest.mark.parametrize(
    "error", ("TimeoutError", "URLError", "ConnectionResetError", "RemoteDisconnected")
)
def test_connection_failures_before_any_answer_retry_with_full_cost_retained(error):
    row = overload_with_id()
    row["stream"].update(
        http_status=None, error_type=error, http_error_body=None, generation_header=None
    )
    row["receipts"] = []
    assert recover.overload(row)["eligible"]
