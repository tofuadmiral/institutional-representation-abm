"""PRIVATE fabricated software checks. No paid model or research observations."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from experiments import paper3_independent_validation_v1 as r
from paper3 import retrospective_validation_budget_v1 as budget
from paper3 import retrospective_validation_design_v1 as design
from paper3 import retrospective_graceful_recovery as recovery
from paper3 import retrospective_receipt_recovery_v1 as billing
from paper3 import retrospective_episode_journal as journal
from tests.test_paper3_graceful_continuation import FakeLedger
from tests.test_paper3_graceful_recovery import overload_with_id
from tests.test_paper3_retrospective_deepinfra_core_v1 import evidence
from tests.test_paper3_retrospective_independent_calls import Clock

REPO = Path(__file__).resolve().parents[1]


def fixture(tmp_path, monkeypatch):
    root = tmp_path / "run"
    root.mkdir()
    ledgerroot = tmp_path / "ledger"
    ledgerroot.mkdir()
    (ledgerroot / "entries").mkdir()
    r.atomic(ledgerroot / "authority.json", dict(
        budget_id="paper3-pivot-b-2026-09-24", cap_usd="10.00",
        credit_purchases_authorized=False))
    book = FakeLedger(ledgerroot)
    clock = Clock()
    monkeypatch.setattr(r, "REPO", tmp_path)
    monkeypatch.setattr(r, "LEDGER", "ledger")
    monkeypatch.setattr(r, "time", SimpleNamespace(time=clock))
    # Bound run code captures previous.time; injecting it locally leaves the
    # frozen module and all actual research evidence untouched.
    manifest = dict(prior_entries={}, baseline=dict(prefix={}, failures={}, references={},
        bounds=[dict(frame=f, maximum_new_physical=280, cap_usd="5")
                for f in design.FRAME_SEEDS]))
    p = "e" * 64
    pins = dict(protocol=p, stages=["private-stage-0", "private-stage-1"], stage_pins={})
    monkeypatch.setattr(r, "verify", lambda *a: (manifest, p))
    monkeypatch.setattr(r, "allocate", lambda *a: pins)
    monkeypatch.setattr(r, "validate_pins", lambda *a: None)
    monkeypatch.setattr(r, "ledger", lambda *a: book)
    original_drivers = r.drivers

    def drivers(admission=None):
        run, audit = original_drivers(admission)
        return billing.bind(run, time=SimpleNamespace(time=clock, sleep=clock.sleep)), audit
    monkeypatch.setattr(r, "drivers", drivers)
    r.atomic(root / "allocation.json", pins)
    sent = []
    lookup_counts = {}

    def send(wire, secret):
        assert secret is None
        sent.append((wire, clock()))
        request = json.loads(wire)
        raw = (overload_with_id(request) if len(sent) == 1 else
               evidence(request, "gen-private-" + str(len(sent))))["stream"]
        raw.update(started_unix=clock(), ended_unix=clock())
        return raw

    def lookup(identifier, secret):
        lookup_counts[identifier] = lookup_counts.get(identifier, 0) + 1
        if identifier == "gen-fabricated-overload":
            return dict(http_status=404, error_type="HTTPError", data=None, secret_redacted=False)
        if identifier == "gen-private-3" and lookup_counts[identifier] == 1:
            return dict(http_status=None, error_type="TimeoutError", data=None, secret_redacted=False)
        return dict(http_status=200, error_type=None, secret_redacted=False,
            data=dict(id=identifier, model=r.previous.route.MODEL_ALIAS,
                      provider_name=r.previous.route.PROVIDER, total_cost=0.0001))
    return root, p, sent, send, lookup, book


def test_inventory_fresh_full_four_arm_bounds_and_exact_economic_code():
    rows = design.assignments()
    assert len(rows) == 16
    assert set(design.FRAME_SEEDS).isdisjoint(r.previous.design.FRAME_SEEDS)
    assert {a['seed_base'] for a in rows} == {2026102900, 2026102964}
    assert design.full_bound()['full_reservation_usd'] == '8.78646588'
    assert design.full_bound()['maximum_physical_calls'] == 560
    assert billing.execute.__code__ is billing.engine.execute.__code__
    assert billing.Calls.one.__code__ is billing.native.Calls.one.__code__
    assert r.drivers()[0].__code__ is r.previous.run.__code__
    assert r.drivers()[1].__code__ is r.previous.audit.__code__


def test_full480_new_actions_busy_retry_receipt_timeout_and_entire_report_audit(
        tmp_path, monkeypatch):
    root, p, sent, send, lookup, book = fixture(tmp_path, monkeypatch)
    result = r.run(root, p, send=send, lookup=lookup)
    assert result['status'] == 'complete' and len(sent) == 481, result
    assert sent[0][0] == sent[1][0] and sent[1][1] - sent[0][1] >= 300
    report = journal.decode(recovery.load(root/'report.json'))
    assert report['analysis']['episodes_complete'] == 16
    assert report['analysis']['first_terms_complete'] == 16
    assert report['validation']['independent_fresh_assignments']
    assert len(report['validation']['per_frame_controls']) == 2
    assert all(len(a['terms']) == 2 for a in report['assignments'])
    assert book.snapshot()['entries'] == 481 and book.snapshot()['uncertified'] == 1
    assert r.drivers()[1](root, p)['entire_report_matched']
    assert len(sent) == 481
    with pytest.raises(ValueError, match='already terminal'):
        r.run(root, p, send=send, lookup=lookup)
    # Tampering even one raw response must invalidate the exact financial replay.
    path = next((root/'block-0/calls').glob('*.json'))
    row = recovery.load(path)
    row['reserved_usd'] = '0'
    r.atomic(path, row)
    with pytest.raises(ValueError):
        r.drivers()[1](root, p)


def test_unknown_inflight_reservation_is_not_blindly_resent(tmp_path, monkeypatch):
    root, p, sent, send, lookup, book = fixture(tmp_path, monkeypatch)
    def crash(wire, secret):
        if len(sent) == 3:
            sent.append((wire, 0))
            raise KeyboardInterrupt()
        return send(wire, secret)
    with pytest.raises(KeyboardInterrupt):
        r.run(root, p, send=crash, lookup=lookup)
    count = len(sent)
    result = r.run(root, p, send=crash, lookup=lookup)
    assert result['status'] == 'paused' and len(sent) == count
    assert any(recovery.load(f)['status'] == 'reserved'
               for f in (book.root/'entries').glob('*.json'))


def test_stale_launch_observation_never_sends_or_reserves(tmp_path, monkeypatch):
    root, p, sent, send, lookup, book = fixture(tmp_path, monkeypatch)
    def admission(m):
        admission.observed_unix = -1000
    result = r.run(root, p, send=send, lookup=lookup, admission=admission)
    assert result['status'] == 'paused'
    assert not sent and book.snapshot()['entries'] == 0


def test_per_setting_controls_cannot_cancel_into_a_replication(monkeypatch):
    F = r.Fraction
    def fake(*args, **kwargs):
        return dict(candidate_screen=dict(selected_case_lead=True, direction='increased_distortion'),
            per_frame=[dict(seed=1, aligned=dict(support_bounds=(F(1,5),)*2),
                conflict=dict(support_bounds=(F(1,4),)*2)),
                dict(seed=2, aligned=dict(support_bounds=(-F(1,5),)*2),
                conflict=dict(support_bounds=(F(1,4),)*2))])
    monkeypatch.setattr(r.science, 'analyze', fake)
    rows=[dict(id=a['id'], terms=(None,None)) for a in r.items()]
    report=r.readout([dict(assignments=rows)])
    assert not report['validation']['positive_discovery_replicated']
    assert not any(v['passed'] for v in report['validation']['per_frame_controls'])


def test_real_budget_private_copy_preserves7391_old_entries_and_holds_every_uncertainty(tmp_path):
    target=tmp_path/'ledger'
    saved=REPO/'paper3/data/pivot_b_graceful_continuation_v1_complete/repo'/r.LEDGER
    shutil.copytree(saved, target)
    shutil.copyfile(REPO/r.LEDGER/budget.EXTENSION_FILE, target/budget.EXTENSION_FILE)
    before={p.name:recovery.digest(p) for p in (target/'entries').glob('*.json')}
    book=budget.ValidationLedger(target)
    initial=book.snapshot()
    assert initial['cap_usd']=='21.31' and initial['entries']==7391
    assert initial['accounted_usd']=='12.225935431'
    assert initial['unspent_active_stage_caps_usd']=='0.29045544'
    assert initial['available_for_new_stages_usd']=='8.793609129'
    caps={'private-validation-0':'4.39519074','private-validation-1':'4.39127514'}
    pins=book.allocate_group('private-validation',caps)['stage_pins']
    book=budget.ValidationLedger(target,stage_pins=pins)
    assert book.snapshot()['available_for_new_stages_usd']=='0.007143249'
    book.reserve('private-validation-0','private-one','0.01','a'*64)
    with pytest.raises(ValueError, match='uncertified reservation'):
        book.settle('private-one','0',False,'b'*64)
    book.settle('private-one','0.01',False,'b'*64)
    with pytest.raises(ValueError, match='existing group/stage'):
        book.allocate_group('private-validation',caps)
    assert before=={n:recovery.digest(target/'entries'/n) for n in before}
    # Neither malformed authority nor mutation of old stage/charge bindings is accepted.
    extension=target/budget.EXTENSION_FILE
    row=recovery.load(extension)
    row['new_total_cap_usd']='100'
    r.atomic(extension,row)
    with pytest.raises(ValueError, match='authority changed'):
        book.snapshot()


def test_no_actual_root_or_model_permission_in_private_checks():
    assert r.authority()['credit_purchase'] is False
