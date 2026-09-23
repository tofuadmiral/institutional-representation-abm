import json
from pathlib import Path
import threading
import time
import pytest
from experiments import paper3_deepseek_fresh_profiles as study
from experiments import paper3_deepseek_fresh_batch as batch
from analysis.paper3_deepseek_fresh_batch_audit import audit,outcome_bounds
from paper3.audit_runtime import PilotStore
from tests.test_paper3_deepseek_fresh_profiles import prerequisite_fixture,transport


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    monkeypatch.setattr(study,'prerequisite',prerequisite_fixture)
    study.configure(0)
    yield
    study.configure(0)


def fake_worker(root,index,fn=transport):
    start=time.time()
    path=root/f'profile-{index}'
    manifest=json.loads((path/'manifest.json').read_text());p=manifest['protocol']
    store=PilotStore(path,p,[Path(s) for s in manifest['sources']])
    backend=study.Backend(store,'TEST_SECRET_NOT_REAL',fn)
    statuses={}
    for spec in p['episodes']:
        r=dict(study.run_one(backend,spec),protocol_hash=store.protocol_hash)
        store.save('sessions',spec['name'],r)
        statuses[spec['name']]=r['status']
        if backend.halt:break
    terminal=dict(protocol_hash=store.protocol_hash,gate_passed=True,checks=0,
        gate_reused_from=p['inherited_gate_protocol'],valid=0,exact=0,
        episodes=statuses,halt=backend.halt,
        budgets={phase:dict(calls=study.ledger(backend.rows(),phase)[0],
            accounted_usd=str(study.ledger(backend.rows(),phase)[1])) for phase in study.LIMITS})
    store.save('sessions','terminal',terminal);store.lock.close()
    return dict(returncode=0,started_unix=start,finished_unix=time.time())


def test_eight_profile_freeze_parallel_limit_full_replay_and_idempotence(tmp_path):
    store=batch.freeze(tmp_path)
    lock=threading.Lock();active=peak=0;called=[]
    def worker(root,index):
        nonlocal active,peak
        assert all((root/f'profile-{i}/manifest.json').is_file() for i in range(8))
        with lock:
            active+=1;peak=max(peak,active);called.append(index)
        time.sleep(.005)
        try:return fake_worker(root,index)
        finally:
            with lock:active-=1
    terminal=batch.execute(store,worker)
    assert sorted(called)==list(range(8)) and 1<peak<=4
    assert terminal['not_started_indices']==[] and terminal['stop_reason'] is None
    r=audit(tmp_path)
    assert r['integrity_errors']==[] and r['calls']==400 and r['complete_pairs']==8
    assert r['feasibility_threshold_met']
    assert float(r['total_accounted_usd'])==pytest.approx(.96)
    assert all(set(v)=={'D','B'} for v in r['completed_episode_final_vote_fidelity'].values())
    assert all(x['strictly_harmful_own_votes']==0 for v in r['completed_episode_final_vote_fidelity'].values() for x in v.values())
    assert all(v['observed_locked_policy'] is not None for pair in r['secondary_scripted_objective_compatibility'].values() for v in pair.values())
    for name,value in r['complete_pair_descriptive_means'].items():
        assert r['all_eight_profile_missingness_bounds'][name]==pytest.approx([value,value])
    assert batch.execute(store,worker)==terminal and len(called)==8


def test_batch_safety_halt_retains_assigned_unstarted_profiles(tmp_path):
    store=batch.freeze(tmp_path)
    def worker(root,index):
        def fail(text,secret):return 429,'{"error":"unavailable"}','HTTPError'
        return fake_worker(root,index,fail)
    terminal=batch.execute(store,worker)
    assert terminal['stop_reason'] and terminal['launched_indices']==[0,1,2,3]
    assert terminal['not_started_indices']==[4,5,6,7]
    r=audit(tmp_path)
    assert r['integrity_errors']==[] and r['complete_pairs']==0 and 1<=r['calls']<=4
    assert not r['feasibility_threshold_met'] and len(r['pairs'])==8
    assert all(v is None for v in r['complete_pair_descriptive_means'].values())
    assert r['all_eight_profile_missingness_bounds']['enacted_mean_regret_B_minus_D'][0]<0


def test_interrupted_coordinator_never_relaunches(tmp_path):
    store=batch.freeze(tmp_path)
    store.save('sessions','execution_started',{'fixture':True})
    with pytest.raises(ValueError,match='never automatically restart'):
        batch.execute(store,lambda *_:pytest.fail('must not launch'))


def test_missing_bounds_cover_menu_not_zero_imputation():
    profile=study.generated_profile(1002000)
    missing={arm:dict(status='not_started') for arm in study.game.ARMS}
    low,high=outcome_bounds(profile,missing,'enacted','mean_regret')
    assert low<0<high and low==pytest.approx(-high)
    for arm,p in [('D','p1'),('B','p2')]:
        missing[arm]=dict(status='failed',events=[dict(stage='locked_proposal',action={'policy_id':p})])
    low,high=outcome_bounds(profile,missing,'locked_proposal','leader_advantage')
    expected=study.game.metrics(profile,'p2')['leader_advantage']-study.game.metrics(profile,'p1')['leader_advantage']
    assert [low,high]==pytest.approx([expected,expected])
