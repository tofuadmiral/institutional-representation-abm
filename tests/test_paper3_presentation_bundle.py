"""Fabricated offline evidence only; no provider calls or real API key."""
import json
import subprocess
import sys
import time
import zipfile

import pytest

from analysis import paper3_presentation_bundle as bundle
from analysis import paper3_presentation_portable_replay as replay
from analysis import paper3_disclosure_presentation_audit as reporting
from tests.test_paper3_disclosure_presentation import completed, fake, receipt, SECRET
from tests.test_paper3_deepseek_disclosure_a3 import ok, stream, reset
from experiments import paper3_disclosure_presentation as run


def outside_replay(target, protocol, cwd):
    return subprocess.run([sys.executable,'-I','-S',str(target/'replay.py'),
                           '--expected-protocol',protocol],cwd=cwd,env={},
                          capture_output=True,text=True,check=False)


def test_complete_archive_replays_after_extraction_without_site_packages(completed,tmp_path):
    target=tmp_path/'export'
    metadata=bundle.build(completed,target)
    assert metadata['post_freeze_tools']==['replay.py','tools/paper3_presentation_bundle.py',
                                           'tools/test_paper3_presentation_bundle.py']
    assert (target/'code/analysis/__init__.py').is_file()
    assert (target/'run/manifest.json').read_bytes()==(completed/'manifest.json').read_bytes()
    frozen=run.load(completed/'sources.json')
    assert {str(p.relative_to(target/'code')) for p in (target/'code').rglob('*') if p.is_file()}==set(frozen)
    archive=tmp_path/'evidence.zip'
    sha=bundle.archive(target,archive)
    assert len(sha)==64
    with pytest.raises(ValueError,match='archive exists'):
        bundle.archive(target,archive)
    with pytest.raises(ValueError,match='destination exists'):
        bundle.build(completed,target)
    relocated=tmp_path/'different-place'/'evidence'
    with zipfile.ZipFile(archive) as z:z.extractall(relocated)
    result=outside_replay(relocated,metadata['coordinator_protocol'],tmp_path)
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)
    assert report['integrity_errors']==[] and report['calls']==736
    assert report['complete_blocks']==8 and report['base_profiles']==1
    original=reporting.audit(completed)
    assert {k:v for k,v in report.items() if k!='portable_replay'}==original
    assert len(report['presentation_diagnostic']['pairs'])==4
    assert report['presentation_diagnostic']['all_assigned_complete_and_clean']
    assert report['presentation_diagnostic']['interpretation'].startswith('original_not_stable')
    assert all(f['benchmark_reproducing_blocks']==0
               for f in report['presentation_diagnostic']['forms'].values())
    assert len(list((relocated/'run/gate/calls').glob('*.json')))==8
    assert not (relocated/'code/results/paper3/deepseek_identification_v1/gate').exists()
    assert not list(relocated.rglob('__pycache__'))
    assert not list((relocated/'code').rglob('.env*'))
    with pytest.raises(ValueError,match='unexpected coordinator'):
        replay.verify_inventory(relocated,'wrong')
    altered=next((relocated/'run/gate/calls').glob('*.json'))
    altered.write_text(altered.read_text()+'\n# changed\n')
    bad=outside_replay(relocated,metadata['coordinator_protocol'],tmp_path)
    assert bad.returncode!=0 and 'hash mismatch' in bad.stderr


def test_failed_terminal_run_replays_with_missing_bounds(tmp_path):
    root=tmp_path/'run';parent=run.freeze(root)
    (root/'network_preflight.json').write_text(json.dumps(dict(passed=True,finished_unix=time.time(),test=True)))
    def gate(root,secret):
        return run.run_gate(root,secret,transport=fake,generation=receipt)
    def worker(root,index):
        # A fabricated uncertain transport failure creates the normal shared stop.
        run.run_shard(root,index,SECRET,transport=lambda *args:reset(),generation=lambda *args:None)
        return dict(returncode=0)
    run.execute(parent,SECRET,gate_runner=gate,run_worker=worker)
    parent.lock.close()
    metadata=bundle.build(root,tmp_path/'bundle')
    result=outside_replay(tmp_path/'bundle',metadata['coordinator_protocol'],tmp_path)
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)
    assert report['integrity_errors']==[] and report['complete_blocks']==0
    assert len(report['profiles'])==8
    assert all(r['information_benefit_bounds_exact']==['-1','1'] for r in report['profiles'])
    assert report['usage']['outcomes']['uncertified']>=1
    assert report['usage']['attempts_with_unknown_tokens']['prompt_tokens']>=1
    assert len(report['presentation_diagnostic']['pairs'])==4
    assert report['presentation_diagnostic']['mean_paired_difference_bounds_exact']==['-2','2']
    assert report['presentation_diagnostic']['interpretation'].startswith('incomplete_or_integrity')
    assert {k:v for k,v in report.items() if k!='portable_replay'}==reporting.audit(root)


