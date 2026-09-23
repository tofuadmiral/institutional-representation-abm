"""Freeze all eight assigned pairs before up to four independent workers run.

No simultaneous decisions within an episode; $3 is split into eight disjoint
allocations. A terminal experiment is never restarted. Synthetic task data only.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import paper3_deepseek_fresh_profiles as study
from paper3.audit_runtime import PilotStore, digest


def freeze(root):
    root = Path(root)
    shards, all_sources = {}, set()
    for index in range(8):
        study.configure(index)
        protocol, sources = study.prepare()
        shards[str(index)] = dict(protocol=protocol,
            sources={str(p): study.hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
        all_sources.update(sources)
    all_sources.add(ROOT / 'tests/test_paper3_deepseek_fresh_batch.py')
    protocol = dict(name='eight-profile-discovery-coordinator-v1',
        shard_hashes={i:digest(m) for i,m in shards.items()},
        profile_indices=list(range(8)), max_workers=4, max_calls=400, max_usd='3.000',
        allocation_per_pair_usd='0.375',
        queue='indices0..7, admit at most4 pair processes; each pair serial and independently seeded',
        stop_policy='transport/accounting marker stops workers at next request boundary; admitted calls finish; '
            'nonzero worker exit or allocation halt prevents new shards; preserve unstarted indices and every call',
        restart_policy='no automatic resume after execution_started; no retry/repair/replacement profiles',
        evidence='fresh-profile discovery, not confirmation; complete-case summaries accompanied by all-profile missingness bounds')
    store = PilotStore(root, protocol, sorted(all_sources))
    snapshot = root / 'sources.json'
    if not snapshot.exists():
        with snapshot.open('x') as f:
            json.dump({str(p.relative_to(ROOT)):p.read_text() for p in sorted(all_sources)},f,indent=2)
    for index in range(8):
        study.configure(index)
        p,s = study.prepare()
        child = PilotStore(root/f'profile-{index}',p,s)
        if child.protocol_hash != protocol['shard_hashes'][str(index)]:
            raise ValueError('shard changed during batch freeze')
        snapshot = child.root/'sources.json'
        if not snapshot.exists():
            with snapshot.open('x') as f:
                json.dump({str(path.relative_to(ROOT)):path.read_text() for path in s},f,indent=2)
        child.lock.close()
    study.configure(0)
    return store


def worker(root, index):
    started=time.time()
    with (root/f'worker-{index}.log').open('x') as log:
        result=subprocess.run([sys.executable,str(ROOT/'experiments/paper3_deepseek_fresh_profiles.py'),
            '--output',str(root/f'profile-{index}'),'--index',str(index)],
            cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=False)
    return dict(returncode=result.returncode,started_unix=started,finished_unix=time.time())


def execute(store, run_worker=worker):
    root=store.root
    terminal=root/'sessions/terminal.json'
    if terminal.exists():
        return json.loads(terminal.read_text())
    if (root/'sessions/execution_started.json').exists() or list(root.glob('profile-*/calls/*.json')):
        raise ValueError('existing execution requires inspection; never automatically restart')
    store.save('sessions','execution_started',dict(protocol_hash=store.protocol_hash,started_unix=time.time()))
    launched, completed, pending = [], {}, {}
    next_index, stop_reason = 0, None
    with ThreadPoolExecutor(max_workers=4) as pool:
        while pending or (next_index < 8 and stop_reason is None):
            if (root/'batch_stop.json').exists():
                stop_reason=stop_reason or 'coordinated transport/accounting halt'
            while stop_reason is None and len(pending)<4 and next_index<8:
                index=next_index;next_index+=1
                store.save('sessions',f'launch-{index}',dict(index=index,admitted_unix=time.time()))
                pending[pool.submit(run_worker,root,index)]=index
                launched.append(index)
            if not pending:
                break
            done,_=wait(pending,timeout=1,return_when=FIRST_COMPLETED)
            for future in done:
                index=pending.pop(future)
                try:
                    result=future.result()
                except Exception as exc:
                    result=dict(returncode=None,error_type=type(exc).__name__)
                completed[str(index)]=result
                store.save('sessions',f'worker-{index}',result)
                path=root/f'profile-{index}/sessions/terminal.json'
                if result['returncode'] != 0 or not path.exists():
                    stop_reason=stop_reason or 'worker failed or lacks terminal record'
                elif json.loads(path.read_text())['halt']:
                    stop_reason=stop_reason or 'worker safety/allocation halt'
                print('WORKER',index,result['returncode'],'completed',len(completed),flush=True)
    result=dict(protocol_hash=store.protocol_hash,launched_indices=launched,workers=completed,
        not_started_indices=[i for i in range(8) if i not in launched],stop_reason=stop_reason)
    store.save('sessions','terminal',result)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--freeze-only',action='store_true')
    args=parser.parse_args()
    store=freeze(args.output)
    print('FROZEN BATCH',store.protocol_hash,flush=True)
    if not args.freeze_only:
        print('TERMINAL BATCH',json.dumps(execute(store)),flush=True)


if __name__=='__main__':
    main()
