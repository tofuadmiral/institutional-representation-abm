"""Private fabricated receipt/network tests, never experimental observations."""
from pathlib import Path
import shutil

import pytest

from experiments import paper3_billing_recovery_v1 as runner
from experiments import paper3_graceful_continuation as old
from paper3 import retrospective_receipt_recovery_v1 as billing
from paper3.retrospective_graceful_recovery import load
from paper3.pivot_b_budget import atomic
from tests.test_paper3_graceful_continuation import private_runner

REPO = Path(__file__).resolve().parents[1]
SAVED = REPO / old.ROOT_NAME / "block-1/calls" / (runner.FAILED + ".json")


def timeout(offset=0):
    return dict(http_status=None, error_type="TimeoutError", data=None,
                secret_redacted=False, scheduled_offset_seconds=offset)


def absent(offset):
    return dict(http_status=404, error_type="HTTPError", data=None,
                secret_redacted=False, scheduled_offset_seconds=offset)


def receipt(row, offset=20):
    summary = row["assessment"]["stream"]
    return dict(http_status=200, error_type=None, secret_redacted=False,
                scheduled_offset_seconds=offset,
                data=dict(id=summary["generation_id"], model=old.route.MODEL,
                          provider_name=old.route.PROVIDER,
                          total_cost=summary["usage"]["cost"]))


def saved_view(observations):
    raw = load(SAVED)
    supplement = dict(amendment_protocol="f" * 64,
        original=dict(path=SAVED.relative_to(REPO).as_posix(), sha256=runner.FAILED_SHA),
        observations=observations)
    return raw, runner.make_view(raw, supplement)


def test_saved_complete_answer_with_receipt_timeout_is_not_regenerated_or_modified():
    before = SAVED.read_bytes()
    raw = load(SAVED)
    original, view = saved_view([receipt(raw)])
    assert view["result"]["status"] == "recorded_valid"
    assert view["request_text"] == original["request_text"]
    assert view["stream"] == original["stream"]
    assert view["final_content"] == original["final_content"]
    assert view["billing_recovery"]["original_result"]["status"] == "unsafe_failed"
    assert SAVED.read_bytes() == before


def test_four_absent_or_transient_receipts_keep_entire_reservation():
    raw, view = saved_view([timeout(20), absent(40), timeout(60)])
    assert view["result"]["status"] == "recorded_valid"
    a = view["assessment"]
    assert a["passed"] and not a["receipt_certified"]
    assert a["accounted_usd"] == raw["reserved_usd"]
    assert [o["scheduled_offset_seconds"] for o in view["receipts"]] == [0, 20, 40, 60]


@pytest.mark.parametrize("status,error,data,redacted", [
    (401, "HTTPError", None, False), (402, "HTTPError", None, False),
    (403, "HTTPError", None, False), (429, "HTTPError", None, False),
    (200, None, {}, False), (None, "ValueError", None, False),
    (None, "TimeoutError", None, True), (None, "TimeoutError", {}, False),
])
def test_unknown_auth_invalid_receipts_never_become_temporary(status,error,data,redacted):
    assert not billing.benign(dict(http_status=status, error_type=error,
                                  data=data, secret_redacted=redacted))


@pytest.mark.parametrize("change", ["wrong_id", "wrong_cost", "wrong_provider", "partial_stream"])
def test_billing_recovery_preserves_conflict_stream_route_and_usage_failures(change):
    raw = load(SAVED)
    observation = receipt(raw)
    if change == "wrong_id":
        observation["data"]["id"] = "different"
    if change == "wrong_cost":
        observation["data"]["total_cost"] = 0.012
    if change == "wrong_provider":
        observation["data"]["provider_name"] = "other"
    if change == "partial_stream":
        raw["stream"]["error_type"] = "TimeoutError"
    raw["receipts"].append(observation)
    assert not billing.assess(raw, old.failure.previous.CONFIG)["passed"]


def test_only_dependencies_change_not_frozen_validator_or_economic_code():
    assert billing.classify_action.__code__ is billing.classifier.classify.__code__
    assert billing.classify.__code__ is billing.failure.classify.__code__
    assert billing.execute.__code__ is billing.engine.execute.__code__
    assert billing.Calls.one.__code__ is billing.native.Calls.one.__code__
    row = load(SAVED)
    row["receipts"] = [receipt(row, 0)]
    assert billing.assess(row, old.failure.previous.CONFIG) == billing.previous.assess(
        row, old.failure.previous.CONFIG)


