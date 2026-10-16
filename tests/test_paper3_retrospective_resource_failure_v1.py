"""Fabricated evidence only; no HTTP, provider claims or historical rescoring."""
from copy import deepcopy
import json

import pytest

from paper3 import retrospective_billing_calls as service
from paper3 import retrospective_independent_execution as old
from paper3 import retrospective_resource_failure_v1 as new
from tests.test_paper3_retrospective_independent_execution import row, request_for_test
from tests.test_paper3_retrospective_score_ledger import fixture


def length_row(*, count=14002, partial=False):
    request = request_for_test()
    evidence = row(request, "fabricated-length", absent=True)
    frames = [json.loads(line[6:]) for line in evidence["stream"]["lines"]
              if line.startswith("data: ") and line != "data: [DONE]"]
    frames[1]["choices"][0]["finish_reason"] = "length"
    frames[1]["choices"][0]["delta"] = dict(content='{"policy":' if partial else "")
    frames[2]["usage"]["completion_tokens"] = 14000
    frames[2]["usage"]["completion_tokens_details"]["reasoning_tokens"] = count
    evidence["stream"]["lines"] = [line for frame in frames
        for line in ("data: " + json.dumps(frame), "")] + ["data: [DONE]", ""]
    evidence["assessment"] = service.assess(evidence, old.CONFIG)
    return request, evidence


@pytest.mark.parametrize("count", (None, 0, 13900, 14000, 14002))
@pytest.mark.parametrize("partial", (False, True))
def test_length_never_accepts_or_repairs_action_and_preserves_anomalies(count, partial):
    request, evidence = length_row(count=count, partial=partial)
    before = deepcopy(evidence)
    assert old.classify(evidence, request, fixture(2), "draft")["status"] == "unsafe_failed"
    result = new.classify(evidence, request, fixture(2), "draft")
    assert evidence == before
    assert result["status"] == "resource_failed" and result["independent_episode_safe"]
    assert result["instrument_safe"] is False
    assert result["action"] is None and result["execution"] is None
    assert not result["accepted_action"]
    assert result["assessment"]["accounted_usd"] == evidence["reserved_usd"]
    assert not result["assessment"]["receipt_certified"]
    assert result["native_evidence"]["reported_tokens"] == count


@pytest.mark.parametrize("mutation", ("request_hash", "bound", "saved_assessment", "native",
    "provider", "done", "receipt503", "wrong_id", "negative_count", "bool_count",
    "under_limit", "dual_channel", "duplicate_json", "post_finish", "extra_choice"))
def test_noneligible_failures_stay_globally_unsafe(mutation):
    request, evidence = length_row()
    if mutation == "request_hash":
        evidence["request_sha256"] = "0" * 64
    elif mutation == "bound":
        evidence["input_token_bound"] += 1
    elif mutation == "saved_assessment":
        evidence["assessment"]["passed"] = False
    elif mutation == "receipt503":
        evidence["receipts"][0]["http_status"] = 503
    else:
        frames = [json.loads(line[6:]) for line in evidence["stream"]["lines"]
                  if line.startswith("data: ") and line != "data: [DONE]"]
        if mutation == "native":
            frames[0]["choices"][0]["delta"]["reasoning"] = ""
        elif mutation == "provider":
            frames[0]["provider"] = "wrong"
        elif mutation == "wrong_id":
            frames[1]["id"] = "second-generation"
        elif mutation in ("negative_count", "bool_count"):
            frames[2]["usage"]["completion_tokens_details"]["reasoning_tokens"] = (
                -1 if mutation == "negative_count" else True)
        elif mutation == "under_limit":
            frames[2]["usage"]["completion_tokens"] = 13999
        elif mutation == "dual_channel":
            frames[1]["choices"][0]["delta"] = dict(content="partial", tool_calls=[
                dict(index=0, function=dict(name="submit_decision", arguments="{"))])
        elif mutation == "post_finish":
            frames.append(dict(choices=[dict(index=0, delta=dict(content="later"))]))
        elif mutation == "extra_choice":
            frames[1]["choices"].append(deepcopy(frames[1]["choices"][0]))
        evidence["stream"]["lines"] = [line for frame in frames
            for line in ("data: " + json.dumps(frame), "")] + ["data: [DONE]", ""]
        if mutation == "done":
            evidence["stream"]["lines"] = evidence["stream"]["lines"][:-2]
        elif mutation == "duplicate_json":
            evidence["stream"]["lines"][0] = evidence["stream"]["lines"][0].replace(
                '"provider": "AtlasCloud"', '"provider":"wrong","provider":"AtlasCloud"')
    if mutation not in ("request_hash", "bound", "saved_assessment"):
        evidence["assessment"] = service.assess(evidence, old.CONFIG)
    result = new.classify(evidence, request, fixture(2), "draft")
    assert result["status"] == "unsafe_failed"
    assert result["action"] is None and not result.get("independent_episode_safe", False)


@pytest.mark.parametrize("options", ({}, {"absent": True}, {"bad_count": True},
    {"channel": "both"}, {"native": False}, {"raw": "bad content"}))
def test_all_nonlength_outcomes_are_identical_to_unchanged_validator(options):
    request = request_for_test()
    evidence = row(request, "fabricated-ordinary", **options)
    assert new.classify(evidence, request, fixture(2), "draft") == old.classify(
        evidence, request, fixture(2), "draft")
