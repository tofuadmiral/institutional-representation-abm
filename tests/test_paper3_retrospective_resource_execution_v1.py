"""Fabricated whole-episode execution only; no transport or empirical evidence."""
from copy import deepcopy

import pytest

from paper3 import retrospective_billing_calls as service
from paper3 import retrospective_independent_execution as previous
from paper3 import retrospective_resource_execution_v1 as engine
from tests.test_paper3_retrospective_independent_execution import assignments, row
from tests.test_paper3_retrospective_resource_failure_v1 import length_row


@pytest.mark.parametrize("bad_index", range(30))
def test_resource_failure_at_every_slot_keeps_prefix_bounds_and_next_assignment(bad_index):
    events, sent = [], []
    _, template = length_row(partial=True)
    def respond(request, identifier):
        sent.append(identifier)
        saved = row(request, identifier, absent=True)
        if len(sent) == bad_index + 1:
            saved["stream"] = deepcopy(template["stream"])
            saved["assessment"] = service.assess(saved, previous.CONFIG)
        return saved
    report = engine.execute(assignments(), respond=respond, verify=lambda: None,
                            persist=lambda e: events.append(deepcopy(e)))
    first, second = report["assignments"]
    assert report["resource_failed"] == 1 and report["completed"] == 1
    assert report["content_failed"] == 0 and not report["global_safety_stop"]
    assert first["status"] == "resource_failed" and second["status"] == "completed"
    assert first["first_term"]["complete"] is (bad_index >= 15)
    assert not first["two_term"]["complete"] and first["outcome"] is None
    slot = first["logicals"][bad_index]
    assert slot["classification"]["action"] is None
    assert slot["classification"]["instrument_safe"] is False
    assert all(s["status"] == "not_started" for s in first["logicals"][bad_index + 1:])
    assert len(sent) == bad_index + 1 + 30 and len(set(sent)) == len(sent)
    assert len(first["two_term"]["citizen_utility_bounds"]) == 7
    assert all(len(d) == 9 for d in first["two_term"]["citizen_utility_bounds"])
    assert events[-1]["report"]["resource_failed"] == 1
    assert not report["allocation_authorized"] and not report["publication_evidence"]


def test_unknown_response_error_still_prevents_every_later_assignment():
    sent = []
    def respond(request, identifier):
        sent.append(identifier)
        raise OSError("fabricated unknown failure")
    report = engine.execute(assignments(), respond=respond, verify=lambda: None,
                            persist=lambda e: None)
    assert len(sent) == 1 and report["global_safety_stop"]
    assert report["assignments"][1]["status"] == "not_started"
    assert report["resource_failed"] == 0 and report["completed"] == 0
