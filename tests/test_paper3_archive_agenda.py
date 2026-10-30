import fcntl
import hashlib
import json
import zipfile

import pytest

from experiments import paper3_archive_agenda as packaging


@pytest.fixture
def terminal(tmp_path, monkeypatch):
    root = tmp_path / "run"
    (root / "sessions").mkdir(parents=True)
    (root / "calls").mkdir()
    (root / "sessions/terminal.json").write_text('{"completed": true}')
    (root / "sessions/failed.json").write_text('{"status": "failed"}')
    (root / "calls/raw.json").write_text('{"content": "p3"}')
    (root / "manifest.json").write_text('{"protocol": "fixture"}')
    (root / "sources.json").write_text('{"fixture.py": "pass"}')
    (root / "writer.lock").touch()
    report = dict(integrity_errors=[], calls=1, tokenization_checks=1)
    monkeypatch.setattr(packaging, "audited_report", lambda source: report)
    return root, tmp_path / "archive.zip", report


def test_preserves_all_records_and_validates_archive(terminal):
    root, destination, report = terminal
    result = packaging.archive(root, destination)
    assert result["report"] == report
    assert result["sha256"] == hashlib.sha256(destination.read_bytes()).hexdigest()
    with zipfile.ZipFile(destination) as bundle:
        assert bundle.testzip() is None
        assert "writer.lock" not in bundle.namelist()
        assert bundle.read("sessions/failed.json") == (root / "sessions/failed.json").read_bytes()
        assert bundle.read("calls/raw.json") == (root / "calls/raw.json").read_bytes()
        manifest = json.loads(bundle.read("packaging/manifest.json"))
        for name, sha in manifest["files"].items():
            assert hashlib.sha256(bundle.read(name)).hexdigest() == sha
        assert json.loads(bundle.read("audit.json")) == report
    assert not (root / "audit.json").exists()  # No mutation of source run.


def test_refuses_overwrite(terminal):
    root, destination, _ = terminal
    destination.write_bytes(b"existing")
    with pytest.raises(ValueError, match="overwrite"):
        packaging.archive(root, destination)
    assert destination.read_bytes() == b"existing"


def test_refuses_nonterminal_or_live_run(terminal):
    root, destination, _ = terminal
    with (root / "writer.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            packaging.archive(root, destination)
    (root / "sessions/terminal.json").unlink()
    with pytest.raises(ValueError, match="not terminal"):
        packaging.archive(root, destination)
    assert not destination.exists()


def test_refuses_integrity_failure(terminal):
    root, destination, report = terminal
    report["integrity_errors"].append("fixture mismatch")
    with pytest.raises(ValueError, match="audit failed"):
        packaging.archive(root, destination)
    assert not destination.exists()


def test_refuses_symlink_and_existing_inconsistent_audit(terminal):
    root, destination, _ = terminal
    (root / "external").symlink_to(destination.parent)
    with pytest.raises(ValueError, match="symlink"):
        packaging.archive(root, destination)
    (root / "external").unlink()
    (root / "audit.json").write_text("{}")
    with pytest.raises(ValueError, match="audit differs"):
        packaging.archive(root, destination)
    assert not destination.exists()


def test_refuses_destination_inside_run(terminal):
    root, _, _ = terminal
    with pytest.raises(ValueError, match="outside"):
        packaging.archive(root, root / "archive.zip")
