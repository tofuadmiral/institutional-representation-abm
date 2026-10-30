"""Post-freeze packaging tests only; no model calls or experimental data writes."""
import json
import importlib.util
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

_source = Path(__file__).resolve().parents[1]/'analysis/paper3_validation_archive_v1.py'
_spec = importlib.util.spec_from_file_location('_validation_packaging_tests', _source)
archive = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(archive)


def test_portable_paths_and_credentials(tmp_path):
    h = archive.helper(Path(__file__).resolve().parents[1])
    assert h.safe(tmp_path, 'repo/a.json') == tmp_path/'repo/a.json'
    for bad in ('../a', '/a', 'repo/../../a', 'repo\\a'):
        with pytest.raises(ValueError):
            h.safe(tmp_path, bad)
    secret = 'private-current-key-test-value'
    with pytest.raises(ValueError):
        h.credentials(secret.encode(), secret)
    with pytest.raises(ValueError):
        h.credentials(b'Bearer '+b'x'*40)


def test_guard_blocks_network_and_process_events():
    h = archive.helper(Path(__file__).resolve().parents[1])
    for event in ('socket.connect', 'urllib.Request', 'subprocess.Popen',
                  'os.system', 'os.exec', 'os.posix_spawn'):
        with pytest.raises(RuntimeError, match='forbids network and child processes'):
            h.offline_guard(event, ())
    h.offline_guard('open', ())


def test_snapshot_does_not_nest_locks():
    class Book:
        def _entries(self):
            return [dict(status='settled', certified=True),
                    dict(status='reserved', certified=False)]

        def _total(self, rows):
            return 3

        def _commitments(self, rows):
            return 4

        def snapshot(self):
            raise AssertionError('must not nest ledger lock')

    r = SimpleNamespace(old=SimpleNamespace(budget=SimpleNamespace(
        previous=SimpleNamespace(BUDGET_ID='private'), TOTAL_CAP=10, EXTENSION_SHA='pin')))
    snapshot = archive.budget_snapshot(r, Book())
    assert snapshot['accounted_usd']=='3'
    assert snapshot['available_for_new_stages_usd']=='3'
    assert snapshot['pending']==snapshot['uncertified']==1


def test_replay_requires_actual_isolated_interpreter():
    with pytest.raises(ValueError, match='actual fresh Python -I -S required'):
        archive.replay('private-fixture')


def test_genuine_wrapper_codec_is_decoded_before_comparison():
    from paper3 import retrospective_episode_journal as journal
    r = SimpleNamespace(old=SimpleNamespace(journal=journal))
    payload = dict(entire_report_matched=True,
        analysis=dict(minimum_effect=Fraction(1, 25)),
        controls=(dict(bounds=(Fraction(0), Fraction(1, 2))),))
    output = json.dumps(journal.encode(payload))
    assert archive.audit_result(r, output)==dict(entire_report_matched=True,
        analysis=dict(minimum_effect='1/25'), controls=[dict(bounds=['0', '1/2'])])


def test_finite_window_selection_and_rejection(tmp_path):
    # A private minimal fixture, never real saved evidence or readiness.
    root = tmp_path/'run'
    meta = root/'reasoning_timeout_amendment_v1'
    meta.mkdir(parents=True)
    amendment = {'prior_files': {'run/block-0/calls/old.json': 'private'}}
    def canonical(value):
        return json.dumps(value, sort_keys=True)
    protocol = archive.hashlib.sha256(canonical(amendment).encode()).hexdigest()
    records = {}
    for index in range(2):
        directory = root/f'block-{index}'/'calls'
        directory.mkdir(parents=True)
        records[root/f'block-{index}'/'admission.json'] = dict(
            started_unix=0, deadline_unix=86400)
    records[meta/'remaining_frame0_admission.json'] = dict(
        amendment_protocol=protocol, started_unix=90000, deadline_unix=176400)
    for name, admitted in (('old', 3), ('new', 90001)):
        path = root/'block-0/calls'/(name+'.json')
        path.touch()
        records[path] = dict(admitted_unix=admitted)

    def require(ok, message):
        if not ok:
            raise ValueError(message)

    r = SimpleNamespace(ROOT=root, META=meta, REPO=tmp_path,
        old=SimpleNamespace(journal=SimpleNamespace(canonical=canonical)),
        load=lambda path:records[path], require=require)
    assert archive.timing_check(r, amendment)['physical_by_frame']==[2, 0]
    records[root/'block-0/calls/new.json']['admitted_unix'] = 176400
    with pytest.raises(ValueError, match='outside'):
        archive.timing_check(r, amendment)