def private_recovery(tmp_path, monkeypatch):
    root = tmp_path / old.ROOT_NAME
    meta = root / "billing_amendment_v1"
    meta.mkdir(parents=True)
    target = root / "block-1/calls" / SAVED.name
    target.parent.mkdir(parents=True)
    shutil.copyfile(SAVED, target)
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "META", meta)
    monkeypatch.setattr(runner, "REPO", tmp_path)
    monkeypatch.setattr(runner, "verify", lambda *a, **k: {})
    return root, meta


def test_receipt_only_resume_uses_no_send_and_never_duplicates_finished_get(tmp_path, monkeypatch):
    root, meta = private_recovery(tmp_path, monkeypatch)
    raw = load(SAVED)
    gets = []
    def lookup(identifier, secret):
        gets.append(identifier)
        return receipt(raw)
    assert runner.recover("f" * 64, lookup=lookup, sleep=lambda t: None)["model_calls"] == 0
    assert runner.recover("f" * 64, lookup=lookup, sleep=lambda t: None)["model_calls"] == 0
    assert len(gets) == 1
    assert (root / "block-1/calls" / SAVED.name).read_bytes() == SAVED.read_bytes()
    assert not (root / "block-1/accepted").exists()
    assert load(meta / "recovered.json")["full_historical_charge_retained"]


def test_receipt_conflict_pauses_without_a_second_lookup(tmp_path, monkeypatch):
    _, meta = private_recovery(tmp_path, monkeypatch)
    gets=[]
    def lookup(*args):
        gets.append(1)
        result = receipt(load(SAVED))
        result["data"]["id"] = "conflict"
        return result
    with pytest.raises(ValueError, match="nonretryable/conflicting"):
        runner.recover("f" * 64, lookup=lookup, sleep=lambda t: None)
    assert len(gets)==1 and not (meta / "recovered.json").exists()
    assert (meta / "receipt_observations/20.json").exists()


def test_saved_get_is_adopted_after_index_crash_without_lookup_reissue(tmp_path, monkeypatch):
    _, meta = private_recovery(tmp_path, monkeypatch)
    original = runner.make_view
    crashes=[]
    def crash_once(*args):
        if not crashes:
            crashes.append(1)
            raise KeyboardInterrupt()
        return original(*args)
    monkeypatch.setattr(runner, "make_view", crash_once)
    gets=[]
    def lookup(*args):
        gets.append(1)
        return receipt(load(SAVED))
    with pytest.raises(KeyboardInterrupt):
        runner.recover("f"*64,lookup=lookup,sleep=lambda t: None)
    assert (meta/'receipt_observations/20.json').exists()
    assert runner.recover("f"*64,lookup=lookup,sleep=lambda t: None)['model_calls']==0
    assert len(gets)==1


def test_actual_bound_driver_full480_actions_billing_timeout_no_extra_model_call_and_audit(
        tmp_path, monkeypatch):
    root, legacy, sent, send, old_lookup, book = private_runner(tmp_path, monkeypatch)
    meta = root / "billing_amendment_v1"
    meta.mkdir()
    atomic(root / 'manifest.json', old.verify(root, legacy)[0])
    atomic(meta/'remaining_frame_admission.json',dict(started_unix=0,deadline_unix=10**20))
    monkeypatch.setattr(runner,'ROOT',root)
    monkeypatch.setattr(runner,'META',meta)
    monkeypatch.setattr(runner,'REPO',tmp_path)
    monkeypatch.setattr(runner,'OLD_PROTOCOL',legacy)
    amendment=dict(prior_files={},disclosure='PRIVATE fabricated software fixture')
    monkeypatch.setattr(runner,'verify',lambda *a,**k:amendment)
    protocol='f'*64
    get_counts={}
    def lookup(identifier, secret):
        get_counts[identifier]=get_counts.get(identifier,0)+1
        if identifier=='gen-private-2' and get_counts[identifier]==1:
            return timeout()
        return old_lookup(identifier,secret)
    run,audit,_,_=runner.drivers(protocol)
    result=run(root,legacy,send=send,lookup=lookup)
    assert result['status']=='complete' and len(sent)==481
    assert get_counts['gen-private-2']==2
    report=old.journal.decode(load(root/'report.json'))
    assert report['analysis']['episodes_complete']==16
    assert report['billing_amendment']['protocol']==protocol
    assert audit(root,legacy)['entire_report_matched']
    assert len(sent)==481
    assert report['assignments'][0]['logicals'][0]['evidence']['receipts'][0]['error_type']=='TimeoutError'
