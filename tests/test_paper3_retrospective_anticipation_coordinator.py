"""Private source/financial copies, fabricated transport/replay only. No API."""
from copy import deepcopy
import json

import pytest

from paper3 import retrospective_anticipation_coordinator as coordinator
from paper3 import retrospective_episode_journal as journal
from paper3.pivot_b_budget import atomic
from tests import test_paper3_retrospective_anticipation_freeze as copied
from tests import test_paper3_retrospective_independent_calls as fabricated


@pytest.fixture
def private(tmp_path, monkeypatch):
    return copied.private.__wrapped__(tmp_path, monkeypatch)


def prepare(private):
    return copied.prepare(private)


def hooks(*, native=True, bad=True, started=1000):
    clock, sent = fabricated.Clock(), []
    clock.now = started
    def send(wire, secret):
        assert secret is None
        request = json.loads(wire)
        sent.append(request)
        value = fabricated.action(request)
        if bad:
            value["policy"] = True
        trace = fabricated.row(request, f"fake-{len(sent)}", value=value, native=native)["stream"]
        trace["started_unix"] = clock()
        clock.sleep(1)
        trace["ended_unix"] = clock()
        return trace
    def lookup(key, secret):
        return dict(http_status=404, error_type="HTTPError", data=None, secret_redacted=False)
    return dict(metadata=copied.metadata(), metadata_observed_unix=clock(), send=send,
                lookup=lookup, clock=clock, sleep=clock.sleep), sent


def execute(private, protocol, batch=0, **kwargs):
    return coordinator.run_block(*private, protocol, batch, **kwargs)


def next_hooks(private):
    end = journal.load(private[0] / "sessions/block-0-terminal.json")
    return hooks(started=end["completed_unix"] + 1)


def fake_certificate(partial):
    # Unit-test callback ONLY, not a claim that archive isolation has happened.
    return dict(protocol=partial["protocol"],
        report_sha256=journal.physical.t.sha(journal.canonical(journal.encode(partial)).encode()),
        isolated_report_matched=True, network_guard_self_test=True, archive_sha256="a"*64,
        fabricated=True)


def test_batch0_local_failures_retain_all16_cases_and_entire_budget(private):
    protocol = prepare(private)
    options, sent = hooks()
    result = execute(private, protocol, **options)
    assert len(sent) == 8
    assert result["analysis"]["assigned"] == 16 and result["analysis"]["first_terms_complete"] == 0
    assert result["blocks"][0]["evidence"]["report"]["content_failed"] == 8
    assert result["blocks"][1]["status"] == "not_launched"
    assert result["budget"]["entries"] == result["budget"]["uncertified"] == 8
    assert result["budget"]["pending"] == 0
    assert result["production_source_protocol_verified"] and not result["publication_evidence"]
    group, blocks = coordinator.layout(private[0], private[2], protocol)
    assert len(journal.load(private[2] / "stage_groups" / (group+".json"))["stages"]) == 2
    assert not blocks[1]["root"].exists()
    with pytest.raises(ValueError, match="never restart"):
        execute(private, protocol, **hooks()[0])
    assert len(sent) == 8


def test_safe_content_failures_do_not_selectively_block_second_assigned_frame(private):
    protocol = prepare(private)
    first, sent0 = hooks()
    execute(private, protocol, **first)
    second, sent1 = next_hooks(private)
    second["certify_partial"] = fake_certificate
    result = execute(private, protocol, 1, **second)
    assert len(sent0) == len(sent1) == 8
    assert all(b["status"] == "audited_terminal" for b in result["blocks"])
    assert result["budget"]["entries"] == 16
    assert result["analysis"]["candidate_screen"]["status"] == "incomplete_first_term"
    second["metadata_observed_unix"] = second["clock"]()
    with pytest.raises(ValueError, match="never restart"):
        execute(private, protocol, 1, **second)


def test_unsafe_first_block_preserves_failed_cost_and_blocks_second_frame(private):
    protocol = prepare(private)
    first, sent0 = hooks(native=False)
    result = execute(private, protocol, **first)
    assert len(sent0) == 1 and result["blocks"][0]["evidence"]["report"]["global_safety_stop"]
    second, sent1 = next_hooks(private)
    second["certify_partial"] = fake_certificate
    with pytest.raises(ValueError, match="unsafe/incomplete"):
        execute(private, protocol, 1, **second)
    assert not sent1 and result["budget"]["uncertified"] == 1


def test_batch1_without_actual_replay_callback_refused_before_transport(private):
    protocol = prepare(private)
    execute(private, protocol, **hooks()[0])
    second, sent = next_hooks(private)
    with pytest.raises(ValueError, match="isolated batch0 replay"):
        execute(private, protocol, 1, **second)
    assert not sent


def test_fresh_route_observation_required_before_allocation_or_start(private):
    protocol = prepare(private)
    options, sent = hooks()
    options["metadata_observed_unix"] -= 61
    with pytest.raises(ValueError, match="fresh explicit"):
        execute(private, protocol, **options)
    assert not sent and not (private[2] / "stage_groups").exists()
    assert not (private[0] / "sessions/start.json").exists()


