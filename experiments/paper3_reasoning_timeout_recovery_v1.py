"""Resume the SAME validation after an approved reasoning-only timeout amendment.

Original source/raw/unsafe verdict/charges remain byte-identical. All economic,
native-call, billing and bounded durable-worker code objects are reused; only
the failed-attempt eligibility and a disclosed finite remaining admission differ.
"""
# ruff: noqa: E402
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True
from experiments import paper3_independent_validation_v1 as old
from paper3 import retrospective_reasoning_timeout_recovery_v1 as policy
from paper3 import retrospective_receipt_recovery_v1 as billing
from paper3.retrospective_source_closure import closure

ROOT = REPO / old.ROOT_NAME
META = ROOT / "reasoning_timeout_amendment_v1"
LEGACY = "1489d7c0d44a091fd431658742f2cbc42428b357c4224129f007d4ff826cadbd"
FAILED = "validation-r1-0-aligned-binding_sum-16-a1"
FAILED_SHA = "5983c74d12f0a21bf85a0fa1c4d14942805fe913f05cd9acf1ae5cd17cac6887"
AUTHORITY = "results/paper3/reasoning_timeout_recovery_authorization_2026_10_28.json"
AUTHORITY_SHA = "7c89f58e01b78495be9fce709ee3271035ca2a8bcfe4ee19636be5a02944766a"
READINESS = "results/paper3/reasoning_timeout_recovery_readiness_2026_10_28.json"
STOP = "results/paper3/independent_validation_stop_2026_10_27.json"
STOP_SHA = "fb78aa49373351c862cf1f26a8d9408383e8d12b4c63dfe1927aaf75bd6b2bb8"
TEST_COMMAND = [".venv/bin/python", "-B", "-m", "pytest",
    "tests/test_paper3_reasoning_timeout_recovery_v1.py",
    "tests/test_paper3_independent_validation_v1.py",
    "tests/test_paper3_graceful_recovery.py",
    "tests/test_paper3_billing_recovery_v1.py", "-q", "--tb=short", "-x"]
require, load, digest, atomic = old.require, old.load, old.digest, old.atomic


def specification():
    return dict(version=policy.VERSION, original_protocol=LEGACY,
        failed_response_sha256=FAILED_SHA, total_cap_usd="21.31",
        maximum_physical_including_history=560, maximum_reissues_per_action=3,
        maximum_reissues_per_frame=40, minimum_cooldowns_seconds=(300,600,1200),
        same_request_seed_and_economic_code=True, no_received_action_retry=True,
        no_accepted_action_replacement=True, failed_attempt_and_cost_preserved=True,
        new_remaining_frame0_window_seconds=86400, window_never_reset_on_resume=True)


def source_inventory():
    manifest = load(ROOT/'manifest.json')
    roots = [REPO/n for n in manifest['sources']]
    roots += [Path(__file__), REPO/AUTHORITY, REPO/STOP,
        REPO/'paper3/retrospective_reasoning_timeout_recovery_v1.py',
        REPO/'tests/test_paper3_reasoning_timeout_recovery_v1.py',
        REPO/'analysis/paper3_reasoning_timeout_checks_v1.py',
        REPO/'analysis/paper3_validation_audit_v1.py',
        REPO/'tests/test_paper3_validation_audit_v1.py']
    return {p.relative_to(REPO).as_posix():digest(p) for p in closure(REPO,roots)}


