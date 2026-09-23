"""Read-only eight-profile audit, including unstarted/failed pairs and bounds."""
from __future__ import annotations
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from analysis.paper3_deepseek_fresh_profiles_audit import audit as shard_audit, verify_stop
from analysis.paper3_agenda_adaptation import paired_readout
from analysis.paper3_agenda_fidelity import final_vote_fidelity
from experiments import paper3_deepseek_fresh_profiles as study
from paper3.audit_runtime import digest


def outcome_bounds(profile, episodes, stage, metric):
    """Full-menu missing-outcome bounds, not confidence intervals/imputation."""
    values=[study.game.metrics(profile,p['policy_id'])[metric] for p in profile['catalog']]
    intervals={}
    for arm in study.game.ARMS:
        episode=episodes[arm]
        observed=[e['action']['policy_id'] for e in episode.get('events',[])
            if e['stage']==stage and 'action' in e]
        if stage=='enacted' and episode['status']=='completed':
            policy=episode['resolution']['outcome']
        elif stage!='enacted' and observed:
            policy=observed[0]  # Valid locked choice survives a later episode failure.
        else:
            policy=None
        if policy is not None:
            value=study.game.metrics(profile,policy)[metric]
            intervals[arm]=(value,value)
        else:
            intervals[arm]=(min(values),max(values))
    return [intervals['B'][0]-intervals['D'][1],intervals['B'][1]-intervals['D'][0]]