def test_changed_prefreeze_ledger_preserves_new_entry_and_cannot_launch(private):
    protocol = prepare(private)
    atomic(private[2] / "entries/unrelated.json", dict(stage="unrelated", status="reserved", reserved_usd=".1"))
    options, sent = hooks()
    with pytest.raises(ValueError, match="financial baseline"):
        execute(private, protocol, **options)
    assert not sent and not (private[2] / "stage_groups").exists()
    # Attempted startup is retained, not treated as permission to try again.
    assert (private[0] / "sessions/start.json").exists()
    assert (private[2] / "entries/unrelated.json").exists()


@pytest.mark.parametrize("mutation", ("terminal", "group", "pilot_start"))
def test_modified_runtime_provenance_cannot_pass_scientific_audit(private, mutation):
    protocol = prepare(private)
    execute(private, protocol, **hooks()[0])
    root, repo, ledger = private
    if mutation == "terminal":
        path = root / "sessions/block-0-terminal.json"
        record = journal.load(path)
        evidence = journal.decode(record["evidence"])
        evidence["physical_attempts"] += 1
        record["evidence"] = journal.encode(evidence)
    elif mutation == "group":
        group, _ = coordinator.layout(root, ledger, protocol)
        path = ledger / "stage_groups" / (group+".json")
        record = journal.load(path)
        record["cap_usd"] = "0"
    else:
        path = root / "sessions/start.json"
        record = journal.load(path)
        record["protocol"] = "0"*64
    atomic(path, record)
    with pytest.raises(ValueError):
        coordinator.audit(root, repo, ledger, protocol)


def test_interrupted_start_preserves_data_and_never_invents_terminal(private, monkeypatch):
    protocol = prepare(private)
    ordinary = coordinator.transport.Calls
    def fail(*args, **kwargs):
        raise OSError("fabricated initialization interruption")
    monkeypatch.setattr(coordinator.transport, "Calls", fail)
    options, sent = hooks()
    with pytest.raises(OSError):
        execute(private, protocol, **options)
    assert not sent
    assert (private[0] / "sessions/block-0-start.json").exists()
    assert not (private[0] / "sessions/block-0-terminal.json").exists()
    monkeypatch.setattr(coordinator.transport, "Calls", ordinary)
    with pytest.raises(ValueError, match="never restart"):
        execute(private, protocol, **options)
    with pytest.raises(ValueError, match="interrupted block"):
        coordinator.audit(*private, protocol)


def test_replay_certificate_must_match_entire_partial_report(private):
    protocol = prepare(private)
    execute(private, protocol, **hooks()[0])
    second, sent = next_hooks(private)
    def altered(partial):
        value = deepcopy(fake_certificate(partial))
        value["report_sha256"] = "0"*64
        return value
    second["certify_partial"] = altered
    with pytest.raises(ValueError, match="isolated partial replay"):
        execute(private, protocol, 1, **second)
    assert not sent and not (private[0] / "block-1").exists()


def test_replay_delay_cannot_make_stale_supplied_metadata_into_a_valid_start(private):
    protocol = prepare(private)
    execute(private, protocol, **hooks()[0])
    second, sent = next_hooks(private)
    def slow_replay(partial):
        second["clock"].sleep(65)  # Explicitly model expensive REAL wall-clock replay.
        return fake_certificate(partial)
    second["certify_partial"] = slow_replay
    with pytest.raises(ValueError, match="fresh explicit"):
        execute(private, protocol, 1, **second)
    assert not sent and not (private[0] / "sessions/block-1-start.json").exists()
    assert not (private[0] / "sessions/partial-replay.json").exists()


def test_endpoint_is_observed_once_after_expensive_second_block_replay(private):
    protocol = prepare(private)
    execute(private, protocol, **hooks()[0])
    second, sent = next_hooks(private)
    second.pop("metadata")
    second.pop("metadata_observed_unix")
    observations, replay_finished = [], []
    def slow_replay(partial):
        second["clock"].sleep(65)
        replay_finished.append(second["clock"]())
        return fake_certificate(partial)
    def observe():
        assert replay_finished
        observations.append(second["clock"]())
        return copied.metadata(), second["clock"]()
    second.update(certify_partial=slow_replay, observe_metadata=observe)
    result = execute(private, protocol, 1, **second)
    assert len(observations) == 1 and observations[0] >= replay_finished[0]
    start = journal.load(private[0] / "sessions/block-1-start.json")
    assert 0 <= start["started_unix"] - start["metadata_observed_unix"] <= 60
    assert len(sent) == 8 and result["analysis"]["assigned"] == 16
    assert result["analysis"]["candidate_screen"]["status"] == "incomplete_first_term"


def test_two_endpoint_observation_modes_cannot_silently_choose_one(private):
    protocol = prepare(private)
    options, sent = hooks()
    observations = []
    options["observe_metadata"] = lambda: observations.append("must not fetch")
    with pytest.raises(ValueError, match="one explicit endpoint"):
        execute(private, protocol, **options)
    assert not observations and not sent and not (private[2] / "stage_groups").exists()