def prepare():
    require(not META.exists(), 'prepare this amendment once only')
    with (ROOT/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        original,_=old.verify(ROOT,LEGACY)
        require(not(ROOT/'report.json').exists(), 'completed experiment cannot restart')
        require(digest(REPO/AUTHORITY)==AUTHORITY_SHA and digest(REPO/STOP)==STOP_SHA,
            'approved scope and original stop must remain')
        auth=load(REPO/AUTHORITY)
        require(auth['total_cumulative_cap_usd']=='21.31'
            and auth['maximum_physical_requests_including_history']==560
            and auth['budget_extension'] is False, 'same cumulative authority and physical bound')
        ready=load(REPO/READINESS)
        sources=source_inventory()
        require(ready['argv']==TEST_COMMAND and ready['returncode']==0
            and not ready['stderr'].strip() and 'passed' in ready['stdout']
            and ready['sources_before']==ready['sources_after']==sources
            and ready['specification']==old.journal.encode(specification()),
            'genuine unchanged current-source offline checks required')
        terminal=load(ROOT/'invocations/0000-terminal.json')
        require(terminal['status']=='paused' and terminal['reason']=='nonretryable_instrument_failure',
            'original latest paused evidence required')
        require(not(ROOT/'block-1').exists(), 'unexpected later writer/block')
        bad=ROOT/'block-0/calls'/(FAILED+'.json')
        require(digest(bad)==FAILED_SHA and policy.eligibility(load(bad))['eligible'],
            'exact original reasoning-only/no-action failure')
        pins=load(ROOT/'allocation.json')
        old.validate_pins(pins,original,LEGACY)
        checker=old.drivers()[0].__globals__['check_record']
        for p in ROOT.glob('block-*/calls/*.json'):
            checker(p,load(p),original,pins)
        accepted={p.stem:load(p) for p in (ROOT/'block-0/accepted').glob('*.json')}
        require(len(accepted)==16 and len(list(ROOT.glob('block-*/calls/*.json')))==17,
            'exact preserved sixteen decisions/seventeen physical attempts')
        files={p.relative_to(REPO).as_posix():digest(p) for p in sorted(ROOT.rglob('*.json'))}
        entries=old.prior_entries()
        require(len(entries)==7408, 'exact pre-amendment historical financial inventory')
        manifest=dict(format='paper3-reasoning-timeout-amendment-v1',sources=sources,
            original_protocol=LEGACY, authority_sha256=AUTHORITY_SHA,
            readiness_sha256=digest(REPO/READINESS), prior_files=files, prior_entries=entries,
            accepted_prefix=accepted, specification=old.journal.encode(specification()),
            failed_response_sha256=FAILED_SHA,
            disclosure='Technical same-study retry amendment after an observed reasoning-only '
                'stream timeout. Original unsafe/paused verdict and charge retained. Fresh '
                'settings remain, but this is not pristine confirmatory or population evidence.')
        protocol=hashlib.sha256(old.journal.canonical(manifest).encode()).hexdigest()
        META.mkdir(exist_ok=False)
        atomic(META/'manifest.json',manifest)
        return dict(protocol=protocol,legacy_wire_protocol=LEGACY,sources=len(sources),
            accepted_decisions_preserved=16,physical_attempts_preserved=17,model_calls=0)


def verify(protocol, *, full=False):
    m=load(META/'manifest.json')
    require(hashlib.sha256(old.journal.canonical(m).encode()).hexdigest()==protocol,
        'external amendment protocol changed')
    old.verify(ROOT,LEGACY)
    require(m['sources']==source_inventory()
        and m['authority_sha256']==AUTHORITY_SHA==digest(REPO/AUTHORITY)
        and m['readiness_sha256']==digest(REPO/READINESS), 'amendment source/authority/readiness changed')
    for name,sha in m['prior_files'].items():
        require(digest(REPO/name)==sha, 'prior raw/cache/start/unsafe record changed: '+name)
    if full:
        for name,sha in m['prior_entries'].items():
            require(digest(REPO/old.LEDGER/'entries'/name)==sha, 'historical charge changed')
    return m


def prefix_replay(m, protocol):
    """Byte-exact replay to the existing failure boundary; NEVER a network call."""
    seen=[]
    accepted={p.stem:load(p) for p in ROOT.glob('block-*/accepted/*.json')}
    original,pin=old.verify(ROOT,LEGACY)[0],load(ROOT/'allocation.json')
    checker=old.drivers()[0].__globals__['check_record']
    boundary=None
    class Boundary(BaseException):
        pass
    def respond(request,key):
        nonlocal boundary
        ref=accepted.get(key)
        if ref is None:
            boundary=key
            raise Boundary()
        path=REPO/ref['path']
        require(digest(path)==ref['sha256'], 'accepted prefix changed')
        row=load(path)
        checker(path,row,original,pin)
        require(row['request_text']==old.previous.route.reservation(request)['request_text'],
            'byte-exact original request/seed')
        require(old.classify(row,request,key)['status'] in
            ('recorded_valid','content_failed','resource_failed'), 'saved decision changed')
        seen.append(key)
        return dict(row,id=key)
    try:
        for frame in old.design.FRAME_SEEDS:
            old.billing.execute(tuple(a for a in old.items() if a['seed']==frame),
                respond=respond,verify=lambda:verify(protocol),persist=lambda event:None)
    except Boundary:
        pass
    require(set(seen)==set(accepted) and set(m['accepted_prefix']) <= set(seen)
        and len(m['accepted_prefix'])==16, 'all saved/original decisions replay without calls')
    if len(seen)==16:
        require(boundary==FAILED.rsplit('-a',1)[0], 'original continuation boundary')
    return dict(accepted_decisions=len(seen),historical_decisions_preserved=16,
        byte_exact_requests=True,model_calls=0,next_logical_id=boundary,amendment_protocol=protocol)


def wait_pending_cooldown(protocol):
    """Finish any remaining shared cooldown BEFORE the late live observer."""
    deadline=time.time()
    for path in ROOT.glob('block-*/calls/*.json'):
        row=load(path)
        key=row['context']['logical_id']
        if (path.parent.parent/'accepted'/(key+'.json')).exists():
            continue
        verdict=policy.eligibility(row)
        if verdict['eligible']:
            attempt=int(row['id'].rsplit('-a',1)[1])
            require(attempt<4,'per-action retry limit; no additional admission')
            deadline=max(deadline,row['ended_unix']+
                max(old.recovery.COOLDOWNS[attempt-1],verdict['delay'] or 0))
    while time.time()<deadline:
        time.sleep(min(30,deadline-time.time()))
        verify(protocol)


def drivers(protocol, admission=None):
    amendment=verify(protocol)
    def guard(root,legacy):
        require(Path(root)==ROOT and legacy==LEGACY, 'same experiment/wire protocol only')
        verify(protocol)
        return old.verify(root,legacy)
    def checked_load(path):
        if Path(path)==ROOT/'block-0/admission.json':
            return load(META/'remaining_frame0_admission.json')
        return load(path)
    def readout(reports):
        result=old.readout(reports)
        result['transport_recovery']=dict(amendment_protocol=protocol,
            original_failed_attempt_and_charge_preserved=True,
            original_accepted_decisions_preserved=16,disclosure=amendment['disclosure'])
        return result
    run,audit=old.drivers(admission)
    base_recovery=SimpleNamespace(DurableResponses=policy.DurableResponses,
        Paused=old.recovery.Paused, overload=policy.eligibility,
        COOLDOWNS=old.recovery.COOLDOWNS)
    deps=dict(verify=guard,load=checked_load,readout=readout,recovery=base_recovery)
    return billing.bind(run,**deps),billing.bind(audit,**deps)


def run(protocol, *, secret=None, send=None, lookup=None, admission=None):
    m=verify(protocol,full=True)
    base_admit=admission or old.live_admission(ROOT,LEGACY,secret)
    def admit(original):
        verify(protocol,full=True)
        window=META/'remaining_frame0_admission.json'
        if window.exists():
            require(time.time()<load(window)['deadline_unix'], 'remaining window expired; never reset')
        proof=prefix_replay(m,protocol)
        if not(META/'prefix_replay.json').exists():
            atomic(META/'prefix_replay.json',proof)
        wait_pending_cooldown(protocol)
        base_admit(original)  # Funding/route observer occurs AFTER expensive prefix replay.
        admit.observed_unix=base_admit.observed_unix
        if not window.exists():
            now=time.time()
            atomic(window,dict(started_unix=now,deadline_unix=now+86400,
                amendment_protocol=protocol,original_admission_preserved=True))
        atomic(META/('admission-'+str(time.time_ns())+'.json'),dict(
            amendment_protocol=protocol,metadata_observed_unix=admit.observed_unix))
    return drivers(protocol,admit)[0](ROOT,LEGACY,secret=secret,send=send,lookup=lookup,admission=admit)


def audit(protocol):
    verify(protocol,full=True)
    inner=drivers(protocol)
    def checked_load(path):
        value=load(path)
        return old.journal.decode(value) if Path(path)==ROOT/'report.json' else value
    def guard(root,legacy):
        require(Path(root)==ROOT and legacy==LEGACY,'same experiment')
        verify(protocol)
        return old.verify(root,legacy)
    # Exact full production outer audit + its previously tested codec dependency.
    outer=billing.bind(old.audit,verify=guard,drivers=lambda:inner,load=checked_load)
    result=outer(ROOT,LEGACY)
    result['amendment_protocol']=protocol
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    for name in ('prepare','run','audit'):
        modes.add_argument('--'+name,action='store_true')
    parser.add_argument('--expected-protocol')
    args=parser.parse_args()
    if args.prepare:
        require(args.expected_protocol is None,'no invented preparation pin')
        result=prepare()
    else:
        require(args.expected_protocol is not None,'external amendment pin required')
        result=(audit(args.expected_protocol) if args.audit else run(args.expected_protocol,
            secret=old.previous.original_runner.read_secret(REPO)))
    print(json.dumps(old.journal.encode(result)),flush=True)


if __name__=='__main__':
    main()
