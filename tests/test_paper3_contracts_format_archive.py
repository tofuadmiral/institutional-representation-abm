"""Post-freeze relocation checks, never pre-inference validation."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
from tests.test_paper3_contracts_format import prepared, fabricated

spec=importlib.util.spec_from_file_location("format_archive",Path(__file__).resolve().parents[1]/"analysis/paper3_contracts_format_archive.py")
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


@pytest.mark.parametrize("mode",["valid","bad_plain","transport","missing_receipt","exception"])
def test_actual_zip_relocation_preserves_report(prepared,tmp_path,mode):
    fabricated(prepared,mode)
    target=tmp_path/"portable";m=a.build(*prepared,target)
    archive=tmp_path/"archive.zip";a.helpers().archive(target,archive)
    fresh=tmp_path/"extracted"
    with zipfile.ZipFile(archive) as z:z.extractall(fresh)
    result=subprocess.run([sys.executable,"-I","-S","code/analysis/paper3_contracts_format_archive.py",".",
        "--replay","--expected-protocol",m["protocol"]],cwd=fresh,env={},capture_output=True,text=True,check=True)
    report=json.loads(result.stdout)
    assert report.pop("portable_replay")["exact_report_match"]
    assert report==json.loads((fresh/"expected_report.json").read_text())
    assert len(report["assignments"])==16
    assert not list(fresh.rglob("*.pyc")) and not list(fresh.rglob(".env*"))
    with pytest.raises(ValueError,match="exists"):a.build(*prepared,target)
    with pytest.raises(ValueError,match="exists"):a.helpers().archive(target,archive)


def test_live_export_refused(prepared,tmp_path):
    with pytest.raises(ValueError,match="terminal"):a.build(*prepared,tmp_path/"portable")
