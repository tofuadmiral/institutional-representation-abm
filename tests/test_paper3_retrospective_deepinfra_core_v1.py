"""Fabricated migration checks only; no inference, qualification or real spending."""
from copy import deepcopy
from dataclasses import asdict
import json

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_billing_calls as service
from paper3 import retrospective_contract_route_v2 as old_route
from paper3 import retrospective_deepinfra_route_v1 as route
from paper3 import retrospective_deepinfra_requests_v1 as requests
from paper3 import retrospective_deepinfra_classifier_v1 as classifier
from paper3 import retrospective_deepinfra_execution_v1 as execution
from paper3 import retrospective_deepinfra_recovery_policy_v1 as policy
from paper3 import retrospective_score_ledger_budget as old_requests
from tests.test_paper3_retrospective_independent_execution import action, row
from tests.test_paper3_retrospective_independent_calls import answerless, Clock
from tests.test_paper3_retrospective_score_ledger import fixture


def evidence(request, identifier, **options):
    saved = row(request, identifier, absent=True, provider=route.PROVIDER, **options)
    saved["assessment"] = service.assess(saved, classifier.CONFIG)
    return saved


def assignments(arms=institution.ARMS):
    return tuple(dict(id=f"fabricated-deepinfra-{i}", game=fixture(2), arm=arm,
                      seed_base=91000000 + 64 * i) for i, arm in enumerate(arms))


def run(*, bad_index=None, unsafe=False):
    seen, events = [], []
    def respond(request, key):
        seen.append(deepcopy(request))
        options = dict(raw="not JSON") if len(seen) == bad_index else {}
        if unsafe:
            options["native"] = False
        return evidence(request, key, **options)
    result = execution.execute(assignments(), respond=respond, verify=lambda: None,
                               persist=lambda event: events.append(deepcopy(event)))
    return result, seen, events


def test_full_all_arm_two_term_execution_and_no_scientific_claim():
    result, seen, events = run()
    assert result["completed"] == 4 and not result["global_safety_stop"]
    assert len(seen) == 120 and events[-1]["event"] == "terminal"
    assert not result["publication_evidence"] and not result["allocation_authorized"]
    for assignment, record in zip(assignments(), result["assignments"], strict=True):
        expected = institution.episode(assignment["game"], assignment["arm"],
            lambda actor, identity, term, stage, context, index: action(
                requests.action_request(assignment["game"], assignment["arm"],
                    assignment["seed_base"], actor, identity, term, stage, context, index)))
        assert record["outcome"] == expected
        assert all(t.requested == t.executed for t in record["terms"])
        assert record["first_term"]["complete"] and record["two_term"]["complete"]
        for slot in record["logicals"]:
            payload = json.loads(slot["request"]["messages"][1]["content"])
            assert len(payload["history"]) == slot["term"]
            assert payload["acting_identity"] == slot["identity"]
            assert payload["office_value"] == 24
            if slot["stage"] == "response":
                assert "responses" not in payload
            assert slot["request"]["provider"]["only"] == ["deepinfra/fp4"]


@pytest.mark.parametrize("bad_index", [1, 8, 15, 16, 23, 30])
def test_content_failure_never_repaired_or_replaced(bad_index):
    result, seen, _ = run(bad_index=bad_index)
    assert result["content_failed"] == 1 and result["completed"] == 3
    assert not result["global_safety_stop"] and len(seen) == bad_index + 90
    first = result["assignments"][0]
    assert first["outcome"] is None
    assert first["first_term"]["complete"] is (bad_index > 15)
    assert first["logicals"][bad_index - 1]["classification"]["action"] is None


def test_missing_native_reasoning_remains_global_failure():
    result, seen, _ = run(unsafe=True)
    assert result["global_safety_stop"] and len(seen) == 1
    assert all(r["status"] == "not_started" for r in result["assignments"][1:])


def test_only_provider_configuration_changes_in_every_request():
    def ask(actor, identity, term, stage, context, index):
        before = deepcopy(context)
        old = old_requests.action_request(fixture(2), "binding_majority", 1,
            actor, identity, term, stage, context, index)
        new = requests.action_request(fixture(2), "binding_majority", 1,
            actor, identity, term, stage, context, index)
        assert context == before
        assert {k:v for k,v in old.items() if k != "provider"} == {
            k:v for k,v in new.items() if k != "provider"}
        assert new["provider"]["only"] == new["provider"]["order"] == [route.TAG]
        assert new["provider"]["quantizations"] == ["fp4"]
        assert new["provider"]["require_parameters"] is True
        assert new["provider"]["allow_fallbacks"] is False
        return action(new)
    institution.episode(fixture(2), "binding_majority", ask)


@pytest.mark.parametrize("attempt,delay", [(1,300), (2,600), (3,1200), (4,None)])
def test_answerless_recovery_is_provider_specific_and_bounded(attempt, delay):
    seen = []
    institution.episode(fixture(2), "binding_sum", lambda a,i,t,s,c,n:
        seen.append(requests.action_request(fixture(2), "binding_sum", 1,a,i,t,s,c,n)) or action(seen[-1]))
    request = seen[0]
    saved = evidence(request, "fabricated-429")
    saved["stream"] = answerless(Clock())
    error = json.loads(saved["stream"]["http_error_body"])
    error["error"]["metadata"]["provider_name"] = route.PROVIDER
    saved["stream"]["http_error_body"] = json.dumps(error)
    saved["receipts"] = []
    result = policy.eligibility(saved, physical_attempt=attempt, block_reissues_used=0,
                               block_started_unix=1000, detected_unix=1000)
    assert result["eligible"] is (delay is not None)
    assert result["delay_seconds"] == delay
    error["error"]["metadata"]["provider_name"] = old_route.PROVIDER
    saved["stream"]["http_error_body"] = json.dumps(error)
    assert not policy.eligibility(saved, physical_attempt=1, block_reissues_used=0,
                                 block_started_unix=1000, detected_unix=1000)["eligible"]


def test_atlascloud_answer_is_not_inherited_as_deepinfra_pass():
    seen = []
    institution.episode(fixture(2), "binding_sum", lambda a,i,t,s,c,n:
        seen.append(requests.action_request(fixture(2), "binding_sum", 1,a,i,t,s,c,n)) or action(seen[-1]))
    saved = row(seen[0], "historical-route", absent=True)
    saved["assessment"] = service.assess(saved, classifier.CONFIG)
    result = classifier.classify(saved, seen[0], fixture(2), "draft")
    assert result["status"] == "unsafe_failed" and result["action"] is None


def test_economic_controller_is_the_original_controller():
    assert execution.institution is institution
    assert asdict(fixture(2))["office_value"] == 24
