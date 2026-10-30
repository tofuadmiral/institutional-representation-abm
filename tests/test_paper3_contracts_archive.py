"""Post-freeze packaging tests against fabricated complete and failed runs."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from tests.test_paper3_coalition_contracts_runner import setup, fake
from experiments import paper3_coalition_contracts as runner

PATH=Path(__file__).resolve().parents[1]/"analysis/paper3_contracts_archive.py"
SPEC=importlib.util.spec_from_file_location("contracts_archive",PATH)
b=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(b)


def isolated(target,protocol,cwd):
    return subprocess.run([sys.executable,"-I","-S",str(target/"code/analysis/paper3_contracts_archive.py"),
        str(target),"--replay","--expected-protocol",protocol],cwd=cwd,env={},capture_output=True,text=True)


@pytest.mark.parametrize("mode,complete",[("valid",9),("content_invalid",0),("gate_wrong",0),("receipt_missing",0)])
def test_extracted_replay_retains_complete_and_failed_evidence(setup,tmp_path,mode,complete):
    root,ledger=setup;fake(setup,mode)
    expected=runner.audit(root,ledger)
    target=tmp_path/"bundle";meta=b.build(root,ledger,target)
    assert meta["frozen_source_count"]==12
    assert len(meta["post_freeze_tools"])==2
    assert (target/"run/manifest.json").read_bytes()==(root/"manifest.json").read_bytes()
    archive=tmp_path/"evidence.zip";assert len(b.archive(target,archive))==64
    extracted=tmp_path/"elsewhere"/"evidence"
    with zipfile.ZipFile(archive) as z:z.extractall(extracted)
    result=isolated(extracted,meta["protocol"],tmp_path)
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)
    assert report.pop("portable_replay")["exact_report_match"]
    assert report==expected and report["complete_episodes"]==complete
    assert len(report["assignments"])==9 and len(report["contrasts"])==6
    assert not list(extracted.rglob("__pycache__"))
    assert not list(extracted.rglob(".env*"))
    diagnostic=json.loads((extracted/"postfreeze_failure_summary.json").read_text())
    assert diagnostic["post_freeze_diagnostic"]
    if mode=="content_invalid":assert len(diagnostic["failures"])==9
    if mode=="valid":assert diagnostic["failures"]==[]
    with pytest.raises(ValueError,match="archive exists"):b.archive(target,archive)
    with pytest.raises(ValueError,match="destination exists"):b.build(root,ledger,target)
    changed=next((extracted/"run/calls").glob("*.json"))
    changed.write_text(changed.read_text()+"\n")
    bad=isolated(extracted,meta["protocol"],tmp_path)
    assert bad.returncode!=0 and "hash mismatch" in bad.stderr


def test_live_export_refused(setup,tmp_path):
    with pytest.raises(ValueError,match="not terminal"):
        b.build(*setup,tmp_path/"bundle")
    assert not (tmp_path/"bundle").exists()


@pytest.mark.parametrize("name",["../escape","/absolute","code/../../escape","code\\escape"])
def test_unsafe_path(tmp_path,name):
    with pytest.raises(ValueError,match="unsafe"):b.safe(tmp_path,name)


def test_credentials_and_offline_guard():
    with pytest.raises(ValueError,match="credential"):b.credentials(b"fake-secret","fake-secret")
    with pytest.raises(ValueError,match="credential"):b.credentials(b"sk-or-v1-"+b"a"*30)
    with pytest.raises(ValueError,match="credential"):b.credentials(b"Bearer "+b"a"*30)
    for event in ("socket.__new__","urllib.Request","subprocess.Popen","os.system"):
        with pytest.raises(RuntimeError,match="offline replay"):b.offline_guard(event,())


def test_symlink_refused(tmp_path):
    (tmp_path/"link").symlink_to(tmp_path/"destination")
    with pytest.raises(ValueError,match="symlink"):b.safe(tmp_path,"link")
