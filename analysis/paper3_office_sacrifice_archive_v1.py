"""Separate offline closeout/export tool; never edits frozen experiment sources.

Requires the actual full audit and completed worker before any stage closure or
export. Cold replay runs the bundled production audit CLI under Python -I -S.
"""
import argparse
import contextlib
import fcntl
import importlib.util
import io
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import zipfile

ENTRY = "tools/paper3_office_sacrifice_archive_v1.py"
WRAPPER = "experiments/paper3_office_sacrifice_probe_v1.py"
AUDIT = "results/paper3/office_sacrifice_final_audit_2026_11_04.json"
CLOSEOUT = "results/paper3/office_sacrifice_stage_closeout_2026_11_04.json"
CHECKS = "results/paper3/office_sacrifice_archive_checks_2026_11_04.json"
FAMILY = "paper3-controlled-office-sacrifice-complete-v1"


def helper(repo):
    spec = importlib.util.spec_from_file_location(
        "_office_archive_safety", Path(repo) / "analysis/paper3_contracts_archive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def runner():
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    from experiments import paper3_office_sacrifice_probe_v1 as r
    return r


def completed(r, protocol):
    root = r.REPO / r.ROOT_NAME
    manifest = r.verify(protocol, full=True)
    starts = sorted((root / "invocations").glob("*-start.json"))
    r.require(bool(starts), "saved original invocation required")
    terminal = r.load(starts[-1].with_name(starts[-1].name.replace("start", "terminal")))
    sha = r.digest(root / "report.json")
    r.require(terminal["status"] == "complete" and terminal["report_sha256"] == sha,
              "actual completed worker/report required")
    record = r.load(r.REPO / AUDIT)
    r.require(record["exit_code"] == 0 and record["protocol"] == protocol and
        record["report_sha256"] == sha and record["result"]["entire_report_matched"] and
        record["result"]["entire_ledger_matched"] and
        record["result"]["report_sha256"] == sha and
        json.loads(record["stdout"]) == record["result"] and not record["stderr"].strip() and
        record["argv"] == [".venv/bin/python", "-B", WRAPPER, "--audit", "--expected-protocol", protocol],
        "genuine exact production CLI audit required")
    allocation = r.load(root / "allocation.json")
    r.require(allocation["protocol"] == protocol and allocation["stage"] == "office-probe-" + protocol[:16],
              "only this new study's pinned stage")
    book = r.budget.ProbeLedger(r.REPO / r.LEDGER, stage_pins=allocation["stage_pins"])
    report = r.load(root / "report.json")
    r.require(r.history() == report["ledger_hashes"] and
        r.accounting(book, allocation["stage"]) == report["accounting"] == record["result"]["accounting"],
        "audit-time ledger entries unchanged")
    return root, manifest, allocation, book, report, sha


def close_stage(protocol):
    r = runner()
    root = r.REPO / r.ROOT_NAME
    with (root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root, manifest, allocation, book, report, sha = completed(r, protocol)
        target = r.REPO / CLOSEOUT
        r.require(not target.exists(), "closeout already recorded; never overwrite")
        before = book.snapshot()
        stage = allocation["stage"]
        path = book.root / r.budget.CLOSURES / (stage + ".json")
        if path.exists():
            closure = r.load(path)
            r.require(closure["terminal_evidence_sha256"] == sha and
                closure["stage_sha256"] == allocation["stage_pins"][stage], "exact interrupted closure")
            recovered = True
        else:
            closure = book.close(stage, sha)
            recovered = False
        after = book.snapshot()
        r.require(r.history() == report["ledger_hashes"] and
            before["accounted_usd"] == after["accounted_usd"] and
            before["pending"] == after["pending"] and before["uncertified"] == after["uncertified"],
            "no incurred uncertainty or charge may be released")
        record = dict(protocol=protocol, report_sha256=sha, before=before, after=after,
            stage_closure=closure, recovered_saved_closure=recovered,
            all_entry_hashes_unchanged=True, accounting=report["accounting"],
            only_unused_current_stage_closed=True)
        r.atomic(target, record)
        return record


def build(target, archive, protocol):
    r = runner()
    repo = r.REPO
    h = helper(repo)
    target, archive = Path(target).resolve(), Path(archive).resolve()
    h.require(not target.exists() and not archive.exists(), "new export paths only")
    root = repo / r.ROOT_NAME
    secret = r.read_secret(repo)  # Exact-current-key scan only; no network use.
    members = {}

    def add(path):
        path = Path(path)
        relative = path.relative_to(repo).as_posix()
        h.safe(repo, relative)
        h.require(path.is_file() and not path.is_symlink(), "regular source/data file")
        members["repo/" + relative] = path

    def tree(path):
        h.require(not list(path.rglob("*.partial")), "interrupted data; preserve and stop")
        for p in sorted(path.rglob("*")):
            h.require(not p.is_symlink(), "no source/data symlinks")
            if p.is_file():
                add(p)

    with (root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root, manifest, allocation, book, report, report_sha = completed(r, protocol)
        snapshot = book.snapshot()
        closeout = r.load(repo / CLOSEOUT)
        h.require(closeout["protocol"] == protocol and closeout["report_sha256"] == report_sha and
            closeout["after"] == snapshot, "pinned audited stage closeout required")
        checks = r.load(repo / CHECKS)
        h.require(checks["exit_code"] == 0 and checks["ruff_exit_code"] == 0 and
            checks["helper_sha256"] == r.digest(Path(__file__)) and
            checks["test_sha256"] == r.digest(repo / "tests/test_paper3_office_sacrifice_archive_v1.py"),
            "actual helper checks required")
        with book.locked():
            # Include every file required by the production auditor's original
            # historical-integrity check, including the old completed archives.
            for name in r.load(repo / r.PROTECTED)["protected_inventory"]:
                add(repo / name)
            for name in manifest["sources"]:
                add(repo / name)
            for name in (r.PROTECTED, r.READINESS, AUDIT, CLOSEOUT, CHECKS,
                "results/paper3/office_sacrifice_check_history_2026_11_04.jsonl",
                "analysis/paper3_office_sacrifice_probe_v1.md",
                "analysis/paper3_contracts_archive.py",
                "analysis/paper3_office_sacrifice_archive_v1.py",
                "tests/test_paper3_office_sacrifice_archive_v1.py"):
                add(repo / name)
            tree(root)
            tree(repo / r.LEDGER)
            members[ENTRY] = Path(__file__).resolve()
            hashes = {}
            for name, path in sorted(members.items()):
                h.safe(target, name)
                data = path.read_bytes()
                h.credentials(data, secret)
                hashes[name] = h.sha(data)
            target.mkdir(parents=True, exist_ok=False)
            for name, path in sorted(members.items()):
                dest = h.safe(target, name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with path.open("rb") as source, dest.open("xb") as output:
                    shutil.copyfileobj(source, output)
                h.require(h.sha(dest.read_bytes()) == hashes[name], "file changed during copy")
    readme = ("# Controlled office-sacrifice diagnostic: complete evidence\n\n"
        "Sixteen constructed games, 96 fixed main/control assignments, one model. "
        "Invalid responses and failed attempts remain; no control-based exclusions. "
        "Explicit game-score sensitivity is not intrinsic motivation or population evidence. "
        "The peers' votes and future payoffs were experimentally fixed.\n\n"
        "Actual offline replay, Python 3.11+ on macOS/Linux, standard library only:\n\n"
        "`python3 -I -S " + ENTRY + " --replay --expected-protocol " + protocol + "`\n\n"
        "This checks the entire bundled production report and all ledger-entry hashes, "
        "plus the post-closeout ledger snapshot, with network/process denial selftests. "
        "It executes trusted bundled source; it is not an arbitrary-code security sandbox. "
        "A successful replay establishes consistency, not a positive scientific effect.\n")
    (target / "README.md").write_text(readme)
    hashes["README.md"] = h.sha(readme.encode())
    metadata = dict(format=h.FORMAT, experiment_family=FAMILY, protocol=protocol,
        files=hashes, report_sha256=report_sha, frozen_source_count=len(manifest["sources"]),
        budget=snapshot, accounting=report["accounting"], publication_evidence=False,
        helper_sha256=hashes[ENTRY])
    with (target / "bundle.json").open("x") as stream:
        json.dump(metadata, stream, sort_keys=True, indent=2)
    h.verify_bundle(target, protocol)
    return dict(archive_sha256=h.archive(target, archive), report_sha256=report_sha,
                files=len(hashes), budget=snapshot)


def replay(protocol):
    if sys.flags.isolated != 1 or sys.flags.no_site != 1:
        raise ValueError("actual fresh Python -I -S required")
    sys.dont_write_bytecode = True
    bundle = Path(__file__).resolve().parents[1]
    repo = bundle / "repo"
    h = helper(repo)
    metadata = h.verify_bundle(bundle, protocol)
    h.require(metadata["experiment_family"] == FAMILY, "correct diagnostic archive")
    sys.addaudithook(h.offline_guard)
    import socket
    for operation in (lambda: socket.getaddrinfo("127.0.0.1", 1),
                      lambda: subprocess.run([sys.executable, "-c", "pass"])):
        try:
            operation()
        except RuntimeError as exc:
            h.require(str(exc) == "offline replay forbids network and child processes", "wrong guard")
        else:
            raise ValueError("network/process denial selftest failed")
    sys.path.insert(0, str(repo))
    from experiments import paper3_office_sacrifice_probe_v1 as r
    h.require(r.REPO == repo and Path(r.__file__).resolve() == repo / WRAPPER,
              "actual fresh bundled runner required")
    captured = io.StringIO()
    sys.argv = [str(repo / WRAPPER), "--audit", "--expected-protocol", protocol]
    with contextlib.redirect_stdout(captured):
        runpy.run_path(str(repo / WRAPPER), run_name="__main__")
    result = json.loads(captured.getvalue())
    h.require(result["entire_report_matched"] and result["entire_ledger_matched"] and
        result["report_sha256"] == metadata["report_sha256"] and
        result["accounting"] == metadata["accounting"], "entire report/accounting replay")
    allocation = r.load(repo / r.ROOT_NAME / "allocation.json")
    book = r.budget.ProbeLedger(repo / r.LEDGER, stage_pins=allocation["stage_pins"])
    h.require(book.snapshot() == metadata["budget"], "entire post-closeout ledger snapshot")
    h.verify_bundle(bundle, protocol)
    return dict(protocol=protocol, report_sha256=metadata["report_sha256"],
        entire_report_matched=True, entire_ledger_matched=True,
        actual_isolated_replay=True, actual_bundled_wrapper_cli=True,
        network_process_guard_selftests=True, budget=metadata["budget"],
        accounting=metadata["accounting"], logical=result["logical"], physical=result["physical"])


def extract(archive, target, metadata, bundle_path, h):
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        h.require(zipped.testzip() is None and len(names) == len(set(names)) and
            set(names) == set(metadata["files"]) | {"bundle.json"}, "ZIP CRC/unique inventory")
        for info in zipped.infolist():
            h.require((info.external_attr >> 16) & 0o170000 != 0o120000, "ZIP symlink")
            path = h.safe(target, info.filename)
            data = zipped.read(info)
            expected = (h.sha(Path(bundle_path).read_bytes()) if info.filename == "bundle.json"
                        else metadata["files"][info.filename])
            h.require(h.sha(data) == expected, "ZIP content hash")
            h.credentials(data)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(data)


def cold_replay(target, archive, protocol):
    h = helper(Path(__file__).resolve().parents[1])
    metadata = h.verify_bundle(target, protocol)
    with tempfile.TemporaryDirectory(prefix="paper3-office-cold-") as temporary:
        extracted = Path(temporary).resolve(strict=True)
        extract(archive, extracted, metadata, Path(target) / "bundle.json", h)
        child = subprocess.run([sys.executable, "-I", "-S", str(extracted / ENTRY),
            "--replay", "--expected-protocol", protocol], cwd=extracted,
            capture_output=True, text=True, timeout=3600)
        h.require(child.returncode == 0 and not child.stderr.strip(),
            "actual cold replay failed: " + child.stderr[-3000:])
        certificate = json.loads(child.stdout)
        h.require(certificate["entire_report_matched"] and certificate["entire_ledger_matched"] and
            certificate["actual_isolated_replay"], "genuine cold replay certificate")
    return dict(certificate, actual_child_argv=child.args, actual_child_exit_code=child.returncode,
                actual_child_stdout=child.stdout, actual_child_stderr=child.stderr,
                extracted_resolved_path=str(extracted))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--close-stage", action="store_true")
    parser.add_argument("--expected-protocol", required=True)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.replay:
        result = replay(args.expected_protocol)
    elif args.close_stage:
        result = close_stage(args.expected_protocol)
    else:
        if args.target is None or args.archive is None:
            raise ValueError("new export directory and ZIP required")
        result = build(args.target, args.archive, args.expected_protocol)
        result["cold_replay"] = cold_replay(args.target, args.archive, args.expected_protocol)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
