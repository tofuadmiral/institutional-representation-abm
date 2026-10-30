"""Post-freeze portable closeout only; no inference or scientific changes."""
import argparse
import fcntl
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ENTRY = "tools/paper3_billing_archive_v1.py"
FAMILY = "paper3-billing-continuation-complete-v1"


def helper(repo):
    spec = importlib.util.spec_from_file_location(
        "_billing_archive_safety", Path(repo) / "analysis/paper3_contracts_archive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def budget_snapshot(r, book):
    rows = book._entries()
    used, held = book._total(rows), book._commitments(rows)
    return dict(budget_id=r.old.budget.BUDGET_ID, cap_usd="19.30", original_cap_usd="10.00",
        authority_extension_sha256=r.old.budget.EXTENSION_SHA,
        accounted_usd=str(used), remaining_usd=str(r.old.budget.TOTAL_CAP-used),
        entries=len(rows), unspent_active_stage_caps_usd=str(held),
        available_for_new_stages_usd=str(r.old.budget.TOTAL_CAP-used-held),
        pending=sum(e['status']!='settled' for e in rows),
        uncertified=sum(e.get('certified') is False for e in rows))


def build(target, archive, protocol):
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    from experiments import paper3_billing_recovery_v1 as r
    h = helper(repo)
    target, archive = Path(target).resolve(), Path(archive).resolve()
    h.require(not target.exists() and not archive.exists(), "never overwrite archive or directory")
    m = r.verify(protocol, full=True)
    report_sha = r.digest(r.ROOT / "report.json")
    audit = r.load(repo / "results/paper3/billing_recovery_final_audit_2026_10_26.json")
    h.require(audit['exit_code']==0 and audit['result']['entire_report_matched']
              and audit['report_sha256']==report_sha
              and audit['result']['amendment_protocol']==protocol, "actual exact audit required")
    secret = r.old.original_runner.read_secret(repo)
    members = {}

    def add(path):
        path = Path(path)
        h.require(path.is_file() and not path.is_symlink(), "regular source/data file required")
        members['repo/' + path.relative_to(repo).as_posix()] = path

    def tree(directory):
        h.require(not list(Path(directory).rglob('*.partial')), "partial write; preserve and stop")
        for path in sorted(Path(directory).rglob('*')):
            h.require(not path.is_symlink(), "symlink source/data")
            if path.is_file():
                add(path)

    with (r.ROOT/'run.lock').open('a') as run_lock:
        fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r.verify(protocol, full=True)
        pins=r.load(r.ROOT/'allocation.json')
        book=r.old.ledger(pins['stage_pins'])
        with book.locked():
            snapshot=budget_snapshot(r,book)
            for name in m['sources']:
                add(repo/name)
            for name in (r.READINESS, r.old.READINESS,
                'results/paper3/billing_recovery_checks_2026_10_26.json',
                'results/paper3/billing_recovery_pending_2026_10_26.json',
                'results/paper3/billing_recovery_final_audit_2026_10_26.json',
                'results/paper3/billing_recovery_stage_closeout_2026_10_26.json',
                'analysis/paper3_contracts_archive.py'):
                add(repo/name)
            tree(r.ROOT)
            tree(repo/r.old.LEDGER)
            legacy=r.load(r.ROOT/'manifest.json')
            for name in legacy['baseline']['references']:
                add(repo/name)
            for name in ('manifest.json','sessions/block-0-start.json','sessions/allocation.json'):
                add(repo/r.old.OLD_ROOT/name)
            members[ENTRY]=Path(__file__).resolve()
            hashes={}
            # Validate ALL credentials and paths before creating an artifact.
            for name,path in sorted(members.items()):
                h.safe(target,name)
                data=path.read_bytes()
                h.credentials(data,secret)
                hashes[name]=h.sha(data)
            target.mkdir(parents=True,exist_ok=False)
            for name,path in sorted(members.items()):
                destination=h.safe(target,name)
                destination.parent.mkdir(parents=True,exist_ok=True)
                with path.open('rb') as source, destination.open('xb') as output:
                    shutil.copyfileobj(source,output)
                h.require(h.sha(destination.read_bytes())==hashes[name], "source changed while copying")
    readme=("# Paper 3 completed discovery: billing-only technical continuation\n\n"
        "All 480 logical decisions / 16 two-term episodes are retained, including the "
        "original failed overload and saved response's original billing failure. "
        "Historical uncertain reservations stay accounted. Both horizons and every "
        "district/citizen outcome and harm remain in the raw report.\n\n"
        "This is two selected settings and one model, after disclosed technical recovery; "
        "not independent, population, motive or publication evidence. First-term district "
        "regret is not total citizen welfare or full-horizon mandate abandonment.\n\n"
        "Offline replay (Python standard library only; no credentials):\n\n"
        "`python3 -I -S "+ENTRY+" --replay --expected-protocol "+protocol+"`\n\n"
        "The helper is post-freeze packaging code. It never changes the 200 frozen "
        "sources or scientific rules. It hashes the complete inventory, blocks network "
        "and child processes, executes the actual bundled amended audit, and requires "
        "the entire report and historical ledger snapshot to match. These guards are "
        "for trusted research-code reproducibility, not arbitrary untrusted-code sandboxing.\n")
    (target/'README.md').write_text(readme)
    hashes['README.md']=h.sha(readme.encode())
    metadata=dict(format=h.FORMAT,experiment_family=FAMILY,protocol=protocol,
        legacy_protocol=r.OLD_PROTOCOL,files=hashes,report_sha256=report_sha,
        budget=snapshot,analysis=audit['result']['analysis'],frozen_sources=200,
        publication_evidence=False,post_freeze_helper_sha256=hashes[ENTRY])
    with (target/'bundle.json').open('x') as stream:
        json.dump(metadata,stream,sort_keys=True,indent=2)
    h.verify_bundle(target,protocol)
    sha=h.archive(target,archive)
    return dict(archive_sha256=sha,report_sha256=report_sha,files=len(hashes),budget=snapshot)


def replay(protocol):
    if sys.flags.isolated!=1 or sys.flags.no_site!=1:
        raise ValueError('fresh Python -I -S required')
    sys.dont_write_bytecode=True
    bundle=Path(__file__).resolve().parents[1]
    repo=bundle/'repo'
    h=helper(repo)
    metadata=h.verify_bundle(bundle,protocol)
    h.require(metadata['experiment_family']==FAMILY, 'archive family differs')
    sys.addaudithook(h.offline_guard)
    import socket
    for operation in (lambda:socket.getaddrinfo('127.0.0.1',1),
                      lambda:subprocess.run([sys.executable,'-c','pass'])):
        try:
            operation()
        except RuntimeError as exc:
            h.require(str(exc)=='offline replay forbids network and child processes','wrong guard')
        else:
            raise ValueError('offline guard self-test did not block')
    sys.path.insert(0,str(repo))
    from experiments import paper3_billing_recovery_v1 as r
    h.require(r.REPO==repo and Path(r.__file__).resolve().is_relative_to(repo),
              'must use actual fresh bundled source')
    result=json.loads(json.dumps(r.audit(protocol),default=str))
    h.require(result['entire_report_matched'] and result['budget']==metadata['budget']
              and result['analysis']==metadata['analysis']
              and r.digest(r.ROOT/'report.json')==metadata['report_sha256'],
              'ENTIRE report or ledger mismatch')
    h.verify_bundle(bundle,protocol)
    return dict(amendment_protocol=protocol,report_sha256=metadata['report_sha256'],
        entire_report_matched=True,actual_isolated_replay=True,
        network_process_guard_self_test=True,budget=result['budget'],
        analysis=result['analysis'],publication_evidence=False)


def cold_replay(target,archive,protocol):
    repo=Path(__file__).resolve().parents[1]
    h=helper(repo)
    metadata=h.verify_bundle(target,protocol)
    with tempfile.TemporaryDirectory(prefix='paper3-billing-cold-') as directory:
        extracted=Path(directory).resolve(strict=True)
        with zipfile.ZipFile(archive) as zipped:
            names=zipped.namelist()
            h.require(zipped.testzip() is None and len(names)==len(set(names))
                and set(names)==set(metadata['files'])|{'bundle.json'},'ZIP CRC/inventory failed')
            for info in zipped.infolist():
                h.require((info.external_attr>>16)&0o170000!=0o120000,'ZIP symlink')
                path=h.safe(extracted,info.filename)
                data=zipped.read(info)
                expected=(h.sha((Path(target)/'bundle.json').read_bytes()) if info.filename=='bundle.json'
                          else metadata['files'][info.filename])
                h.require(h.sha(data)==expected,'ZIP member differs')
                path.parent.mkdir(parents=True,exist_ok=True)
                with path.open('xb') as stream:
                    stream.write(data)
        child=subprocess.run([sys.executable,'-I','-S',str(extracted/ENTRY),
            '--replay','--expected-protocol',protocol],cwd=extracted,
            capture_output=True,text=True,timeout=1800)
        h.require(child.returncode==0 and not child.stderr.strip(),
                  'actual isolated replay failed: '+child.stderr[-3000:])
        certificate=json.loads(child.stdout)
    h.require(certificate['entire_report_matched'] and certificate['actual_isolated_replay'],
              'missing genuine cold replay certificate')
    return certificate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay',action='store_true')
    parser.add_argument('--expected-protocol',required=True)
    parser.add_argument('--target',type=Path)
    parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    if args.replay:
        result=replay(args.expected_protocol)
    else:
        if args.target is None or args.archive is None:
            raise ValueError('new target and archive required')
        result=build(args.target,args.archive,args.expected_protocol)
        result['cold_replay']=cold_replay(args.target,args.archive,args.expected_protocol)
    print(json.dumps(result,default=str),flush=True)


if __name__=='__main__':
    main()