def audit(root):
    root=Path(root)
    manifest=json.loads((root/'manifest.json').read_text())
    terminal=json.loads((root/'sessions/terminal.json').read_text())
    errors=[]
    try:
        verify_stop(root)
    except (ValueError,KeyError,AssertionError,OSError,TypeError) as exc:
        errors.append('invalid batch stop evidence: '+type(exc).__name__)
    snapshots=json.loads((root/'sources.json').read_text())
    for p,sha in manifest['sources'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=sha:
            errors.append('changed frozen source: '+p)
        if hashlib.sha256(snapshots[str(Path(p).relative_to(ROOT))].encode()).hexdigest()!=sha:
            errors.append('source snapshot mismatch: '+p)
    if terminal['protocol_hash']!=digest(manifest):
        errors.append('batch terminal hash mismatch')
    launched=terminal['launched_indices'];not_started=terminal['not_started_indices']
    if launched!=list(range(len(launched))) or sorted(launched+not_started)!=list(range(8)):
        errors.append('assignment/launch order mismatch')
    if set(terminal['workers'])!={str(i) for i in launched}:
        errors.append('missing or extra worker records')
    if not_started and terminal['stop_reason'] is None:
        errors.append('unstarted profiles without safety halt')
    reports, pairs, bounds, rows, fidelity, overlong, membership = {}, {}, {}, [], {}, {}, {}
    if {p.name for p in root.glob('profile-*') if p.is_dir()}!={f'profile-{i}' for i in range(8)}:
        errors.append('unexpected or missing profile directories')
    for index in range(8):
        shard=root/f'profile-{index}'
        sm=json.loads((shard/'manifest.json').read_text())
        if digest(sm)!=manifest['protocol']['shard_hashes'][str(index)]:
            errors.append(f'shard manifest mismatch:{index}')
        ss=json.loads((shard/'sources.json').read_text())
        for path,sha in sm['sources'].items():
            if hashlib.sha256(ss[str(Path(path).relative_to(ROOT))].encode()).hexdigest()!=sha:
                errors.append(f'shard{index}:source snapshot mismatch:{path}')
        study.configure(index)
        if sm['protocol']!=study.prepare()[0]:
            errors.append(f'shard protocol mismatch:{index}')
        profile=sm['protocol']['fresh_frame'][index]
        if index in launched:
            try:
                report=shard_audit(shard)
                reports[str(index)]=report
                errors.extend(f'shard{index}:{e}' for e in report['integrity_errors'])
            except (ValueError,KeyError,AssertionError,OSError,TypeError) as exc:
                errors.append(f'shard{index}:incomplete audit ({type(exc).__name__})')
            if terminal['workers'][str(index)]['returncode']!=0:
                errors.append(f'shard{index}:nonzero or unknown exit')
        elif list((shard/'calls').glob('*.json')) or list((shard/'sessions').glob('*.json')):
            errors.append(f'unstarted shard{index} has execution records')
        episodes={}
        for arm in study.game.ARMS:
            path=shard/'sessions'/f"generated-{study.PROFILE_SEEDS[index]}-s{241000+index*1000}-{arm}.json"
            episodes[arm]=json.loads(path.read_text()) if path.exists() else dict(
                profile=profile,arm=arm,status='not_started')
        pairs[str(index)]=paired_readout(episodes)
        membership[str(index)]={}
        sets=sm['protocol']['set_valued_objective_benchmarks'][index]
        for arm,e in episodes.items():
            choices=[event['action']['policy_id'] for event in e.get('events',[])
                if event['stage']=='locked_proposal']
            policy=choices[0] if choices else None
            membership[str(index)][arm]=dict(observed_locked_policy=policy,
                scripted_own_optimum_compatible=policy in sets['arms'][arm]['own_best_proposals'] if policy is not None else None,
                scripted_group_optimum_compatible=policy in sets['arms'][arm]['group_best_proposals'] if policy is not None else None)
        fidelity[str(index)]={arm:final_vote_fidelity(profile,arm,e['events'])
            for arm,e in episodes.items() if e['status']=='completed'}
        overlong[str(index)]={arm:sum(bool(a.get('overlong_message')) for a in e.get('actions',[]))
            for arm,e in episodes.items()}
        bounds[str(index)]=dict(
            locked_leader_advantage_B_minus_D=outcome_bounds(profile,episodes,'locked_proposal','leader_advantage'),
            enacted_mean_regret_B_minus_D=outcome_bounds(profile,episodes,'enacted','mean_regret'))
        rows.extend(json.loads(p.read_text()) for p in (shard/'calls').glob('*.json'))
    total=sum((study.ledger(rows,phase)[1] for phase in study.LIMITS),Decimal(0))
    if len(rows)>400 or total>Decimal('3'):
        errors.append('batch call or budget cap exceeded')
    keys=[digest(dict(request=r['request'],phase=r['phase'],protocol=r['protocol_hash'])) for r in rows]
    if len(keys)!=len(set(keys)):
        errors.append('duplicate request records')
    if list(root.rglob('*.partial')):
        errors.append('partial writes remain')
    if (root/'batch_stop.json').exists():
        marker=json.loads((root/'batch_stop.json').read_text())
        if any(row['started_unix']>marker['created_unix'] for row in rows):
            errors.append('request admitted after coordinated stop')
    if terminal['stop_reason'] is not None and not ((root/'batch_stop.json').exists()
            or any(r['terminal']['halt'] for r in reports.values())
            or any(w['returncode']!=0 for w in terminal['workers'].values())):
        errors.append('coordinator halt lacks an observed cause')
    prior=Decimal(json.loads((root/'profile-0/manifest.json').read_text())['protocol']['prerequisite']['prior_conservative_usd'])
    if prior+total>Decimal('10'):
        errors.append('cumulative additional allowance exceeded')
    timeline=[]
    for row in rows:
        if 'elapsed_seconds' in row:
            timeline.extend([(row['started_unix'],1),(row['started_unix']+row['elapsed_seconds'],-1)])
    simultaneous=peak=0
    for _,change in sorted(timeline):
        simultaneous+=change;peak=max(peak,simultaneous)
    if peak>4:
        errors.append('more than4 overlapping inference calls')
    complete=[p for p in pairs.values() if p['complete_pair']]
    endpoints=('locked_leader_advantage_B_minus_D','enacted_mean_regret_B_minus_D')
    return dict(protocol_hash=digest(manifest),integrity_errors=errors,calls=len(rows),
        total_accounted_usd=str(total),cumulative_additional_accounted_usd=str(prior+total),
        maximum_recorded_call_overlap=peak,assigned_profiles=8,complete_pairs=len(complete),
        feasibility_threshold_met=len(complete)>=7,
        complete_pair_descriptive_means={k:sum(p['primary_endpoints'][k] for p in complete)/len(complete)
            if complete else None for k in endpoints},
        all_eight_profile_missingness_bounds={k:[sum(b[k][i] for b in bounds.values())/8 for i in (0,1)] for k in endpoints},
        pair_missingness_bounds=bounds,pairs=pairs,shards=reports,
        completed_episode_final_vote_fidelity=fidelity,overlong_public_messages=overlong,
        secondary_scripted_objective_compatibility=membership,
        scope='Discovery, not confirmation. Bounds cover missing outcomes over each finite policy menu, not sampling uncertainty. '
            'One requested seed pair per profile; no call-level independence or causal-mediation claim.')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    if args.archive:
        from experiments.paper3_archive_agenda import archive
        print(json.dumps(archive(args.root,args.archive,report_fn=audit),indent=2))
    else:
        report=audit(args.root)
        print(json.dumps(report,indent=2));sys.exit(bool(report['integrity_errors']))
