"""Offline same-batch two-form replay, fresh gate and all-assigned readout.

No API calls. Uses matching frozen local sources. Incomplete profiles are retained
with finite-menu bounds, not imputed or reported as population confidence intervals.
"""
from __future__ import annotations
import argparse
from collections import Counter
from analysis.paper3_identification_report import usage_summary
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from experiments import paper3_disclosure_presentation as run
from paper3.audit_runtime import digest
from analysis.paper3_deepseek_disclosure_audit import bounds
from paper3 import agenda_rights as game
from paper3 import agenda_weak_preferences as weak
from analysis.paper3_disclosure_choice_audit import episode_report


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
    require(key==digest(dict(request=row['request'],phase=phase,protocol=ph,attempt=row['attempt'],
                            decision_id=row['decision_id'])),'call key mismatch')
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
            key=digest(dict(request=request,phase=self.phase,protocol=self.ph,attempt=attempt,
                            decision_id=case['decision_id']))
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
            seed=run.design.inference_seed(index)
            value=(run.run_early(backend,profile,arm,seed) if condition=='early'
                   else run.run_late_condition(backend,profile,arm,seed))
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


def planning_diagnostics(profile, condition, policy):
    certificate=weak.certificate(profile)
    require(certificate['identified'],'fixture no longer outcome-identified')
    predictions=certificate['predictions']
    key=condition.removeprefix('early-')
    payoffs={p:Fraction(v) for p,v in predictions['own_payoffs_exact'][key].items()}
    u=profile['utilities'][profile['leader']]
    return dict(locked=policy,own_compatible=policy in predictions['own_best'][key],
        group_compatible=policy in predictions['group_best'][key],
        myopic_compatible=policy in predictions['ratification_only_best'],
        own_best=predictions['own_best'][key],group_best=predictions['group_best'][key],
        myopic_best=predictions['ratification_only_best'],
        benchmark_planning_regret_normalized_exact=str((max(payoffs.values())-payoffs[policy])/(max(u.values())-min(u.values()))),
        scope='Conditional benchmark planning loss, not empirical counterfactual or motive.')


def episode_diagnostics(profile, arm, episode):
    # Independently reconstruct resolution from public events.
    result=episode_report(profile,arm,episode)
    ids=[p['policy_id'] for p in profile['catalog']]
    possible={a:weak.selector_outcomes(profile,arm,result['locked'],a) for a in ids}
    u=profile['utilities'][profile['sponsor']]
    floor=max(min(u[o] for o in options) for options in possible.values())
    ceiling=max(max(u[o] for o in options) for options in possible.values())
    actual=possible[result['amendment']]
    result.update(sponsor_amendment_optimal_for_some_ties=max(u[o] for o in actual)>=floor,
                  sponsor_amendment_optimal_for_all_ties=min(u[o] for o in actual)>=
                  max((max(u[o] for o in options) for a,options in possible.items()
                       if a!=result['amendment']),default=min(u[o] for o in actual)),
                  sponsor_best_payoff_bounds=[floor,ceiling],
                  enacted=game.metrics(profile,result['outcome']),
                  passed=episode['resolution']['passed'])
    return result


def profile_readout(root,index):
    profile=run.design.frame()['profiles'][index]
    outcomes={'early':{},'late':{}};locks={};episodes={}
    for condition,arm in run.design.schedule(index):
        path=root/f'profile-{index}/sessions/{condition}-{arm}.json'
        if not path.exists(): continue
        s=run.load(path)
        if condition=='early':
            for a in s.get('actions',[]):
                if a['stage']=='locked_proposal':locks[f'early-{arm}']=a['action']['policy_id']
            if s['status']=='completed':
                outcomes['early'][arm]=s['resolution']['outcome']
                episodes['early-'+arm]=episode_diagnostics(profile,arm,s)
        else:
            if s.get('locked_proposal'):locks['late']=s['locked_proposal']
            for a,b in s.get('branches',{}).items():
                if b['status']=='completed':
                    outcomes['late'][a]=b['resolution']['outcome']
                    episodes['late-'+a]=episode_diagnostics(profile,a,b)
    complete=all(set(c)==set('DB') for c in outcomes.values())
    u=profile['utilities'][profile['leader']]
    low=high=Fraction(0)
    for c in ('early','late'):
        for a in 'DB':
            coeff=Fraction(1 if c=='early' else -1,2*(max(u.values())-min(u.values())))
            vals=[coeff*u[outcomes[c][a]]] if a in outcomes[c] else [coeff*v for v in u.values()]
            low+=min(vals);high+=max(vals)
    assignment=run.design.assignment(index)
    row=dict(seed=run.design.PROFILE_SEED,stratum='positive',form=assignment['form'],
             pair=assignment['pair'],wave=assignment['wave'],
             block_index=index,replicate=assignment['pair'],inference_seed=run.design.inference_seed(index),
             complete=complete,locked=locks,outcomes=outcomes,episodes=episodes,
             planning={c:planning_diagnostics(profile,c,p) for c,p in locks.items()},
             information_benefit_bounds_exact=[str(low),str(high)],interaction_bounds=bounds(profile,outcomes))
    if complete:
        row['interaction']=run.old.late.interaction(profile,outcomes)
        changes={}
        for r,utilities in profile['utilities'].items():
            value=Fraction(sum(utilities[outcomes['early'][a]]-utilities[outcomes['late'][a]] for a in 'DB'),2)
            changes[r]=dict(raw_exact=str(value),normalized_exact=str(value/(max(utilities.values())-min(utilities.values()))))
        row['early_minus_late_expected_utilities']=changes
        expected=Fraction(run.design.frame()['predictions'][row['form']]['predictions']['normalized_information_value_exact'])
        row['information_benefit_discrepancy_exact']=str(low-expected)
        row['information_benefit_absolute_discrepancy_exact']=str(abs(low-expected))
    inverse=run.design.inverse_mapping(index)
    row['original_label_locks']={c:inverse[p] for c,p in locks.items()}
    row['original_label_outcomes']={c:{a:inverse[p] for a,p in values.items()} for c,values in outcomes.items()}
    return row


