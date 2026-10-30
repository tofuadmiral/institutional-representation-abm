"""Bounded PRIVATE software integration; no provider qualification or paid calls.

The economic controller executes all480 scripted actions in memory. A separate
small real transport/ledger/freeze/archive path exercises overload recovery and
actual isolated replay, without another hours-long480-call fake-ledger ladder.
Only the PRIVATE fixture's readiness is fabricated to exercise admission guards;
the real checkout must use this command's genuine complete terminal output.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from experiments import paper3_retrospective_deepinfra_pilot_v2 as runner
from paper3 import retrospective_deepinfra_archive_v2 as archive
from paper3 import retrospective_deepinfra_budget_v2 as budget
from paper3 import retrospective_deepinfra_coordinator_v2 as coordinator
from paper3 import retrospective_deepinfra_design_v1 as previous_design
from paper3 import retrospective_deepinfra_design_v2 as design
from paper3 import retrospective_deepinfra_execution_v1 as execution
from paper3 import retrospective_deepinfra_freeze_v2 as freeze
from paper3 import retrospective_deepinfra_operating_v2 as operating
from paper3 import retrospective_deepinfra_route_v1 as route
from paper3 import retrospective_episode_journal as journal
from tests.test_paper3_retrospective_deepinfra_core_v1 import evidence
from tests.test_paper3_retrospective_deepinfra_overload_v2 import overload
from tests.test_paper3_retrospective_independent_calls import Clock

REPO = Path(__file__).resolve().parents[1]


def test_unchanged_all_sixteen_games_and_all480_scripted_economic_actions():
    items, old = design.assignments(), previous_design.assignments()
    assert len(items) == 16
    for before, after in zip(old, items, strict=True):
        assert before["game"] == after["game"] and before["arm"] == after["arm"]
        assert before["stratum"] == after["stratum"]
        assert before["seed_base"] != after["seed_base"]
    sent = []
    def respond(request, key):
        sent.append(key)
        return evidence(request, key)
    result = execution.execute(items, respond=respond, verify=lambda: None,
                               persist=lambda event: None)
    assert result["completed"] == 16 and len(sent) == 480
    assert not result["global_safety_stop"]
    for assignment in result["assignments"]:
        assert all(t.requested == t.executed for t in assignment["terms"])
        assert len(assignment["outcome"].cumulative_citizen_utilities) == 7
        assert all(len(d) == 9 for d in assignment["outcome"].cumulative_citizen_utilities)
    bound = design.full_bound()
    assert bound["logical_calls"] == 480 and bound["maximum_physical_calls"] == 560
    assert bound["full_reservation_usd"] == previous_design.full_bound()["full_reservation_usd"]


@pytest.fixture(scope="module")
def partial(tmp_path_factory):
    base = tmp_path_factory.mktemp("deepinfra-overload-private")
    code = base / "code"
    for name in operating.readiness_inventory(REPO):
        target = code / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, target)
    ledger = code / "results/paper3/pivot_b_budget"
    shutil.copytree(REPO / "results/paper3/pivot_b_budget", ledger, dirs_exist_ok=True)
    sources = operating.readiness_inventory(code)
    private_readiness = dict(format=operating.READINESS_FORMAT, sources_before=sources,
        sources_after=sources, specification_sha256=journal.physical.t.sha(
            journal.canonical(freeze.specification()).encode()),
        checks={name: dict(argv=argv, returncode=0, stdout="1 passed in 0.01s\n", stderr="")
                for name, argv in operating.REQUIRED_CHECKS.items()}, actual_model_calls=0)
    budget.atomic(code / freeze.READINESS_FILE, private_readiness)
    pin = dict(path=freeze.READINESS_FILE, sha256=journal._digest(code / freeze.READINESS_FILE))
    metadata = journal.load(REPO / "results/paper3/deepinfra_bounded_pilot_endpoint_observation_2026_10_19.json")
    root = code / "results/paper3" / runner.STAGE
    protocol = freeze.prepare(root, code, ledger, metadata=metadata, operating_readiness=pin)
    clock, sent = Clock(), []
    def send(wire, secret):
        assert secret is None
        sent.append((wire, clock()))
        if len(sent) == 1:
            trace = overload()["stream"]
            trace["retry_after"] = "900"
        else:
            request = json.loads(wire)
            trace = evidence(request, f"fabricated-new-{len(sent)}",
                             native=len(sent) != 3)["stream"]
        trace.update(started_unix=clock(), ended_unix=clock())
        return trace
    def lookup(identifier, secret):
        assert secret is None
        return dict(http_status=200, error_type=None, secret_redacted=False,
            data=dict(id=identifier, model=route.MODEL_ALIAS,
                      provider_name=route.PROVIDER, total_cost=.0001))
    report = coordinator.run_block(root, code, ledger, protocol, 0,
        observe_metadata=lambda: (deepcopy(metadata), clock()), send=send,
        lookup=lookup, clock=clock, sleep=clock.sleep)
    assert report["blocks"][0]["evidence"]["report"]["global_safety_stop"]
    assert len(sent) == 3 and sent[0][0] == sent[1][0]
    assert sent[1][1] - sent[0][1] >= 900
    report = coordinator.close_terminal_block(root, code, ledger, protocol, 0)
    target, zipped = base / "archive", base / "archive.zip"
    certificate = archive.export(root, code, ledger, protocol, None, None, target, zipped)
    return dict(root=root, code=code, ledger=ledger, protocol=protocol, report=report,
                certificate=certificate, target=target, zip=zipped)


def test_actual_overload_retry_costs_source_freeze_and_cold_archive_replay(partial):
    report, certificate = partial["report"], partial["certificate"]
    evidence = report["blocks"][0]["evidence"]
    assert evidence["physical_attempts"] == 3 and evidence["physical_reissues"] == 1
    assert report["assigned"] == 16 and report["analysis"]["episodes_complete"] == 0
    assert report["analysis"]["candidate_screen"]["status"] == "incomplete_first_term"
    assert report["budget"]["entries"] == 6913
    assert report["budget"]["pending"] == 4 and report["budget"]["uncertified"] == 324
    assert report["budget"]["cap_usd"] == "19.30"
    assert certificate["isolated_report_matched"] and certificate["network_guard_self_test"]
    assert certificate["retirement_binding_verified"]
    assert not certificate["inherited_provider_qualification_pass"]
    assert not certificate["publication_evidence"]


def test_unsafe_failure_still_prevents_second_block_without_any_observer(partial):
    with pytest.raises(ValueError, match="unsafe/incomplete previous block"):
        coordinator.run_block(partial["root"], partial["code"], partial["ledger"],
            partial["protocol"], 1, observe_metadata=lambda: (_ for _ in ()).throw(
                AssertionError("no route observation allowed")), certify_partial=lambda _: {},
            send=lambda *a: None, lookup=lambda *a: None)


def test_default_backend_is_retry_after_capturing_transmitter():
    from paper3 import hosted_reasoning_transport_v2 as transmitter
    send, lookup = operating.resolve_default_transport()
    assert send is transmitter.transmit and callable(lookup)


def test_total1930_ledger_preserves_every_prior_entry_and_only_unused_retirement():
    ledger = budget.RecoveryLedger(REPO / "results/paper3/pivot_b_budget",
                                  retirement_pins=freeze.RETIREMENT_PINS)
    value = ledger.snapshot()
    assert value["cap_usd"] == "19.30" and value["entries"] == 6910
    assert value["accounted_usd"] == "10.224219931"
    assert value["unspent_active_stage_caps_usd"] == "0.29045544"
    assert budget.amount(value["available_for_new_stages_usd"]) >= budget.amount(
        design.full_bound()["full_reservation_usd"])
