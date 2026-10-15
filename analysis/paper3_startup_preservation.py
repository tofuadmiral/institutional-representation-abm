"""Integrity-only preservation of a zero-call startup interruption.

Not a terminal controller audit, institutional replay or scientific result.
Uses only the standard library; --verify works under Python -I -S offline.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(root):
    root = Path(root)
    inventory = json.loads((root / "inventory.json").read_text())
    actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()} - {"inventory.json"}
    assert actual == set(inventory), "payload inventory mismatch"
    for name, expected in inventory.items():
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        assert digest((root / name).read_bytes()) == expected, "payload changed: " + name
    manifest = json.loads((root / "run/manifest.json").read_text())
    sources = json.loads((root / "run/sources.json").read_text())
    assert set(sources) == set(manifest["sources"])
    for name, expected in manifest["sources"].items():
        assert digest(sources[name].encode()) == expected == digest((root / "code" / name).read_bytes())
    diagnostic = json.loads((root / "diagnostic.json").read_text())
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert digest(canonical.encode()) == diagnostic["protocol"], "protocol mismatch"
    start = root / "run/batches/batch-0/sessions/start.json"
    assert start.is_file() and not (start.parent / "terminal.json").exists()
    for batch in (0, 1):
        for kind in ("calls", "decisions", "logicals", "attempts", "recoveries", "episodes"):
            assert not list((root / f"run/batches/batch-{batch}" / kind).glob("*.json"))
    entries = {p.name: p for p in (root / "ledger/entries").glob("*.json")}
    assert set(entries) == set(manifest["protocol"]["prior_ledger_entries"])
    for name, expected in manifest["protocol"]["prior_ledger_entries"].items():
        assert digest(entries[name].read_bytes()) == expected
    rows = [json.loads(p.read_text()) for p in entries.values()]
    amount = sum((Decimal(r["accounted_usd"] if r["status"] == "settled" else r["reserved_usd"])
                  for r in rows), Decimal(0))
    assert amount == Decimal(diagnostic["budget"]["accounted_usd"])
    assert len(rows) == diagnostic["budget"]["entries"]
    assert sum(r["status"] != "settled" for r in rows) == diagnostic["budget"]["pending"]
    assert sum(r.get("certified") is False for r in rows) == diagnostic["budget"]["uncertified"]
    return dict(integrity_verified=True, payloads=len(inventory), frozen_sources=len(sources),
                protocol=diagnostic["protocol"], model_calls=0, accounted_usd=str(amount),
                full_controller_replay=False, publication_evidence=False,
                limitation="Preserved zero-call startup state; runtime cause is declared from observed traceback, not rerun. No terminal controller or institutional evidence.")


def export(repo, run, ledger, diagnostic, target, archive, secret=None):
    repo, run, ledger, diagnostic, target, archive = map(Path, (repo, run, ledger, diagnostic, target, archive))
    assert not target.exists() and not archive.exists(), "never overwrite preserved evidence"
    target.mkdir(parents=True)
    shutil.copytree(run, target / "run")
    shutil.copytree(ledger, target / "ledger")
    shutil.copyfile(diagnostic, target / "diagnostic.json")
    sources = json.loads((run / "sources.json").read_text())
    for name, content in sources.items():
        path = target / "code" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    shutil.copyfile(Path(__file__), target / "verify_startup.py")
    payloads = [p for p in target.rglob("*") if p.is_file()]
    pattern = re.compile(rb"sk-or-v1-[A-Za-z0-9_-]{20,}|Bearer [A-Za-z0-9_-]{20,}")
    assert all(not pattern.search(p.read_bytes()) for p in payloads), "credential scan failed"
    if secret:
        assert all(secret.encode() not in p.read_bytes() for p in payloads), "credential scan failed"
    inventory = {str(p.relative_to(target)): digest(p.read_bytes()) for p in payloads}
    (target / "inventory.json").write_text(json.dumps(inventory, sort_keys=True, indent=2) + "\n")
    report = verify(target)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(target.rglob("*")):
            if p.is_file():
                z.write(p, str(p.relative_to(target)))
    return dict(**report, archive_sha256=digest(archive.read_bytes()), credential_scan_passed=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.root), sort_keys=True))
