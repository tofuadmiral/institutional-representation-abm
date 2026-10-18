"""Private orchestration, fabricated source guard/transport/certificate; no API.

Real source freezing is checked in the separate freeze suite. These tests do NOT
claim operating readiness or actual isolated archive replay.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_resource_coordinator_v1 as coordinator
from paper3.pivot_b_budget import atomic
from tests import test_paper3_retrospective_independent_calls as fabricated

PROTOCOL = "f" * 64
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def private(tmp_path, monkeypatch):
    root, repo, ledger = tmp_path / "run", tmp_path / "code", tmp_path / "ledger"
    root.mkdir()
    repo.mkdir()
    (ledger / "entries").mkdir(parents=True)
    for name in coordinator.budget.AUTHORITY_FILES:
        shutil.copy2(REPO / "results/paper3/pivot_b_budget" / name, ledger / name)
    atomic(ledger / "entries/old.json", dict(stage="old", status="settled", reserved_usd=".2",
                                            accounted_usd=".2", certified=False))
    scoped = coordinator.budget.RecoveryLedger(ledger)
    baseline = scoped.snapshot()
    history = dict(overlap=[], historical_files=0, fabricated=True)
    manifest = dict(specification=coordinator.freeze.specification(), retirement_pins={},
        prior_entries=coordinator.freeze.inventory(ledger),
        pre_stage_accounted_usd=baseline["accounted_usd"],
        pre_stage_unused_commitments_usd=baseline["unspent_active_stage_caps_usd"], seed_audit=history)
    monkeypatch.setattr(coordinator.freeze, "verify", lambda *a: (deepcopy(manifest), PROTOCOL))
    monkeypatch.setattr(coordinator.design, "seed_audit", lambda *a, **k: deepcopy(history))
    return root, repo, ledger


def hooks(*, native=True, bad=True, started=1000, rate=()):
    clock, sent = fabricated.Clock(), []
    clock.now = started
    old = REPO / "results/paper3/pivot_b_retrospective_score_ledger_gate_v1/manifest.json"
    metadata = deepcopy(journal.load(old)["protocol"]["endpoint_metadata"])
    def send(wire, secret):
        assert secret is None
        request = json.loads(wire)
        sent.append((wire, clock()))
        if len(sent) in rate:
            return fabricated.answerless(clock)
        action = fabricated.action(request)
        if bad:
            action["policy"] = True
        stream = fabricated.row(request, f"fake-coordinator-{len(sent)}", value=action, native=native)["stream"]
        stream["started_unix"] = clock()
        clock.sleep(1)
        stream["ended_unix"] = clock()
        return stream
    def lookup(key, secret):
        return dict(http_status=404, error_type="HTTPError", data=None, secret_redacted=False)
    return dict(metadata=metadata, metadata_observed_unix=clock(), send=send,
                lookup=lookup, clock=clock, sleep=clock.sleep), sent


def run(private, batch=0, **kwargs):
    return coordinator.run_block(*private, PROTOCOL, batch, **kwargs)


def certificate(partial):
    return dict(protocol=PROTOCOL,
        report_sha256=journal.physical.t.sha(journal.canonical(journal.encode(partial)).encode()),
        isolated_report_matched=True, network_guard_self_test=True, archive_sha256="a" * 64,
        fabricated=True)


def later(private):
    end = journal.load(private[0] / "sessions/block-0-terminal.json")
    return hooks(started=end["completed_unix"] + 1)


def test_entire_group_is_reserved_before_first_answer_and_all_content_failures_remain(private):
    options, sent = hooks()
    before = (private[2] / "entries/old.json").read_bytes()
    result = run(private, **options)
    assert len(sent) == 8 and result["assigned"] == 16
    assert result["blocks"][0]["evidence"]["report"]["content_failed"] == 8
    assert result["blocks"][1]["status"] == "not_launched"
    group, blocks = coordinator.layout(private[0], private[2], PROTOCOL)
    record = journal.load(private[2] / coordinator.budget.GROUPS / (group + ".json"))
    assert len(record["stages"]) == 2 and not blocks[1]["root"].exists()
    assert (private[2] / "entries/old.json").read_bytes() == before
    assert result["analysis"]["candidate_screen"]["status"] == "incomplete_first_term"
    with pytest.raises(ValueError, match="never restart"):
        run(private, **hooks()[0])


def test_bounded_recovery_preserves_identical_wire_and_failed_cost(private):
    options, sent = hooks(rate=(1, 2, 3))
    result = run(private, **options)
    evidence = result["blocks"][0]["evidence"]
    assert evidence["physical_attempts"] == 11 and evidence["physical_reissues"] == 3
    assert len({wire for wire, _ in sent[:4]}) == 1
    assert [stamp for _, stamp in sent[:4]] == [1000, 1300, 1900, 3100]
    assert result["budget"]["uncertified"] == 12


def test_batch1_requires_audited_closure_even_with_matching_fabricated_replay(private):
    run(private, **hooks()[0])
    options, sent = later(private)
    with pytest.raises(ValueError, match="unused-cap closure"):
        run(private, 1, certify_partial=certificate, **options)
    assert not sent and not (private[0] / "sessions/block-1-start.json").exists()


def test_both_assigned_blocks_continue_safe_failures_regardless_of_effect_after_closure(private):
    run(private, **hooks()[0])
    before = coordinator.audit(*private, PROTOCOL)
    closed = coordinator.close_terminal_block(*private, PROTOCOL, 0)
    assert closed["budget"]["accounted_usd"] == before["budget"]["accounted_usd"]
    options, sent = later(private)
    result = run(private, 1, certify_partial=certificate, **options)
    assert len(sent) == 8 and all(b["evidence"] is not None for b in result["blocks"])
    assert result["assigned"] == 16 and result["analysis"]["candidate_screen"]["status"] == "incomplete_first_term"


def test_unsafe_stop_blocks_second_frame_without_replacing_cases(private):
    result = run(private, **hooks(native=False)[0])
    assert result["blocks"][0]["evidence"]["report"]["global_safety_stop"]
    coordinator.close_terminal_block(*private, PROTOCOL, 0)
    options, sent = later(private)
    with pytest.raises(ValueError, match="unsafe/incomplete"):
        run(private, 1, certify_partial=certificate, **options)
    assert not sent


def test_no_unrun_closure_or_cached_replay_authority(private):
    run(private, **hooks()[0])
    with pytest.raises(ValueError, match="unstarted/interrupted"):
        coordinator.close_terminal_block(*private, PROTOCOL, 1)
    options, sent = later(private)
    with pytest.raises(ValueError, match="isolated batch0 replay"):
        run(private, 1, **options)
    assert not sent


def test_stale_route_prevents_start_and_allocation(private):
    options, sent = hooks()
    options["metadata_observed_unix"] -= 61
    with pytest.raises(ValueError, match="fresh explicit"):
        run(private, **options)
    assert not sent and not (private[2] / coordinator.budget.GROUPS).exists()
    assert not (private[0] / "sessions/start.json").exists()


def test_changed_financial_baseline_cannot_start_requests_or_silently_reprepare(private):
    atomic(private[2] / "entries/unrelated.json", dict(stage="unrelated", status="reserved", reserved_usd=".1"))
    options, sent = hooks()
    with pytest.raises(ValueError, match="financial baseline"):
        run(private, **options)
    assert not sent and (private[0] / "sessions/start.json").exists()


@pytest.mark.parametrize("mutation", ("terminal", "group", "pilot_start"))
def test_terminal_and_allocation_provenance_cannot_supply_changed_science(private, mutation):
    run(private, **hooks()[0])
    if mutation == "terminal":
        path = private[0] / "sessions/block-0-terminal.json"
        value = journal.load(path)
        evidence = journal.decode(value["evidence"])
        evidence["physical_attempts"] += 1
        value["evidence"] = journal.encode(evidence)
    elif mutation == "group":
        group, _ = coordinator.layout(private[0], private[2], PROTOCOL)
        path = private[2] / coordinator.budget.GROUPS / (group + ".json")
        value = journal.load(path)
        value["cap_usd"] = "0"
    else:
        path = private[0] / "sessions/start.json"
        value = journal.load(path)
        value["protocol"] = "0" * 64
    atomic(path, value)
    with pytest.raises(ValueError):
        coordinator.audit(*private, PROTOCOL)


def test_partial_initialization_never_invents_terminal_or_licenses_restart(private, monkeypatch):
    def interrupted(*args, **kwargs):
        raise OSError("fabricated initialization interruption")
    monkeypatch.setattr(coordinator.transport, "Calls", interrupted)
    options, sent = hooks()
    with pytest.raises(OSError, match="initialization interruption"):
        run(private, **options)
    assert not sent and (private[0] / "sessions/block-0-start.json").exists()
    assert not (private[0] / "sessions/block-0-terminal.json").exists()
    with pytest.raises(ValueError, match="never restart"):
        run(private, **hooks()[0])
