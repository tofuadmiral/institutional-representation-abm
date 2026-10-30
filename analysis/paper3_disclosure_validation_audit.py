"""Offline held-out validation replay and all-assigned-profile descriptive readout.

No API calls. Uses matching frozen local sources. Incomplete profiles are retained
with finite-menu bounds, not imputed or reported as population confidence intervals.
"""
from __future__ import annotations
import argparse
from collections import Counter
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from experiments import paper3_disclosure_validation as run
from paper3.audit_runtime import digest
from analysis.paper3_deepseek_disclosure_audit import bounds
from analysis.paper3_disclosure_readout import readout


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sources(root,index):
    manifest=run.load(root/'manifest.json')
    require(manifest['protocol']==run.protocol(index),'protocol mismatch')
    expected={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in run.sources()}
    require(manifest['sources']==expected,'source hash mismatch')
    snapshot=run.load(root/'sources.json')
    require(set(snapshot)=={str(p.relative_to(run.ROOT)) for p in run.sources()},'snapshot inventory mismatch')
    for p in run.sources():
        require(hashlib.sha256(snapshot[str(p.relative_to(run.ROOT))].encode()).hexdigest()==expected[str(p)],
                'source snapshot mismatch')
    return digest(manifest)


def record_check(key,row,ph,phase):
    require(row['status']=='recorded','started request remains; not terminal')
    require(row['protocol_hash']==ph and row['phase']==phase,'record protocol mismatch')
    require(row['attempt'] in (1,2),'invalid attempt')
    require(key==digest(dict(request=row['request'],phase=phase,protocol=ph,attempt=row['attempt'])),'call key mismatch')
    require(json.loads(row['request_text'])==row['request'],'wire/object mismatch')
    bound,reserve=run.base.reserve_for(row['request'])
    require(row['input_token_bound']==bound and Decimal(row['reserved_usd'])==reserve,'reservation mismatch')
    try: response,complete=run.old.assemble(row['stream_lines'])
    except (ValueError,TypeError): response,complete={},False
    require(response==row['response'],'stream/response mismatch')
    require(not row.get('secret_redacted'),'credential echo')
    if row.get('outcome')=='answered':
        require(complete and row['http_status']==200,'incomplete answered call')
        require(row['generation_id']==response['id'],'generation id mismatch')
        require(str(run.base.accounting(row))==row['verified_cost_usd'],'cost mismatch')
        require(not row.get('accounting_error'),'answered accounting error')
    elif row.get('outcome')=='transport_certified':
        receipt=row['generation_receipt']
        require(receipt['id']==row['generation_id'] and receipt['model']==run.old.MODEL,'receipt identity mismatch')
        require(str(run.old.certify(receipt,row))==row['certified_cost_usd'],'receipt cost mismatch')
        require(not (complete and row['http_status']==200 and not row.get('transport_error')),
                'unjustified transport reissue')
    else:
        require(bool(row.get('accounting_error')) and bool(row.get('halt_reason')),'unexplained failure')
        require('verified_cost_usd' not in row and 'certified_cost_usd' not in row,'failure cost not reserved')
        if complete and row['http_status']==200 and not row.get('transport_error'):
            failed=row['generation_id']!=response.get('id')
            try: run.base.accounting(row)
            except (ValueError,KeyError,TypeError,ArithmeticError): failed=True
            require(failed,'accounting failure did not reproduce')
        else:
            receipt=row.get('generation_receipt')
            failed=not receipt or receipt.get('id')!=row['generation_id'] or receipt.get('model')!=run.old.MODEL
            try: run.old.certify(receipt,row)
            except (ValueError,KeyError,TypeError,ArithmeticError): failed=True
            require(failed,'certification failure did not reproduce')
    return run.row_cost(row)


class Replay:
    def __init__(self,records,ph,phase):
        self.records,self.ph,self.phase=records,ph,phase
        self.used=[]
        self.halt=None
        self.unsubmitted_request=None
        self.expected_unsubmitted=None

    def call(self,case):
        if self.halt:
            raise run.base.Halt(self.halt)
        request=run.request_for(case)
        for attempt in (1,2):
            key=digest(dict(request=request,phase=self.phase,protocol=self.ph,attempt=attempt))
            if key not in self.records:
                saved=self.expected_unsubmitted
                require(saved and saved['case']==case and saved['attempt']==attempt,'missing exact request')
                require(saved['reason'] in ('coordinated batch safety halt','phase spending ceiling reached',
                    'shared spending ceiling reached','authorized call ceiling reached','request exceeds frozen byte bound'),
                    'unknown admission failure')
                self.halt=saved['reason'];self.unsubmitted_request=saved
                raise run.base.Halt(self.halt)
            row=self.records[key]
            require(row['request']==request and row['request_text']==run.base.encoded_request(request),
                    'exact serialized request mismatch')
            self.used.append(key)
            if row.get('accounting_error'):
                self.halt=row['halt_reason']
                raise run.base.Halt(self.halt)
            if row.get('outcome')=='transport_certified':
                continue
            return key,row
        raise run.old.TransportFailed('transport failed on both declared attempts')


