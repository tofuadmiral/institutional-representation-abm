"""Package completed pilot records and their exact source snapshots for inspection."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
from paper3_pilot_audit import audit


def archive(source: Path, destination: Path, expected_sessions: int):
    report = audit(source)
    if report["sessions"] != expected_sessions or report["missing_referenced_calls"]:
        raise ValueError("incomplete pilot or missing request records")
    manifest = json.loads((source / "manifest.json").read_text())
    snapshot_path = source / "sources.json"
    if snapshot_path.exists():
        snapshots = json.loads(snapshot_path.read_text())
    else:
        snapshots = {}
        for path, expected in manifest["sources"].items():
            actual = Path(path).read_text()
            if hashlib.sha256(actual.encode()).hexdigest() != expected:
                raise ValueError(f"cannot recover exact source: {path}")
            snapshots[str(Path(path).relative_to(ROOT))] = actual
    for path, expected in manifest["sources"].items():
        key = str(Path(path).relative_to(ROOT))
        if hashlib.sha256(snapshots[key].encode()).hexdigest() != expected:
            raise ValueError(f"source snapshot mismatch: {path}")
    if destination.exists():
        raise ValueError("refusing to overwrite an existing archive")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("audit.json", json.dumps(report, indent=2, sort_keys=True))
        bundle.writestr("sources.json", json.dumps(snapshots, indent=2, sort_keys=True))
        bundle.write(source / "manifest.json", "manifest.json")
        for folder in ("calls", "sessions"):
            for path in sorted((source / folder).glob("*.json")):
                bundle.write(path, str(path.relative_to(source)))
    with zipfile.ZipFile(destination) as bundle:
        if bundle.testzip() is not None:
            raise ValueError("archive integrity check failed")
    print(json.dumps(dict(path=str(destination), sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                          calls=report["recorded_calls"], sessions=report["sessions"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--expected-sessions", type=int, required=True)
    args = parser.parse_args()
    archive(args.source, args.destination, args.expected_sessions)