def test_export_refuses_live_run_and_preserves_existing_files(tmp_path):
    with pytest.raises(ValueError,match='not terminal'):
        bundle.build(tmp_path,tmp_path/'export')
    assert not (tmp_path/'export').exists()


def test_failed_fresh_gate_exports_without_admitting_institutional_calls(tmp_path):
    root=tmp_path/'run';parent=run.freeze(root)
    (root/'network_preflight.json').write_text(json.dumps(dict(passed=True,finished_unix=time.time(),test=True)))
    def gate(root,secret):
        return run.run_gate(root,secret,transport=lambda *args:ok(stream('{}')),generation=receipt)
    run.execute(parent,SECRET,gate_runner=gate,
                run_worker=lambda *args:pytest.fail('failed gate admitted institutional worker'))
    parent.lock.close()
    metadata=bundle.build(root,tmp_path/'bundle')
    result=outside_replay(tmp_path/'bundle',metadata['coordinator_protocol'],tmp_path)
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)
    assert report['integrity_errors']==[] and report['calls']==8 and report['complete_blocks']==0
    assert len(report['profiles'])==8 and len(report['presentation_diagnostic']['pairs'])==4
    assert report['presentation_diagnostic']['mean_paired_difference_bounds_exact']==['-2','2']
    assert {k:v for k,v in report.items() if k!='portable_replay'}==reporting.audit(root)


def test_partial_write_prevents_export_before_audit(tmp_path):
    root=tmp_path/'run';(root/'sessions').mkdir(parents=True)
    (root/'sessions/terminal.json').write_text('{}')
    (root/'pending.partial').write_text('unfinished')
    with pytest.raises(ValueError,match='partial writes'):
        bundle.build(root,tmp_path/'export')
    assert not (tmp_path/'export').exists()


def test_failed_integrity_cannot_be_archived(completed,tmp_path):
    path=completed/'profile-0/sessions/early-D.json'
    data=run.load(path);data['actions'][0]['action']['message']='changed'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='integrity audit failed'):
        bundle.build(completed,tmp_path/'export')
    assert not (tmp_path/'export').exists()


@pytest.mark.parametrize('path',['../outside','/absolute','code/../../outside','code\\evil'])
def test_unsafe_paths_rejected(tmp_path,path):
    with pytest.raises(ValueError,match='unsafe'):
        replay.safe_path(tmp_path,path)


def test_symlinks_rejected(tmp_path):
    (tmp_path/'link').symlink_to(tmp_path/'outside')
    with pytest.raises(ValueError,match='symlink'):
        replay.safe_path(tmp_path,'link')


def test_secret_scan_and_offline_guard():
    with pytest.raises(ValueError,match='credential found'):
        bundle.check_credentials(b'fixture private-string','private-string')
    with pytest.raises(ValueError,match='possible API credential'):
        bundle.check_credentials(b'sk-or-v1-'+b'x'*30)
    with pytest.raises(ValueError,match='possible bearer credential'):
        bundle.check_credentials(b'Bearer '+b'a'*30)
    bundle.check_credentials(b'OPENROUTER_API_KEY variable name is not a key')
    with pytest.raises(RuntimeError,match='offline replay'):
        replay.forbid_network_and_processes('socket.__new__',())
    with pytest.raises(RuntimeError,match='offline replay'):
        replay.forbid_network_and_processes('subprocess.Popen',())
    replay.forbid_network_and_processes('open',())


def test_null_usage_is_unknown_not_zero_and_zero_is_retained():
    rows=[dict(response=None),dict(response=dict(usage=None)),dict(response=dict(usage={
        'prompt_tokens':3,'completion_tokens':0,'completion_tokens_details':None})),
          dict(response=dict(usage={'prompt_tokens':False,'completion_tokens':'10',
                                   'completion_tokens_details':dict(reasoning_tokens=0)}))]
    result=reporting.usage_summary(rows)
    assert result['known_token_totals']==dict(prompt_tokens=3,completion_tokens=0,reasoning_tokens=0)
    assert result['attempts_with_unknown_tokens']==dict(prompt_tokens=3,completion_tokens=3,reasoning_tokens=3)