def benchmark_reproduced(p):
    return (p['complete'] and len(p['planning'])==3
        and all(d['own_compatible'] for d in p['planning'].values())
        and all(c in p['planning'] and not p['planning'][c]['group_compatible']
                and not p['planning'][c]['myopic_compatible'] for c in ('early-B','late'))
        and p['original_label_outcomes']=={'early':{'D':'p2','B':'q'},'late':{'D':'q','B':'q'}}
        and p['information_benefit_bounds_exact']==['3/38','3/38'])


def paired_readout(profiles, errors):
    pairs=[]
    for pair in range(run.design.PAIR_COUNT):
        rows={p['form']:p for p in profiles if p['pair']==pair}
        original,mapped=rows['original'],rows['mapped']
        ol,oh=map(Fraction,original['information_benefit_bounds_exact'])
        ml,mh=map(Fraction,mapped['information_benefit_bounds_exact'])
        pairs.append(dict(pair=pair,inference_seed=original['inference_seed'],
            original_index=original['block_index'],mapped_index=mapped['block_index'],
            complete=original['complete'] and mapped['complete'],
            original_benefit_bounds_exact=[str(ol),str(oh)],
            mapped_benefit_bounds_exact=[str(ml),str(mh)],
            mapped_minus_original_bounds_exact=[str(ml-oh),str(mh-ol)]))
    forms={}
    for form in run.design.FORMS:
        rows=[p for p in profiles if p['form']==form]
        forms[form]=dict(assigned_blocks=len(rows),complete_blocks=sum(p['complete'] for p in rows),
            benchmark_reproducing_blocks=sum(benchmark_reproduced(p) for p in rows),
            observed_benefits_exact=sorted({p['information_benefit_bounds_exact'][0]
                for p in rows if p['complete']},key=Fraction),
            mean_benefit_bounds_exact=[str(sum(Fraction(p['information_benefit_bounds_exact'][j])
                for p in rows)/len(rows)) for j in (0,1)],
            observed_locks=sum(len(p['planning']) for p in rows),assigned_locks=3*len(rows),
            own_compatible_locks=sum(d['own_compatible'] for p in rows for d in p['planning'].values()))
    complete=len(profiles)==8 and all(p['complete'] for p in profiles) and not errors
    all_fit={f:complete and forms[f]['benchmark_reproducing_blocks']==4 for f in forms}
    if not complete:
        interpretation='incomplete_or_integrity_failure_no_unqualified_paired_readout'
    elif all(all_fit.values()):
        interpretation='both_forms_reproduce_at_all_four_sampled_seeds_not_equivalence'
    elif all_fit['original']:
        interpretation='original_reproduces_mapped_does_not_in_this_sample'
    else:
        interpretation='original_not_stable_at_all_four_sampled_seeds_not_mapping_specific'
    same_sign=None
    if complete:
        differences=[Fraction(p['mapped_minus_original_bounds_exact'][0]) for p in pairs]
        same_sign=('negative' if all(d<0 for d in differences) else
                   'positive' if all(d>0 for d in differences) else
                   'all_zero' if all(d==0 for d in differences) else 'mixed_or_tied')
    return dict(pairs=pairs,forms=forms,all_assigned_complete_and_clean=complete,
        mean_paired_difference_bounds_exact=[str(sum(Fraction(p['mapped_minus_original_bounds_exact'][j])
            for p in pairs)/len(pairs)) for j in (0,1)],
        paired_difference_sign=same_sign,interpretation=interpretation,
        scope='All four assigned seed pairs on one selected game; descriptive, not a population test or equivalence claim. '
              'Finite-menu bounds, not confidence intervals. A consistent sign does not by itself establish a stable label-only effect.')


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
        for i in launched:
            if i>=run.design.WAVE_SIZE:
                require(all(str(j) in terminal['workers'] for j in range(run.design.WAVE_SIZE)),
                        'second wave without completed first wave')
                first_end=max(terminal['workers'][str(j)]['finished_unix'] for j in range(run.design.WAVE_SIZE))
                require(run.load(root/f'sessions/launch-{i}.json')['admitted_unix']>=first_end,
                        'second wave admitted before first wave finished')
        require({p.stem for p in (root/'sessions').glob('*.json')}==known,'coordinator session inventory mismatch')
        require({p.name for p in root.glob('profile-*') if p.is_dir()}=={f'profile-{i}' for i in range(run.SHARDS)},
                'profile directory inventory mismatch')
    except (ValueError,KeyError,TypeError,OSError) as exc:errors.append('coordinator terminal: '+str(exc))
    return dict(integrity_errors=errors,shards=shards,calls=len(rows),accounted_usd=str(cost),
        cumulative_additional_usd=str(run.PRIOR+cost),complete_profiles=sum(p['complete'] for p in profiles),
        complete_blocks=sum(p['complete'] for p in profiles),base_profiles=1,
        usage=usage_summary(rows), presentation_diagnostic=paired_readout(profiles,errors),
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