def verify_shard(root,index):
    ph=sources(root,index)
    phase='gate' if index is None else 'episodes'
    records={p.stem:run.load(p) for p in (root/'calls').glob('*.json')}
    sessions={p.stem:run.load(p) for p in (root/'sessions').glob('*.json')}
    cost=sum((record_check(k,r,ph,phase) for k,r in records.items()),Decimal(0))
    backend=Replay(records,ph,phase)
    known={'terminal'}
    if not sessions and not records:
        return dict(state='not_started',calls=0,accounted_usd='0')
    terminal=sessions['terminal']
    if index is None:
        checks=[]
        backend.expected_unsubmitted=terminal['unsubmitted_request']
        for case in run.gate_cases():
            try:
                key,raw=run.old.answer(backend,case)
                expected=dict(run.old.gate_score(raw,case['expected']),name=case['name'],call_key=key)
            except run.base.Halt: break
            except ValueError as exc:
                expected=dict(status='failed',valid=False,exact=False,error=str(exc),name=case['name'])
            require(sessions[case['name']]==expected,'gate replay mismatch')
            known.add(case['name']);checks.append(expected)
        expected=dict(protocol_hash=ph,passed=len(checks)==8 and all(c['valid'] and c['exact'] for c in checks),
            checks=len(checks),valid=sum(c['valid'] for c in checks),exact=sum(c['exact'] for c in checks),
            halt=backend.halt,unsubmitted_request=backend.unsubmitted_request,accounted_usd=str(cost))
    else:
        profile=run.design.frame()['profiles'][index]
        conditions={}
        for condition,arm in run.design.schedule(index):
            name=f'{condition}-{arm}'
            saved=sessions[name]
            backend.expected_unsubmitted=saved['unsubmitted_request']
            seed=run.SEED_BASE+1000*index
            value=(run.old.run_early(backend,profile,arm,seed) if condition=='early'
                   else run.old.run_late_condition(backend,profile,arm,seed))
            expected_session=dict(value,condition=condition,arm=arm,halt=backend.halt,
                                  unsubmitted_request=backend.unsubmitted_request)
            require(expected_session==saved,'episode replay mismatch: '+name)
            known.add(name);conditions[name]=value['status']
            if backend.halt: break
        expected=dict(protocol_hash=ph,profile=profile['name'],conditions=conditions,halt=backend.halt,
                      calls=len(records),accounted_usd=str(cost))
    require(expected==terminal,'terminal mismatch')
    require(set(sessions)==known,'session inventory mismatch')
    require(Counter(backend.used)==Counter({k:1 for k in records}),'unattached/duplicate calls')
    require(len(records)<=(16 if index is None else 182),'call limit exceeded')
    require(cost<=(Decimal('0.1') if index is None else run.CAP),'shard cost limit exceeded')
    ordered=[records[k] for k in backend.used]
    require(all(b['started_unix']>=a['started_unix']+a['elapsed_seconds'] for a,b in zip(ordered,ordered[1:])),
            'overlapping or out-of-order shard requests')
    require(not list(root.rglob('*.partial')),'partial writes remain')
    return dict(state='terminal',calls=len(records),accounted_usd=str(cost),halt=terminal.get('halt'))


