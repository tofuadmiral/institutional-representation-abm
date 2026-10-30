"""Offline packaging and relocation tests; fabricated data, no credentials/API."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

from analysis import paper3_validation_bundle as bundle
from analysis import paper3_portable_replay as replay
from tests.test_paper3_disclosure_validation import completed


def test_complete_bundle_replays_outside_checkout_without_site_packages(completed, tmp_path):
    target = tmp_path/'export'
    metadata = bundle.build(completed, target)
    assert len(metadata['supplemental_dependencies']) > 0
    assert all(x['captured_after_freeze'] for x in metadata['supplemental_dependencies'].values())
    assert (target/'run/manifest.json').read_bytes() == (completed/'manifest.json').read_bytes()
    assert not (target/'code/analysis/__init__.py').exists()
    assert 'namespace' in metadata['adapter']
    relocated = tmp_path/'unrelated-place'/'bundle'
    relocated.parent.mkdir()
    shutil.move(str(target), relocated)
    command = [sys.executable, '-I', '-S', str(relocated/'replay.py'),
               '--expected-protocol', metadata['coordinator_protocol']]
    result = subprocess.run(command, cwd=tmp_path, env={}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['integrity_errors'] == []
    assert report['complete_profiles'] == 12 and report['calls'] == 1100
    assert not list(relocated.rglob('__pycache__'))
    with pytest.raises(ValueError, match='unexpected coordinator'):
        replay.verify_inventory(relocated, 'wrong-hash')
    altered = relocated/'code/paper3/agenda_rights.py'
    altered.write_text(altered.read_text()+'\n# changed\n')
    result = subprocess.run(command, cwd=tmp_path, env={}, capture_output=True, text=True)
    assert result.returncode != 0 and 'hash mismatch' in result.stderr


def test_refuses_live_bundle(tmp_path):
    with pytest.raises(ValueError, match='not terminal'):
        bundle.build(tmp_path, tmp_path/'output')
    assert not (tmp_path/'output').exists()


@pytest.mark.parametrize('path', ['../outside', '/absolute', 'code/../../outside', 'code\\evil'])
def test_unsafe_paths_rejected(tmp_path, path):
    with pytest.raises(ValueError, match='unsafe'):
        replay.safe_path(tmp_path, path)


def test_secret_scan_no_key_is_printed():
    with pytest.raises(ValueError, match='credential found'):
        bundle.check_credentials(b'fixture private-string', 'private-string')
    with pytest.raises(ValueError, match='possible API credential'):
        bundle.check_credentials(b'sk-or-v1-'+b'x'*30)
    bundle.check_credentials(b'OPENROUTER_API_KEY is an environment variable name')


def test_offline_guard():
    with pytest.raises(RuntimeError, match='offline replay'):
        replay.forbid_network_and_processes('socket.__new__', ())
    replay.forbid_network_and_processes('open', ())


def test_symlink_rejected(tmp_path):
    (tmp_path/'pointer').symlink_to(tmp_path/'outside')
    with pytest.raises(ValueError, match='symlink'):
        replay.safe_path(tmp_path, 'pointer')
