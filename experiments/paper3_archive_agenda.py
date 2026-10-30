"""Audit and archive a terminal agenda pilot, without inference or action repair.

This post-run utility is outside the frozen experiment. The frozen specialized
auditor remains unchanged. Its namespace import avoids unrelated plotting imports
in analysis/__init__.py in the deliberately minimal inference environment.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib
import json
from pathlib import Path
import sys
import types
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def audited_report(source):
    if "analysis" not in sys.modules:
        namespace = types.ModuleType("analysis")
        namespace.__path__ = [str(ROOT / "analysis")]
        sys.modules["analysis"] = namespace
    auditor = importlib.import_module("analysis.paper3_agenda_audit")
    return auditor.audit(source, check_tokenization=True)


def archive(source: Path, destination: Path, report_fn=None):
    source, destination = source.resolve(), destination.resolve()
    if destination.exists():
        raise ValueError("refusing to overwrite an existing archive")
    if source == destination or source in destination.parents:
        raise ValueError("archive destination must be outside the run directory")
    if not (source / "sessions/terminal.json").is_file():
        raise ValueError("pilot is not terminal")
    # The inference worker holds this lock for its lifetime. Do not archive
    # between its last session write and actual exit, or race a new writer.
    with (source / "writer.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = (audited_report if report_fn is None else report_fn)(source)
        if report["integrity_errors"]:
            raise ValueError("specialized audit failed: " + repr(report["integrity_errors"]))
        audit_bytes = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        payload = {}
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ValueError("symlink in pilot output: " + str(path))
            if not path.is_file():
                continue
            name = path.relative_to(source).as_posix()
            if name == "writer.lock":
                continue  # Process-coordination file, not an experimental record.
            if name == "audit.json":
                if json.loads(path.read_text()) != report:
                    raise ValueError("existing audit differs; no overwrite")
                continue
            payload[name] = path.read_bytes()
        payload["audit.json"] = audit_bytes
        # Include the post-run packager itself without misrepresenting it as
        # part of the experiment's earlier protocol/source freeze.
        packager = Path(__file__).read_bytes()
        payload["packaging/source.py"] = packager
        payload["packaging/manifest.json"] = (json.dumps(dict(
            role="post-run packaging only; not part of the frozen experiment",
            packager_sha256=hashlib.sha256(packager).hexdigest(),
            files={name: hashlib.sha256(data).hexdigest() for name, data in payload.items()},
            excluded="writer.lock: process coordination only",
        ), indent=2, sort_keys=True) + "\n").encode()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, data in sorted(payload.items()):
                bundle.writestr(name, data)
        with zipfile.ZipFile(destination) as bundle:
            if bundle.testzip() is not None or set(bundle.namelist()) != set(payload):
                raise ValueError("archive integrity or membership mismatch")
            for name, data in payload.items():
                if bundle.read(name) != data:
                    raise ValueError("archive byte mismatch: " + name)
        return dict(path=str(destination), sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                    calls=report["calls"], report=report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(archive(args.source, args.destination), indent=2))