def profile_readout(root,index):
    profile=run.design.frame()['profiles'][index]
    outcomes={'early':{},'late':{}};locks={}
    for condition,arm in run.design.schedule(index):
        path=root/f'profile-{index}/sessions/{condition}-{arm}.json'
        if not path.exists(): continue
        s=run.load(path)
        if condition=='early':
            for a in s.get('actions',[]):
                if a['stage']=='locked_proposal':locks[f'early-{arm}']=a['action']['policy_id']
            if s['status']=='completed':outcomes['early'][arm]=s['resolution']['outcome']
        else:
            if s.get('locked_proposal'):locks['late']=s['locked_proposal']
            for a,b in s.get('branches',{}).items():
                if b['status']=='completed':outcomes['late'][a]=b['resolution']['outcome']
    complete=all(set(c)==set('DB') for c in outcomes.values())
    u=profile['utilities'][profile['leader']]
    low=high=Fraction(0)
    for c in ('early','late'):
        for a in 'DB':
            coeff=Fraction(1 if c=='early' else -1,2*(max(u.values())-min(u.values())))
            vals=[coeff*u[outcomes[c][a]]] if a in outcomes[c] else [coeff*v for v in u.values()]
            low+=min(vals);high+=max(vals)
    row=dict(seed=run.design.frame()['seeds'][index],stratum='positive' if index%2==0 else 'zero_control',
             complete=complete,locked=locks,outcomes=outcomes,
             information_benefit_bounds_exact=[str(low),str(high)],interaction_bounds=bounds(profile,outcomes))
    if complete:
        row['interaction']=run.old.late.interaction(profile,outcomes)
        row['diagnostics']=readout(profile,locks,outcomes)
    return row


def audit(root):
    root=Path(root);errors=[];shards={}
    try: sources(root,'coordinator')
    except (ValueError,KeyError,TypeError,OSError) as exc:errors.append('coordinator: '+str(exc))
    for index in [None]+list(range(run.SHARDS)):
        name='gate' if index is None else f'profile-{index}'
        try: shards[name]=verify_shard(root/name,index)
        except (ValueError,KeyError,TypeError,IndexError,OSError,ArithmeticError) as exc:
            errors.append(name+': '+str(exc))
    rows=run.all_rows(root)
    cost=sum((run.row_cost(r) for r in rows),Decimal(0))
    if cost>run.CAP or run.PRIOR+cost>run.AUTHORIZED or len(rows)>run.MAX_CALLS:
        errors.append('aggregate budget exceeded')
    profiles=[profile_readout(root,i) for i in range(run.SHARDS)]
    try:
        terminal=run.load(root/'sessions/terminal.json')
        start=run.load(root/'sessions/execution_started.json')
        ph=digest(run.load(root/'manifest.json'))
        require(start['protocol_hash']==terminal['protocol_hash']==ph,'coordinator protocol mismatch')
        require(start['preflight_hash']==digest(run.load(root/'network_preflight.json')),'preflight changed')
        require(Decimal(terminal['accounted_usd'])==cost,'coordinator cost mismatch')
        launched=terminal['launched_indices']
        require(launched==list(range(len(launched))) and len(launched)<=run.SHARDS,'launch order mismatch')
        require(terminal['not_started_indices']==list(range(len(launched),run.SHARDS)),'unstarted inventory mismatch')
        require(set(terminal['workers'])=={str(i) for i in launched},'worker inventory mismatch')
        known={'terminal','execution_started'}
        gate=run.load(root/'gate/sessions/terminal.json')
        require(gate['passed']==terminal['gate_passed'],'coordinator gate mismatch')
        require(gate['passed'] or not launched,'episodes ran after gate failed')
        for i in launched:
            require(run.load(root/f'sessions/launch-{i}.json')['index']==i,'launch index mismatch')
            require(run.load(root/f'sessions/worker-{i}.json')==terminal['workers'][str(i)],'worker record mismatch')
            known.update({f'launch-{i}',f'worker-{i}'})
        require({p.stem for p in (root/'sessions').glob('*.json')}==known,'coordinator session inventory mismatch')
        require({p.name for p in root.glob('profile-*') if p.is_dir()}=={f'profile-{i}' for i in range(run.SHARDS)},
                'profile directory inventory mismatch')
    except (ValueError,KeyError,TypeError,OSError) as exc:errors.append('coordinator terminal: '+str(exc))
    return dict(integrity_errors=errors,shards=shards,calls=len(rows),accounted_usd=str(cost),
        cumulative_additional_usd=str(run.PRIOR+cost),complete_profiles=sum(p['complete'] for p in profiles),
        profiles=profiles,scope=run.design.frame()['inference_scope'],
        limitations='Matching local source replay, not portable reproduction or provider-internal verification. '
        'Admission-failure reasons replay from saved unsubmitted requests; aggregate final costs checked. '
        'Shared budget safety is enforced atomically by the runner, not inferred from final completion timestamps.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    report=audit(parser.parse_args().root)
    print(json.dumps(report,indent=2))
    raise SystemExit(bool(report['integrity_errors']))
