"""Read-only old evidence + fresh extracted isolated retirement replay, no API.

This checks the new export component's nested ORIGINAL evidence, not a complete
new-study export or operating readiness. All temporary mutations are private.
"""
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from paper3 import retrospective_recovery_archive_v2 as archive

REPO = Path(__file__).resolve().parents[1]
RETIRED = REPO / "paper3/data/pivot_b_retrospective_anticipation_v1_batch0"
ZIPPED = RETIRED.with_suffix(".zip")


def test_entire_original_bundle_matches_original_zip_and_report():
    metadata = archive._retirement_bundle(RETIRED, ZIPPED)
    assert metadata["report_sha256"] == archive.retirement.REPORT_SHA
    assert metadata["protocol"] == archive.retirement.PROTOCOL
    assert len(metadata["files"]) > 13000


def test_changed_zip_cannot_supply_a_retirement_or_new_spending(tmp_path):
    path = tmp_path / "wrong.zip"
    path.write_bytes(b"not the pinned archive")
    with pytest.raises(ValueError, match="retirement ZIP"):
        archive._retirement_bundle(RETIRED, path)


def test_actual_fresh_extracted_original_report_reproduces_under_new_nested_replay(tmp_path):
    extracted = tmp_path / "retired"
    extracted.mkdir()
    with zipfile.ZipFile(ZIPPED) as zipped:
        # Original pinned ZIP's inventory/path checks precede extraction.
        archive._retirement_bundle(RETIRED, ZIPPED)
        for name in zipped.namelist():
            target = archive.portable.safe(extracted, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zipped.read(name))
    script = """
import importlib.util, json, pathlib, sys
sys.dont_write_bytecode = True
repo = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(repo))
spec = importlib.util.spec_from_file_location('_isolated_guard', repo / 'analysis/paper3_contracts_archive.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
sys.addaudithook(guard.offline_guard)
import socket, subprocess
for operation in (lambda: socket.getaddrinfo('127.0.0.1',1), lambda: subprocess.run([sys.executable,'-c','pass'])):
    try:
        operation()
    except RuntimeError as exc:
        assert str(exc) == 'offline replay forbids network and child processes'
    else:
        raise ValueError('guard did not reject operation')
from paper3 import retrospective_recovery_archive_v2 as archive
certificate = archive._replay_retirement(pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]))
print(json.dumps(certificate,sort_keys=True))
"""
    result = subprocess.run([sys.executable, "-I", "-S", "-c", script, str(REPO), str(extracted), str(ZIPPED)],
        cwd=tmp_path, capture_output=True, text=True, timeout=600, check=True)
    certificate = json.loads(result.stdout)
    assert certificate["isolated_report_matched"] and certificate["genuine_qualification_reproduced"]
    assert certificate["report_sha256"] == archive.retirement.REPORT_SHA
    archive.portable.verify_bundle(extracted, archive.retirement.PROTOCOL)
