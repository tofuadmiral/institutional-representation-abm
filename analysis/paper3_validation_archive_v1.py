"""Post-freeze offline packaging of the completed amended validation only.

No inference, economic, retry, scoring or frozen-source changes. The cold replay
executes the bundled NEW wrapper's actual audit CLI under Python -I -S.
"""
import argparse
import contextlib
import fcntl
import hashlib
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

ENTRY = "tools/paper3_validation_archive_v1.py"
FAMILY = "paper3-fresh-validation-timeout-recovery-complete-v1"
AUDIT = "results/paper3/validation_final_audit_2026_10_29.json"
CLOSEOUT = "results/paper3/validation_stage_closeout_2026_10_29.json"
WRAPPER = "experiments/paper3_reasoning_timeout_recovery_v1.py"


def helper(repo):
    spec = importlib.util.spec_from_file_location(
        "_validation_archive_safety", Path(repo)/"analysis/paper3_contracts_archive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit_result(r, output):
    """Decode the genuine wrapper CLI's lossless journal before comparing summaries."""
    return json.loads(json.dumps(r.old.journal.decode(json.loads(output)), default=str))


def budget_snapshot(r, book):
    """Use only while the caller holds the ledger lock; do not nest locks."""
    rows = book._entries()
    used, held = book._total(rows), book._commitments(rows)
    return dict(budget_id=r.old.budget.previous.BUDGET_ID,
        cap_usd=str(r.old.budget.TOTAL_CAP), original_cap_usd="10.00",
        authority_extension_sha256=r.old.budget.EXTENSION_SHA,
        accounted_usd=str(used), remaining_usd=str(r.old.budget.TOTAL_CAP-used),
        entries=len(rows), unspent_active_stage_caps_usd=str(held),
        available_for_new_stages_usd=str(r.old.budget.TOTAL_CAP-used-held),
        pending=sum(e['status']!='settled' for e in rows),
        uncertified=sum(e.get('certified') is False for e in rows))


def timing_check(r, amendment):
    """Preserve and check the historical and prospective finite admission windows."""
    windows = [r.load(r.ROOT/f'block-{i}/admission.json') for i in range(2)]
    remaining = r.load(r.META/'remaining_frame0_admission.json')
    r.require(remaining['amendment_protocol']==
        hashlib.sha256(r.old.journal.canonical(amendment).encode()).hexdigest(),
        'remaining admission protocol')
    r.require(remaining['deadline_unix']-remaining['started_unix']==86400,
        'remaining frame window changed')
    counts = [0, 0]
    for index in range(2):
        r.require(windows[index]['deadline_unix']-windows[index]['started_unix']==86400,
            'original finite frame window changed')
        for path in (r.ROOT/f'block-{index}/calls').glob('*.json'):
            row = r.load(path)
            window = windows[index]
            if index==0 and path.relative_to(r.REPO).as_posix() not in amendment['prior_files']:
                window = remaining
            r.require(window['started_unix'] <= row['admitted_unix'] < window['deadline_unix'],
                'physical admission outside its original/amended finite window')
            counts[index] += 1
    r.require(sum(counts)<=560 and all(n<=280 for n in counts), 'physical bounds changed')
    return dict(physical_by_frame=counts, finite_windows_checked=True,
        historical_window_unchanged=True, remaining_window_never_reset=True)


def build(target, archive, protocol):
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    from experiments import paper3_reasoning_timeout_recovery_v1 as r
    h = helper(repo)
    target, archive = Path(target).resolve(), Path(archive).resolve()
    h.require(not target.exists() and not archive.exists(), 'never overwrite any artifact')
    m = r.verify(protocol, full=True)
    report_sha = r.digest(r.ROOT/'report.json')
    audit = r.load(repo/AUDIT)
    h.require(audit['exit_code']==0 and audit['result']['entire_report_matched']
        and audit['report_sha256']==report_sha
        and audit['result']['amendment_protocol']==protocol, 'genuine exact terminal audit required')
    terminal = r.load(r.ROOT/'invocations/0001-terminal.json')
    h.require(terminal['status']=='complete', 'completed original worker evidence required')
    secret = r.old.previous.original_runner.read_secret(repo)
    members = {}

    def add(path):
        path = Path(path)
        h.require(path.is_file() and not path.is_symlink(), 'regular source/data required')
        members['repo/'+path.relative_to(repo).as_posix()] = path

    def tree(directory):
        directory = Path(directory)
        h.require(not list(directory.rglob('*.partial')), 'partial write; preserve and stop')
        for path in sorted(directory.rglob('*')):
            h.require(not path.is_symlink(), 'symlink source/data')
            if path.is_file():
                add(path)

    with (r.ROOT/'run.lock').open('a') as run_lock:
        fcntl.flock(run_lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        r.verify(protocol, full=True)
        timing = timing_check(r, m)
        pins = r.load(r.ROOT/'allocation.json')
        book = r.old.ledger(pins['stage_pins'])
        with book.locked():
            snapshot = budget_snapshot(r, book)
            closeout = r.load(repo/CLOSEOUT)
            h.require(closeout['report_sha256']==report_sha
                and closeout['amendment_protocol']==protocol
                and closeout['after']==snapshot, 'pinned audited stage closeout required')
            for name in m['sources']:
                add(repo/name)
            for name in (r.READINESS, r.old.READINESS, AUDIT, CLOSEOUT,
                'results/paper3/reasoning_timeout_pending_2026_10_28.json',
                'results/paper3/reasoning_timeout_checks_2026_10_28.json',
                'results/paper3/reasoning_timeout_preliminary_checks_2026_10_28.json',
                'results/paper3/independent_validation_checks_2026_10_27.json',
                'results/paper3/independent_validation_pending_2026_10_27.json',
                'results/paper3/independent_validation_audit_helper_checks_2026_10_27.json',
                'results/paper3/billing_recovery_readiness_2026_10_26.json',
                'results/paper3/graceful_continuation_readiness_2026_10_23.json',
                'tests/test_paper3_validation_archive_v1.py',
                'results/paper3/validation_archive_helper_checks_2026_10_29.json',
                'analysis/paper3_contracts_archive.py'):
                add(repo/name)
            tree(r.ROOT)
            tree(repo/r.old.LEDGER)
            # Preserve the completed discovery provenance AND its original archive.
            discovery = repo/r.old.DISCOVERY
            h.require(r.digest(discovery/'report.json')==r.old.DISCOVERY_REPORT_SHA
                and r.digest(repo/r.old.DISCOVERY_ARCHIVE)==r.old.DISCOVERY_ARCHIVE_SHA,
                'completed discovery evidence changed')
            tree(discovery)
            add(repo/r.old.DISCOVERY_ARCHIVE)
            add(repo/'paper3/data/pivot_b_graceful_continuation_v1_complete/bundle.json')
            legacy = r.load(discovery/'manifest.json')
            for name in legacy['baseline']['references']:
                add(repo/name)
            for name in ('manifest.json','sessions/block-0-start.json','sessions/allocation.json'):
                add(repo/r.old.previous.OLD_ROOT/name)
            members[ENTRY] = Path(__file__).resolve()
            hashes = {}
            for name, path in sorted(members.items()):
                h.safe(target, name)
                data = path.read_bytes()
                h.credentials(data, secret)
                hashes[name] = h.sha(data)
            target.mkdir(parents=True, exist_ok=False)
            for name, path in sorted(members.items()):
                destination = h.safe(target, name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with path.open('rb') as source, destination.open('xb') as output:
                    shutil.copyfileobj(source, output)
                h.require(h.sha(destination.read_bytes())==hashes[name], 'source changed during copy')
    readme = ("# Paper 3 complete fresh-setting validation, with disclosed timeout recovery\n\n"
        "All 480 decisions / 16 two-term episodes and the failed reasoning-only attempt "
        "are retained. Same cases, seeds, model and frozen scientific screens; no "
        "accepted decision regenerated. The original paused verdict and charge remain.\n\n"
        "This is a complete bounded replication on two selected settings / one model, "
        "after technical recovery, not pristine confirmatory or population/motive/publication "
        "evidence. District normalized regret is not total citizen welfare or full-mandate "
        "abandonment. Both horizons, every district/citizen harm and missingness remain.\n\n"
        "Offline replay (standard library only, no credentials):\n\n"
        "`python3 -I -S "+ENTRY+" --replay --expected-protocol "+protocol+"`\n\n"
        "The separate post-freeze helper hashes the complete inventory, self-tests "
        "network/process denial and executes the bundled NEW wrapper's actual --audit "
        "CLI. ENTIRE report, validation screen, physical admission windows and ledger "
        "snapshot must match. These are reproducibility guards for trusted research "
        "code, not a sandbox for arbitrary untrusted code. No model calls occur.\n")
    with (target/'README.md').open('x') as stream:
        stream.write(readme)
    hashes['README.md'] = h.sha(readme.encode())
    metadata = dict(format=h.FORMAT, experiment_family=FAMILY, protocol=protocol,
        legacy_protocol=r.LEGACY, files=hashes, report_sha256=report_sha,
        budget=snapshot, analysis=audit['result']['analysis'],
        validation=audit['result']['validation'], timing=timing,
        frozen_sources=215, publication_evidence=False,
        post_freeze_helper_sha256=hashes[ENTRY])
    with (target/'bundle.json').open('x') as stream:
        json.dump(metadata, stream, sort_keys=True, indent=2)
    h.verify_bundle(target, protocol)
    archive_sha = h.archive(target, archive)
    return dict(archive_sha256=archive_sha, report_sha256=report_sha,
        files=len(hashes), budget=snapshot, timing=timing)


def replay(protocol):
    if sys.flags.isolated!=1 or sys.flags.no_site!=1:
        raise ValueError('actual fresh Python -I -S required')
    sys.dont_write_bytecode = True
    bundle = Path(__file__).resolve().parents[1]
    repo = bundle/'repo'
    h = helper(repo)
    metadata = h.verify_bundle(bundle, protocol)
    h.require(metadata['experiment_family']==FAMILY, 'archive family differs')
    sys.addaudithook(h.offline_guard)
    import socket
    for operation in (lambda:socket.getaddrinfo('127.0.0.1', 1),
                      lambda:subprocess.run([sys.executable, '-c', 'pass'])):
        try:
            operation()
        except RuntimeError as exc:
            h.require(str(exc)=='offline replay forbids network and child processes', 'wrong guard')
        else:
            raise ValueError('offline guard self-test did not block')
    sys.path.insert(0, str(repo))
    from experiments import paper3_reasoning_timeout_recovery_v1 as r
    h.require(r.REPO==repo and Path(r.__file__).resolve()==repo/WRAPPER,
        'must use actual fresh bundled source')
    captured = io.StringIO()
    sys.argv = [str(repo/WRAPPER), '--audit', '--expected-protocol', protocol]
    with contextlib.redirect_stdout(captured):
        runpy.run_path(str(repo/WRAPPER), run_name='__main__')
    result = audit_result(r, captured.getvalue())
    h.require(result['entire_report_matched'] and result['budget']==metadata['budget']
        and result['analysis']==metadata['analysis'] and result['validation']==metadata['validation']
        and r.digest(r.ROOT/'report.json')==metadata['report_sha256'],
        'ENTIRE amended report, validation or ledger mismatch')
    h.require(timing_check(r, r.verify(protocol, full=True))==metadata['timing'],
        'finite-window timing changed')
    h.verify_bundle(bundle, protocol)
    return dict(amendment_protocol=protocol, report_sha256=metadata['report_sha256'],
        entire_report_matched=True, actual_isolated_replay=True,
        actual_bundled_wrapper_cli=True, network_process_guard_self_test=True,
        budget=result['budget'], analysis=result['analysis'], validation=result['validation'],
        timing=metadata['timing'], publication_evidence=False)


def cold_replay(target, archive, protocol):
    repo = Path(__file__).resolve().parents[1]
    h = helper(repo)
    metadata = h.verify_bundle(target, protocol)
    with tempfile.TemporaryDirectory(prefix='paper3-validation-cold-') as directory:
        extracted = Path(directory).resolve(strict=True)
        with zipfile.ZipFile(archive) as zipped:
            names = zipped.namelist()
            h.require(zipped.testzip() is None and len(names)==len(set(names))
                and set(names)==set(metadata['files'])|{'bundle.json'}, 'ZIP CRC/inventory failed')
            for info in zipped.infolist():
                h.require((info.external_attr>>16)&0o170000!=0o120000, 'ZIP symlink')
                path = h.safe(extracted, info.filename)
                data = zipped.read(info)
                expected = (h.sha((Path(target)/'bundle.json').read_bytes())
                    if info.filename=='bundle.json' else metadata['files'][info.filename])
                h.require(h.sha(data)==expected, 'ZIP member differs')
                h.credentials(data)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('xb') as stream:
                    stream.write(data)
        child = subprocess.run([sys.executable,'-I','-S',str(extracted/ENTRY),
            '--replay','--expected-protocol',protocol], cwd=extracted,
            capture_output=True, text=True, timeout=3600)
        h.require(child.returncode==0 and not child.stderr.strip(),
            'actual isolated replay failed: '+child.stderr[-3000:])
        certificate = json.loads(child.stdout)
    h.require(certificate['entire_report_matched'] and certificate['actual_isolated_replay'],
        'missing genuine cold replay certificate')
    return dict(certificate, actual_child_argv=child.args, actual_child_exit_code=child.returncode,
        actual_child_stdout=child.stdout, actual_child_stderr=child.stderr,
        extracted_resolved_path=str(extracted))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay', action='store_true')
    parser.add_argument('--expected-protocol', required=True)
    parser.add_argument('--target', type=Path)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    if args.replay:
        result = replay(args.expected_protocol)
    else:
        if args.target is None or args.archive is None:
            raise ValueError('new target and archive required')
        result = build(args.target, args.archive, args.expected_protocol)
        result['cold_replay'] = cold_replay(args.target, args.archive, args.expected_protocol)
    print(json.dumps(result), flush=True)


if __name__=='__main__':
    main()
