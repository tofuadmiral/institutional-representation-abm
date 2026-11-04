"""Private simulated checks; no provider calls or experimental observations."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from experiments import paper3_office_sacrifice_probe_v1 as w
from paper3 import office_sacrifice_probe_v1 as d
from paper3 import office_sacrifice_budget_v1 as budget
from tests.test_paper3_graceful_continuation import FakeLedger
from tests.test_paper3_retrospective_independent_calls import Clock
from tests.test_paper3_retrospective_deepinfra_core_v1 import evidence
from tests.test_paper3_graceful_recovery import overload_with_id

REPO = Path(__file__).resolve().parents[1]


def test_all_fresh_cases_strict_objective_conflict_same_utilities_and_controls():
    items = d.assignments()
    assert len(items) == 96 and len({a['id'] for a in items}) == 96
    for i in range(d.N):
        main = [d.assignment(i, c) for c in d.CONDITIONS[:4]]
        assert len({a['request']['seed'] for a in main}) == 1
        assert all(a['game'].utilities == main[0]['game'].utilities for a in main)
        for a in main:
            yes, no = a['consequences']['yes'], a['consequences']['no']
            assert sum(yes['votes']) == 4 and sum(no['votes']) == 3
            assert yes['district_sum'] > no['district_sum'] == 0
            assert yes['total_citizen_utility'] > 0 and yes['harms_by_district'][i % 7] == 5
            office_prefers_yes = yes['officeholder_score'] > no['officeholder_score']
            assert office_prefers_yes == (a['condition'] != 'binding_24')
            assert yes['retained'] == a['condition'].startswith('advisory')
        harmful = d.assignment(i, 'harmful')
        assert harmful['consequences']['yes']['district_sum'] < 0
        assert harmful['consequences']['yes']['total_citizen_utility'] < 0
        assert d.assignment(i, 'factual')['expected_mandate_or_fact'] == (i % 2 == 0)


def test_readout_reports_fixed_denominators_controls_and_missing_bounds():
    rows = []
    for a in d.assignments():
        vote = a['expected_mandate_or_fact']
        if a['condition'] == 'binding_24':
            vote = False
        rows.append(dict(id=a['id'], case=a['case'], condition=a['condition'], vote=vote,
                         expected_mandate_or_fact=a['expected_mandate_or_fact']))
    report = d.readout(rows)
    assert report['primary']['complete_case_mean'] == report['interaction']['complete_case_mean'] == '1'
    assert report['primary']['exact_two_sided_sign_p'] == '1/32768'
    assert report['cells']['factual']['mandate_or_fact_correct'] == 16
    for r in rows:
        if r['case'] == 0 and r['condition'] == 'binding_24':
            r['vote'] = None
    report = d.readout(rows)
    assert report['primary']['all_case_lower'] == '15/16'
    assert report['primary']['all_case_upper'] == '1'
    assert report['primary']['assigned_cases'] == 16


def private(tmp_path, monkeypatch):
    root = tmp_path / 'run'
    root.mkdir()
    ledger = tmp_path / 'ledger'
    ledger.mkdir()
    (ledger / 'entries').mkdir()
    w.atomic(ledger / 'authority.json', dict(budget_id='paper3-pivot-b-2026-09-24',
        cap_usd='10.00', credit_purchases_authorized=False))
    book = FakeLedger(ledger)
    protocol = 'e' * 64
    stage = 'office-probe-' + protocol[:16]
    spec = d.specification()
    monkeypatch.setattr(book, '_stage', lambda s: dict(cap_usd=spec['full_reservation_usd']))
    monkeypatch.setattr(book, '_entries', lambda: [w.load(p) for p in (ledger / 'entries').glob('*.json')], raising=False)
    monkeypatch.setattr(w, 'REPO', tmp_path)
    monkeypatch.setattr(w, 'ROOT_NAME', 'run')
    monkeypatch.setattr(w, 'LEDGER', 'ledger')
    monkeypatch.setattr(w, 'verify', lambda *a, **k: dict(specification=spec))
    monkeypatch.setattr(w, 'allocate', lambda *a: (book, stage))
    monkeypatch.setattr(w.budget, 'ProbeLedger', lambda *a, **k: book)
    w.atomic(root / 'allocation.json', dict(protocol=protocol, stage=stage, stage_pins={stage:'a'*64}))
    clock = Clock()
    monkeypatch.setattr(w, 'time', SimpleNamespace(time=clock, sleep=clock.sleep, time_ns=lambda: int(clock()*1e9)))
    sent = []
    by_wire = {w.route.reservation(a['request'])['request_text']: a for a in d.assignments()}
    def send(wire, secret):
        assert secret is None
        sent.append((wire, clock()))
        a = by_wire[wire]
        if len(sent) == 1:
            stream = deepcopy(overload_with_id(a['request'])['stream'])
        else:
            options = dict(raw='not JSON') if len(sent) == 7 else dict(
                value=dict(vote=a['expected_mandate_or_fact']))
            stream = evidence(a['request'], 'gen-private-'+str(len(sent)), **options)['stream']
        stream.update(started_unix=clock(), ended_unix=clock())
        return stream
    def lookup(identifier, secret):
        if identifier == 'gen-fabricated-overload':
            return dict(http_status=404, error_type='HTTPError', data=None, secret_redacted=False)
        return dict(http_status=200, error_type=None, secret_redacted=False,
            data=dict(id=identifier, model=w.route.MODEL_ALIAS, provider_name=w.route.PROVIDER,
                      total_cost=.0001))
    def admit(root, protocol, book, stage, secret):
        old = w.load(REPO / 'results/paper3/pivot_b_independent_validation_v1/admissions/1793205286757644000.json')
        w.atomic(root / 'admissions' / (str(clock())+'.json'), dict(
            metadata_observed_unix=clock(), protocol=protocol, metadata=old['metadata'],
            account=dict(account_funded=True, research_authority_extended=False)))
        return clock()
    return root, protocol, sent, send, lookup, book, admit


def test_entire96_action_private_run_recovers_crash_without_resend_and_audits(tmp_path, monkeypatch):
    root, protocol, sent, send, lookup, book, admit = private(tmp_path, monkeypatch)
    original = w.check_record
    crashed = False
    def crash_after_durable_response(*args, **kwargs):
        nonlocal crashed
        original(*args, **kwargs)
        if len(sent) == 2 and not crashed:
            crashed = True
            raise KeyboardInterrupt()
    monkeypatch.setattr(w, 'check_record', crash_after_durable_response)
    with pytest.raises(KeyboardInterrupt):
        w.run(protocol, send=send, lookup=lookup, admit=admit)
    assert len(sent) == 2 and not list((root / 'invocations').glob('*terminal*'))
    raw_before = {p:p.read_bytes() for p in (root / 'calls').glob('*.json')}
    monkeypatch.setattr(w, 'check_record', original)
    assert w.run(protocol, send=send, lookup=lookup, admit=admit)['status'] == 'complete'
    assert len(sent) == 97 and sent[0][0] == sent[1][0] and sent[1][1] - sent[0][1] >= 300
    assert all(p.read_bytes() == b for p,b in raw_before.items())
    result = w.audit(protocol)
    assert result['entire_report_matched'] and result['entire_ledger_matched']
    assert len(sent) == 97 and result['logical'] == 96 and result['physical'] == 97
    report = w.load(root / 'report.json')
    assert sum(r['status'] == 'content_failed' for r in report['assignments']) == 1
    assert sum(c['missing'] for c in report['cells'].values()) == 1


def test_new_budget_adapter_private_real_history_preserves_old_uncertainty(tmp_path):
    target = tmp_path / 'ledger'
    shutil.copytree(REPO / w.LEDGER, target)
    before = {p.name:p.read_bytes() for p in (target / 'entries').glob('*.json')}
    book = budget.ProbeLedger(target)
    baseline = book.snapshot()
    assert baseline['cap_usd'] == '21.31'
    pins = book.allocate_group('private-office-group', {'private-office-stage':'.02'})['stage_pins']
    book = budget.ProbeLedger(target, stage_pins=pins)
    assert Decimal(book.snapshot()['available_for_new_stages_usd']) == Decimal(baseline['available_for_new_stages_usd']) - Decimal('.02')
    book.reserve('private-office-stage', 'private-office-call', '.01', 'a'*64)
    book.settle('private-office-call', '.01', False, 'b'*64)
    book.close('private-office-stage', 'c'*64)
    after = book.snapshot()
    assert Decimal(after['accounted_usd']) == Decimal(baseline['accounted_usd']) + Decimal('.01')
    assert after['pending'] == baseline['pending'] and after['uncertified'] == baseline['uncertified'] + 1
    assert after['unspent_active_stage_caps_usd'] == baseline['unspent_active_stage_caps_usd']
    assert all((target / 'entries' / name).read_bytes() == b for name,b in before.items())
