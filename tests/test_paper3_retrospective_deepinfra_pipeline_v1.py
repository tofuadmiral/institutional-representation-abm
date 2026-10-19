"""PRIVATE complete scripted pipeline, not a qualification or empirical result.

Uses copied genuine authority/ledger and fabricated native responses. Only the
PRIVATE copied readiness record is fabricated to exercise production guards;
it cannot certify the real checkout. Actual readiness comes from this command's
authentic output with exact before/after source hashes, never these test fixtures.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from experiments import paper3_retrospective_deepinfra_pilot_v1 as runner
from paper3 import retrospective_deepinfra_archive_v1 as archive
from paper3 import retrospective_deepinfra_budget_v1 as budget
from paper3 import retrospective_deepinfra_coordinator_v1 as coordinator
from paper3 import retrospective_deepinfra_design_v1 as design
from paper3 import retrospective_deepinfra_freeze_v1 as freeze
from paper3 import retrospective_deepinfra_operating_v1 as operating
from paper3 import retrospective_deepinfra_retirement_v1 as retirement
from paper3 import retrospective_deepinfra_route_v1 as route
from paper3 import retrospective_episode_journal as journal
from tests.test_paper3_retrospective_deepinfra_core_v1 import evidence
from tests.test_paper3_retrospective_independent_calls import Clock, answerless

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def complete(tmp_path_factory):
    base = tmp_path_factory.mktemp("deepinfra-private-complete")
    code = base/"code"
    for name in operating.readiness_inventory(REPO):
        target = code/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(REPO/name,target)
    ledger = code/"results/paper3/pivot_b_budget"
    shutil.copytree(REPO/"results/paper3/pivot_b_budget",ledger,dirs_exist_ok=True,
                    copy_function=shutil.copyfile)
    prior = freeze.inventory(ledger)
    sources = operating.readiness_inventory(code)
    private_readiness = dict(format=operating.READINESS_FORMAT,sources_before=sources,
        sources_after=sources,specification_sha256=journal.physical.t.sha(
            journal.canonical(freeze.specification()).encode()),
        checks={name:dict(argv=command,returncode=0,stdout="1 passed in 0.01s\n",stderr="")
                for name,command in operating.REQUIRED_CHECKS.items()},actual_model_calls=0)
    budget.atomic(code/freeze.READINESS_FILE,private_readiness)
    pin = dict(path=freeze.READINESS_FILE,sha256=journal._digest(code/freeze.READINESS_FILE))
    metadata = journal.load(REPO/"results/paper3/deepinfra_bounded_pilot_endpoint_observation_2026_10_19.json")
    root = code/"results/paper3"/runner.STAGE
    protocol = freeze.prepare(root,code,ledger,metadata=metadata,operating_readiness=pin)
    clock,sent = Clock(),[]
    def send(wire,secret):
        assert secret is None
        request = json.loads(wire)
        sent.append((wire,clock()))
        if len(sent) == 1:
            trace = answerless(clock)
            error = json.loads(trace["http_error_body"])
            error["error"]["metadata"]["provider_name"] = route.PROVIDER
            trace["http_error_body"] = json.dumps(error)
        else:
            trace = evidence(request,f"fabricated-deepinfra-{len(sent)}")["stream"]
        trace["started_unix"] = clock()
        clock.sleep(1)
        trace["ended_unix"] = clock()
        return trace
    def lookup(identifier,secret):
        assert secret is None
        return dict(http_status=200,error_type=None,secret_redacted=False,data=dict(
            id=identifier,model=route.MODEL_ALIAS,provider_name=route.PROVIDER,total_cost=.0001))
    def observe():
        return deepcopy(metadata),clock()
    first = coordinator.run_block(root,code,ledger,protocol,0,observe_metadata=observe,
        send=send,lookup=lookup,clock=clock,sleep=clock.sleep)
    assert first["analysis"]["first_terms_complete"] == 8
    assert first["analysis"]["candidate_screen"]["status"] == "incomplete_first_term"
    assert first["blocks"][0]["evidence"]["physical_attempts"] == 241
    assert not first["blocks"][0]["evidence"]["report"]["global_safety_stop"]
    coordinator.close_terminal_block(root,code,ledger,protocol,0)
    target = base/"partial"
    certificate = archive.export(root,code,ledger,protocol,None,None,target,base/"partial.zip")
    def certify(partial):
        proof = archive.isolated_certificate(target,base/"partial.zip",protocol)
        assert proof["report_sha256"] == archive.report_sha(partial)
        return proof
    final = coordinator.run_block(root,code,ledger,protocol,1,observe_metadata=observe,
        certify_partial=certify,send=send,lookup=lookup,clock=clock,sleep=clock.sleep)
    final = coordinator.close_terminal_block(root,code,ledger,protocol,1)
    full_certificate = archive.export(root,code,ledger,protocol,None,None,
        base/"complete",base/"complete.zip")
    assert all(freeze.inventory(ledger).get(k) == v for k,v in prior.items())
    return dict(root=root,repo=code,ledger=ledger,protocol=protocol,report=final,
        partial_certificate=certificate,full_certificate=full_certificate,sent=sent,base=base)


def test_actual_full_sixteen_episode_execution_partial_and_full_isolated_replay(complete):
    report = complete["report"]
    assert report["assigned"] == report["analysis"]["episodes_complete"] == 16
    assert report["analysis"]["first_terms_complete"] == 16
    assert report["analysis"]["candidate_screen"]["status"] != "incomplete_first_term"
    assert len(complete["sent"]) == 481  # Included one eligible answerless reissue.
    assert complete["sent"][0][0] == complete["sent"][1][0]
    assert complete["sent"][1][1]-complete["sent"][0][1] >= 300
    for proof in (complete["partial_certificate"],complete["full_certificate"]):
        assert proof["isolated_report_matched"] and proof["network_guard_self_test"]
        assert proof["retirement_binding_verified"]
        assert not proof["inherited_provider_qualification_pass"]
        assert not proof["publication_evidence"]
    assert len(report["analysis"]["assignments"]) == 16
    assert report["budget"]["pending"] == 4
    assert report["budget"]["uncertified"] == 323
    assert report["budget"]["entries"] == 6787+481
    assert report["budget"]["unspent_active_stage_caps_usd"] == "0.29045544"
    for record in report["blocks"]:
        assert not record["evidence"]["report"]["global_safety_stop"]
        for assignment in record["evidence"]["report"]["assignments"]:
            assert len(assignment["outcome"].cumulative_citizen_utilities) == 7
            assert all(len(d) == 9 for d in assignment["outcome"].cumulative_citizen_utilities)
            assert all(t.requested == t.executed for t in assignment["terms"])


def test_terminal_root_is_not_restartable_and_tampered_bundle_is_rejected(complete):
    with pytest.raises(ValueError, match="block already started"):
        coordinator.run_block(complete["root"],complete["repo"],complete["ledger"],
            complete["protocol"],0,observe_metadata=lambda: (_ for _ in ()).throw(
                AssertionError("restart must fail before any observation")),
            send=lambda *a:None,lookup=lambda *a:None)
    bundle = complete["base"]/"complete"
    path = bundle/"expected_report.json"
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError):
        archive.isolated_certificate(bundle,complete["base"]/"complete.zip",complete["protocol"])


def test_new_design_is_complete_and_whole_budget_is_bounded():
    assignments = design.assignments()
    bound = design.full_bound()
    assert len(assignments) == 16 and bound["logical_calls"] == 480
    assert bound["maximum_physical_calls"] == 560
    assert budget.amount(bound["full_reservation_usd"]) <= budget.amount("9")
    assert retirement.ENTRY_COUNT == 6787
