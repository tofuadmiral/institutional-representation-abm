"""Approved single policy-relabel form: 364 intended calls, shared $1.25 cap.

Immutable original gate is inherited, verified offline, and never re-run here.
All transport, failure retention and atomic charge/reservation safeguards remain.
One certified exact transport reissue is allowed; no content repair or restart.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import paper3_deepseek_disclosure_a3 as old
from paper3 import disclosure_relabel_design as design
from experiments import paper3_disclosure_identification as original
from analysis import paper3_disclosure_identification_audit as original_audit
from paper3 import agenda_disclosure_canonical as game
from paper3.source_closure import closure
from paper3.audit_runtime import PilotStore, digest

NAME = 'deepseek-disclosure-relabel-v1'
ORIGINAL_ROOT = ROOT/'results/paper3/deepseek_identification_v1'
ORIGINAL_PROTOCOL = 'f15d4d9a72af4bd741739c7f064b3a143b577969fc82e025ce9ccf1021cf4bf4'
PRIOR = Decimal('4.048918542')
CAP = Decimal('1.25')
AUTHORIZED = Decimal('10')
SHARDS = 4
SEED_BASE = 301000
MAX_WORKERS = 4
MAX_CALLS = SHARDS * 182  # one initial attempt + at most one transport reissue
base = old.base
request_for = old.request_for
row_cost = old.row_cost


def load(path):
    return json.loads(path.read_text())


def gate_reference():
    """Read-only exact replay of the prior gate; no provider calls."""
    manifest = load(ORIGINAL_ROOT/'manifest.json')
    if digest(manifest) != ORIGINAL_PROTOCOL:
        raise ValueError('original coordinator protocol changed')
    reference = original_audit.verify_shard(ORIGINAL_ROOT/'gate', None)
    terminal = load(ORIGINAL_ROOT/'gate/sessions/terminal.json')
    if reference['state'] != 'terminal' or reference['calls'] != 8 or not terminal['passed']:
        raise ValueError('inherited gate is not a completed 8/8 pass')
    configured = {k:v for k,v in request_for(dict(messages=[],seed=SEED_BASE)).items()
                  if k not in ('messages','seed')}
    records = [load(p) for p in sorted((ORIGINAL_ROOT/'gate/calls').glob('*.json'))]
    if any({k:v for k,v in row['request'].items() if k not in ('messages','seed')} != configured
           for row in records):
        raise ValueError('native inference configuration differs from inherited gate')
    return dict(mode='inherited_no_new_calls', original_protocol=ORIGINAL_PROTOCOL,
        original_gate_protocol=terminal['protocol_hash'], passed=True, checks=8,
        terminal_sha256=hashlib.sha256((ORIGINAL_ROOT/'gate/sessions/terminal.json').read_bytes()).hexdigest(),
        records_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted((ORIGINAL_ROOT/'gate/calls').glob('*.json'))},
        request_configuration=configured,
        caveat='Same advertised endpoint/configuration, not immutable provider weights or a new competence sample.')


def inherited_gate_terminal(protocol_hash):
    return dict(protocol_hash=protocol_hash, passed=True, fresh_calls=0,
                accounted_usd='0', reference=gate_reference(), halt=None)


def all_rows(root):
    return [load(p) for p in root.glob('*/calls/*.json')]


class Backend(old.Backend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unsubmitted_request = None

    def guard(self, reserve):
        # MUST be called under the shared admission lock, including save(started).
        local, global_rows = self.rows(), all_rows(self.store.root.parent)
        if self.phase != 'episodes':
            raise base.Halt('fresh gate calls are not authorized')
        cap_calls = 182
        cap_cost = CAP
        if len(local) >= cap_calls or len(global_rows) >= MAX_CALLS:
            raise base.Halt('authorized call ceiling reached')
        if sum((row_cost(r) for r in local), Decimal(0)) + reserve > cap_cost:
            raise base.Halt('phase spending ceiling reached')
        total = sum((row_cost(r) for r in global_rows), Decimal(0)) + reserve
        if total > CAP or PRIOR + total > AUTHORIZED:
            raise base.Halt('shared spending ceiling reached')

    def call(self, case):
        if self.halt:
            raise base.Halt(self.halt)
        request = request_for(case)
        decision_id = case['decision_id']
        for attempt in (1, 2):
            key = digest(dict(request=request, phase=self.phase, protocol=self.store.protocol_hash,
                              attempt=attempt, decision_id=decision_id))
            if (self.store.root / 'calls' / (key + '.json')).exists():
                self.fail('existing call is not automatically resumed')
            try:
                bound, reserve = base.reserve_for(request)
                with base.admission_lock(self.store.root):
                    if self.stop_path().exists():
                        raise base.Halt('coordinated batch safety halt')
                    self.guard(reserve)
                    row = dict(request=request, request_text=base.encoded_request(request), phase=self.phase,
                        attempt=attempt, decision_id=decision_id,
                        protocol_hash=self.store.protocol_hash, input_token_bound=bound,
                        reserved_usd=str(reserve), started_unix=time.time(), status='started')
                    self.store.save('calls', key, row)
            except base.Halt as exc:
                self.unsubmitted_request = dict(case=case, attempt=attempt, reason=str(exc))
                self.fail(str(exc), batch=True)
            sent = self.transport(row['request_text'], self.secret)
            wire = '\n'.join(sent['lines'])
            redacted = self.secret in wire
            lines = [line.replace(self.secret, '[REDACTED_CREDENTIAL]') for line in sent['lines']]
            row.update(status='recorded', http_status=sent['http_status'], stream_lines=lines,
                generation_id=sent['generation_id'], secret_redacted=redacted,
                elapsed_seconds=time.time()-row['started_unix'])
            if sent['error']:
                row['transport_error'] = sent['error']
            try:
                response, complete = old.assemble(lines)
            except (ValueError, TypeError):
                response, complete = {}, False
            row['response'] = response
            row['generation_id'] = row['generation_id'] or response.get('id')
            if complete and sent['http_status'] == 200 and not sent['error'] and not redacted:
                try:
                    if row['generation_id'] != response.get('id'):
                        raise ValueError('generation id mismatch')
                    row.update(verified_cost_usd=str(base.accounting(row)), outcome='answered')
                except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
                    row.update(accounting_error=type(exc).__name__ + ': ' + str(exc),
                               halt_reason='transport/accounting/routing failure')
                    self.store.save('calls', key, row)
                    self.fail(row['halt_reason'], key, batch=True)
                self.store.save('calls', key, row)
                self._log(case, row)
                return key, row
            try:
                if redacted:
                    raise ValueError('credential echo')
                receipt = self.generation(row['generation_id'], self.secret) if row['generation_id'] else None
                receipt_text = json.dumps(receipt)
                if self.secret in receipt_text:
                    row['secret_redacted'] = True
                    row['generation_receipt'] = json.loads(receipt_text.replace(self.secret, '[REDACTED_CREDENTIAL]'))
                    raise ValueError('credential echo in receipt')
                row['generation_receipt'] = receipt
                if not receipt or receipt.get('id') != row['generation_id']:
                    raise ValueError('generation receipt missing or id mismatch')
                if receipt.get('model') != old.MODEL:
                    raise ValueError('served model mismatch')
                row.update(certified_cost_usd=str(old.certify(receipt, row)), outcome='transport_certified')
                self.store.save('calls', key, row)
                self._log(case, row)
            except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
                row.update(accounting_error=type(exc).__name__ + ': ' + str(exc),
                           halt_reason='uncertified transport failure; reservation retained')
                self.store.save('calls', key, row)
                self.fail(row['halt_reason'], key, batch=True)
        raise old.TransportFailed('transport failed on both declared attempts')


def protocol(index):
    return dict(name=NAME, shard=index, frame=design.frame(), schedules=[[list(v) for v in design.schedule(i)] for i in range(SHARDS)],
        seed_base=SEED_BASE, inherited_gate=gate_reference(),
        seed_check=dict(pairing='Reuse the original two requested seed schedules, intentionally paired across label forms; new protocol/request identities, never cached answers.'),
        request_identity='Logical decision_id is ledger metadata only: separate calls even if independent paths have identical serialized requests. Exact transport reissue keeps decision_id and all wire bytes unchanged.',
        inference=request_for(dict(messages=[],seed=SEED_BASE)),
        endpoint_recheck=dict(date='2026-09-23', source='https://openrouter.ai/api/v1/models/deepseek/deepseek-v3.2/endpoints',
            tag='atlas-cloud/fp8', model='deepseek/deepseek-v3.2', provider='AtlasCloud',
            prompt_usd_per_token='0.00000026', completion_usd_per_token='0.00000038',
            max_completion_tokens=147456, quantization='fp8', native_reasoning=True,
            note='Public endpoint rechecked before freeze; request price ceilings and no fallback remain enforced.'),
        budget=dict(prior=str(PRIOR), ceiling=str(CAP), cumulative_maximum=str(PRIOR+CAP),
                    gate_ceiling='0', intended_calls=364, max_calls=MAX_CALLS, max_workers=MAX_WORKERS,
                    allocation='shared atomic admission ledger, charges plus outstanding/uncertified reservations'),
        transport=__doc__,
        prerequisites='Original identification pilot completed. Inherit its exact offline-verified 8/8 gate only with identical native request/provider configuration; zero fresh gate calls. New isomorphism/replay tests and current endpoint preflight must pass.',
        safety='No interrupted coordinator or worker restart. No replacement profiles, content repair, provider fallback or automatic follow-on. '
               'Uncertain accounting stops batch; admitted calls finish. Invalid normal model action ends episode only.',
        evidence='One prospectively fixed sequential label/serialization robustness form on two selected games; not independent population confirmation or publication-ready evidence.')


def sources():
    # Freeze every original source plus raw inherited-gate evidence and new code.
    evidence = [ORIGINAL_ROOT/'manifest.json'] + sorted((ORIGINAL_ROOT/'gate').rglob('*.json'))
    return closure(ROOT, original.sources() + evidence + [
        Path(__file__).resolve(), ROOT/'analysis/paper3_disclosure_relabel_audit.py',
        ROOT/'tests/test_paper3_disclosure_relabel.py',
    ])


def run_early(backend, profile, arm, seed):
    keys = []
    def ask(messages, position):
        case = dict(old.case_for(messages, seed+position), decision_id=f'early-{arm}:{position}')
        key, raw = old.answer(backend, case)
        keys.append(key)
        return raw
    return dict(game.run_early(profile, arm, ask), call_keys=keys)


def run_late_condition(backend, profile, order, seed):
    keys = []
    def ask(messages, position):
        context = json.loads(messages[1]['content'].split('\n', 1)[0])
        arm = 'prefix' if position < 9 else next(e['rule'] for e in context['official_events']
                                                if e['stage']=='authority_in_force')
        case = dict(old.case_for(messages, seed+position), decision_id=f'late-{arm}:{position}')
        key, raw = old.answer(backend, case)
        keys.append(key)
        return raw
    return dict(game.run_late(profile, ask, order), call_keys=keys)


def open_store(root, index):
    store = PilotStore(root, protocol(index), sources())
    snapshot = root/'sources.json'
    if not snapshot.exists():
        with snapshot.open('x') as f:
            json.dump({str(p.relative_to(ROOT)):p.read_text() for p in sources()}, f, indent=2)
    return store


def run_gate(root, secret):
    """Record inherited evidence only; this function cannot perform inference."""
    store = open_store(root/'gate', None)
    if list((store.root/'calls').glob('*.json')) or list((store.root/'sessions').glob('*.json')):
        raise base.Halt('gate record already exists; do not restart')
    out = inherited_gate_terminal(store.protocol_hash)
    store.save('sessions', 'terminal', out)
    store.lock.close()
    print('INHERITED_GATE', out['passed'], 'fresh_calls', 0, flush=True)
    return out


def run_shard(root,index,secret,transport=None,generation=None):
    saved_gate = load(root/'gate/sessions/terminal.json')
    if saved_gate != inherited_gate_terminal(digest(load(root/'gate/manifest.json'))):
        raise base.Halt('inherited gate evidence changed')
    store=open_store(root/f'profile-{index}',index)
    if list((store.root/'calls').glob('*.json')) or list((store.root/'sessions').glob('*.json')):
        raise base.Halt('shard has started; do not restart')
    backend=Backend(store,secret,'episodes',transport,generation)
    profile=design.frame()['profiles'][index]
    seed=design.inference_seed(index)
    conditions={}
    for condition,arm in design.schedule(index):
        name=f'{condition}-{arm}'
        result=(run_early(backend,profile,arm,seed) if condition=='early'
                else run_late_condition(backend,profile,arm,seed))
        result=dict(result,condition=condition,arm=arm,halt=backend.halt,
                    unsubmitted_request=backend.unsubmitted_request)
        store.save('sessions',name,result)
        conditions[name]=result['status']
        print('EPISODE',index,name,result['status'],flush=True)
        if backend.halt:
            break
    out=dict(protocol_hash=store.protocol_hash,profile=profile['name'],conditions=conditions,halt=backend.halt,
             calls=len(backend.rows()),accounted_usd=str(sum((row_cost(r) for r in backend.rows()),Decimal(0))))
    store.save('sessions','terminal',out)
    store.lock.close()
    return out


def freeze(root):
    parent=open_store(root,'coordinator')
    for index in [None]+list(range(SHARDS)):
        child=open_store(root/('gate' if index is None else f'profile-{index}'),index)
        child.lock.close()
    return parent


def worker(root,index):
    started=time.time()
    with (root/f'worker-{index}.log').open('x') as log:
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--output',str(root),'--index',str(index)],
                              cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=False)
    return dict(returncode=result.returncode,started_unix=started,finished_unix=time.time())


def execute(store, secret, gate_runner=run_gate, run_worker=worker):
    root=store.root
    if list((root/'sessions').glob('*.json')) or all_rows(root):
        raise base.Halt('execution exists; do not restart')
    probe=load(root/'network_preflight.json')
    if not probe['passed'] or not 0<=time.time()-probe['finished_unix']<=3600:
        raise base.Halt('missing, failed or stale network preflight')
    store.save('sessions','execution_started',dict(protocol_hash=store.protocol_hash,started_unix=time.time(),
                                                 preflight_hash=digest(probe)))
    gate=gate_runner(root,secret)
    done,pending,launched={}, {}, []
    next_index=0
    stopped=None if gate['passed'] else 'gate failed'
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        while pending or (next_index<SHARDS and stopped is None):
            if (root/'batch_stop.json').exists():
                stopped=stopped or 'coordinated safety/spending halt'
            while stopped is None and len(pending)<MAX_WORKERS and next_index<SHARDS:
                i=next_index;next_index+=1
                store.save('sessions',f'launch-{i}',dict(index=i,admitted_unix=time.time()))
                pending[pool.submit(run_worker,root,i)]=i
                launched.append(i)
            if not pending:
                break
            ready,_=wait(pending,timeout=1,return_when=FIRST_COMPLETED)
            for future in ready:
                i=pending.pop(future)
                try: record=future.result()
                except Exception as exc: record=dict(returncode=None,error_type=type(exc).__name__)
                done[str(i)]=record
                store.save('sessions',f'worker-{i}',record)
                if record['returncode']!=0 or not (root/f'profile-{i}/sessions/terminal.json').exists():
                    stopped=stopped or 'worker crash or missing terminal'
                    marker=root/'batch_stop.json'
                    with base.admission_lock(root/'gate'):
                        if not marker.exists():
                            with marker.open('x') as f: json.dump(dict(shard=f'profile-{i}',reason=stopped),f)
                print('WORKER',i,record['returncode'],'finished',len(done),flush=True)
    result=dict(protocol_hash=store.protocol_hash,gate_passed=gate['passed'],launched_indices=launched,
                not_started_indices=[i for i in range(SHARDS) if i not in launched],workers=done,stop_reason=stopped,
                accounted_usd=str(sum((row_cost(r) for r in all_rows(root)),Decimal(0))))
    store.save('sessions','terminal',result)
    return result


def network_preflight(root):
    """Seven minutes of unauthenticated public GETs, not a guarantee for long SSE."""
    root.mkdir(parents=True,exist_ok=True)
    target=root/'network_preflight.json'
    if target.exists():
        raise ValueError('preflight already exists; preserve it')
    started=time.time();checks=[]
    url='https://openrouter.ai/api/v1/models/deepseek/deepseek-v3.2/endpoints'
    while True:
        t=time.time()
        try:
            with urllib.request.urlopen(url,timeout=20) as response:
                data=json.load(response)
            endpoint=next(e for e in data['data']['endpoints'] if e['tag']=='atlas-cloud/fp8')
            ok=(endpoint['model_id']==old.MODEL and endpoint['provider_name']==old.PROVIDER_NAME
                and endpoint['quantization']=='fp8' and endpoint['max_completion_tokens']>=base.MAX_OUTPUT
                and Decimal(endpoint['pricing']['prompt'])*1000000<=base.PRICE_IN
                and Decimal(endpoint['pricing']['completion'])*1000000<=base.PRICE_OUT
                and {'reasoning','seed','max_tokens','top_k','min_p'}<=set(endpoint['supported_parameters']))
            checks.append(dict(started_unix=t,ok=ok,elapsed_seconds=time.time()-t))
        except Exception as exc:
            checks.append(dict(started_unix=t,ok=False,error_type=type(exc).__name__))
        if len(checks)%12==0: print('PREFLIGHT',len(checks),'failures',sum(not c['ok'] for c in checks),flush=True)
        if time.time()-started>=420:break
        time.sleep(5)
    report=dict(source=url,started_unix=started,finished_unix=time.time(),checks=checks,
                passed=all(c['ok'] for c in checks),scope='No paid inference or key; short GETs cannot certify long-stream reliability.')
    with target.open('x') as f:json.dump(report,f,indent=2)
    print('PREFLIGHT TERMINAL',report['passed'],'checks',len(checks),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--freeze-only',action='store_true')
    group.add_argument('--batch',action='store_true')
    group.add_argument('--preflight',action='store_true')
    group.add_argument('--index',type=int,choices=range(SHARDS))
    args=parser.parse_args()
    if args.preflight:
        network_preflight(args.output)
    elif args.index is not None:
        print('TERMINAL',json.dumps(run_shard(args.output,args.index,base.read_key())),flush=True)
    else:
        store=freeze(args.output)
        print('FROZEN',store.protocol_hash,flush=True)
        if args.batch:
            print('TERMINAL',json.dumps(execute(store,base.read_key())),flush=True)


if __name__=='__main__':
    main()

