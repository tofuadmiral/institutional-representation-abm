"""Fabricated model responses only. No provider calls or credentials."""
import json
from decimal import Decimal
import time
import pytest

from experiments import paper3_disclosure_identification as run
from analysis import paper3_disclosure_identification_audit as auditor
from tests.test_paper3_deepseek_disclosure_a3 import fake_model as old_fake, stream, ok, reset, SECRET
from paper3.audit_runtime import PilotStore


def fake(wire,secret):
    request=json.loads(wire)
    gate={c['seed']:c for c in run.gate_cases()}
    if request['seed'] in gate:
        return ok(stream(json.dumps(gate[request['seed']]['expected'])))
    return old_fake(wire,secret)


def receipt(gid,secret):
    return dict(id=gid,model=run.old.MODEL,provider_name=run.old.PROVIDER_NAME,total_cost=0.0002)


def case():
    return dict(name='synthetic',decision_id='synthetic:0',seed=1,messages=[dict(role='user',content='synthetic')])


def test_fixed_frame_separates_myopia_and_balances_order():
    frame=run.design.frame()
    assert frame['seeds']==[1006576,1006006,1006576,1006006]
    assert [run.design.inference_seed(i) for i in range(4)]==[301000,301100,302000,302100]
    for parity in (0,1):
        orders=[next(a for c,a in run.design.schedule(i) if c=='late') for i in range(parity,4,2)]
        assert sorted(orders)==['BD','DB']
        early=[''.join(a for c,a in run.design.schedule(i) if c=='early') for i in range(parity,4,2)]
        assert early==['DB','BD']
    assert run.PRIOR+run.CAP==Decimal('4.584369882')
    assert run.MAX_CALLS==744
    assert run.request_for(case())['reasoning']==dict(enabled=True,exclude=False)


def test_receipt_saved_and_reissue_is_identical_even_with_partial_text(tmp_path):
    store=PilotStore(tmp_path/'profile-0',dict(fake=True),[])
    wires=[]
    def transport(wire,secret):
        wires.append(wire)
        return reset(stream('partial final answer')[:-2]) if len(wires)==1 else ok(stream('{"policy_id":"p1"}'))
    backend=run.Backend(store,SECRET,'episodes',transport,receipt)
    run.old.answer(backend,case())
    records=sorted(backend.rows(),key=lambda r:r['attempt'])
    assert len(records)==2 and wires[0]==wires[1]
    assert records[0]['generation_receipt']['id']=='gen-abc'
    assert records[0]['outcome']=='transport_certified'
    assert 'partial final answer' in '\n'.join(records[0]['stream_lines'])
    for p in (store.root/'calls').glob('*.json'):
        auditor.record_check(p.stem,run.load(p),store.protocol_hash,'episodes')


def test_uncertified_receipt_keeps_reservation_and_stops_batch(tmp_path):
    store=PilotStore(tmp_path/'profile-0',dict(fake=True),[])
    backend=run.Backend(store,SECRET,'episodes',lambda *a:reset(),lambda *a:None)
    with pytest.raises(run.base.Halt,match='uncertified'):
        backend.call(case())
    row=backend.rows()[0]
    assert row['generation_receipt'] is None
    assert run.row_cost(row)==Decimal(row['reserved_usd'])
    assert (tmp_path/'batch_stop.json').exists()


def test_shared_guard_counts_another_workers_inflight_reservation(tmp_path,monkeypatch):
    monkeypatch.setattr(run,'CAP',Decimal('0.04'))
    first=PilotStore(tmp_path/'profile-0',dict(fake=True),[])
    def interrupted(*a): raise SystemExit('simulated process disappearance')
    with pytest.raises(SystemExit):
        run.Backend(first,SECRET,'episodes',interrupted,receipt).call(case())
    assert run.load(next((first.root/'calls').glob('*.json')))['status']=='started'
    second=PilotStore(tmp_path/'profile-1',dict(fake=True),[])
    with pytest.raises(run.base.Halt,match='shared spending'):
        run.Backend(second,SECRET,'episodes',lambda *a:pytest.fail('overspending'),receipt).call(case())
    assert not list((second.root/'calls').glob('*.json'))


@pytest.fixture
def completed(tmp_path):
    parent=run.freeze(tmp_path)
    with (tmp_path/'network_preflight.json').open('w') as f:
        json.dump(dict(passed=True,finished_unix=time.time(),test=True),f)
    def gate(root,secret):return run.run_gate(root,secret,transport=fake,generation=receipt)
    def worker(root,index):
        run.run_shard(root,index,SECRET,transport=fake,generation=receipt)
        return dict(returncode=0)
    run.execute(parent,SECRET,gate_runner=gate,run_worker=worker)
    parent.lock.close()
    return tmp_path


def test_full_fabricated_batch_and_replay(completed):
    report=auditor.audit(completed)
    assert report['integrity_errors']==[]
    assert report['calls']==372 and report['complete_blocks']==4 and report['base_profiles']==2
    assert Decimal(report['accounted_usd'])==Decimal('0.0744')
    for p in report['profiles']:
        assert p['information_benefit_bounds_exact'][0]==p['information_benefit_bounds_exact'][1]
    with pytest.raises(run.base.Halt,match='do not restart'):
        run.execute(run.freeze(completed),SECRET)


def test_audit_rejects_changed_action_even_if_outcome_same(completed):
    path=completed/'profile-0/sessions/early-D.json'
    saved=run.load(path);saved['actions'][0]['action']['message']='different'
    path.write_text(json.dumps(saved))
    assert auditor.audit(completed)['integrity_errors']


def test_fresh_gate_is_same_structure_new_seed_labels():
    cases=run.gate_cases()
    assert {c['seed'] for c in cases}==set(range(300000,300008))
    assert 'policy_k' not in json.dumps(cases) and 'policy_x' in json.dumps(cases)


@pytest.mark.parametrize('failure',['invalid_answer','uncertified_transport','single_reissue'])
def test_partial_or_reissued_shard_replays_without_repair(tmp_path,failure):
    parent=run.freeze(tmp_path)
    run.run_gate(tmp_path,SECRET,transport=fake,generation=receipt)
    count=0
    def transport(wire,secret):
        nonlocal count
        count+=1
        if count==1:
            return ok(stream('{}')) if failure=='invalid_answer' else reset()
        return fake(wire,secret)
    gen=(lambda *a:None) if failure=='uncertified_transport' else receipt
    terminal=run.run_shard(tmp_path,0,SECRET,transport=transport,generation=gen)
    result=auditor.verify_shard(tmp_path/'profile-0',0)
    assert result['state']=='terminal'
    p=auditor.profile_readout(tmp_path,0)
    if failure=='single_reissue':
        assert terminal['calls']==92 and p['complete']
    else:
        assert not p['complete']
        assert p['information_benefit_bounds_exact'][0]!=p['information_benefit_bounds_exact'][1]
        assert terminal['calls']==(1 if failure=='uncertified_transport' else 67)
    parent.lock.close()


def test_failed_gate_admits_no_profiles(tmp_path):
    parent=run.freeze(tmp_path)
    (tmp_path/'network_preflight.json').write_text(json.dumps(dict(passed=True,finished_unix=time.time())))
    def wrong(wire,secret):return ok(stream('{}'))
    def gate(root,secret):return run.run_gate(root,secret,transport=wrong,generation=receipt)
    result=run.execute(parent,SECRET,gate_runner=gate,run_worker=lambda *a:pytest.fail('gate bypass'))
    assert not result['gate_passed'] and result['launched_indices']==[]
    report=auditor.audit(tmp_path)
    assert report['integrity_errors']==[] and report['calls']==8 and report['complete_profiles']==0
    parent.lock.close()


def test_source_closure_includes_indirect_dependencies_and_package_initializers():
    sources={str(p.relative_to(run.ROOT)) for p in run.sources()}
    assert {'paper3/source_closure.py','paper3/agenda_disclosure_canonical.py',
            'paper3/agenda_weak_preferences.py','paper3/agenda_identification.py',
            'paper3/disclosure_identification_design.py',
            'experiments/paper3_bonsai_structured_agenda.py',
            'analysis/__init__.py','tests/__init__.py',
            'analysis/paper3_disclosure_identification_audit.py'} <= sources
    assert '.env.local' not in sources
    assert all(not p.endswith('.zip') for p in sources)


def test_planning_regret_is_exact_and_tie_retaining():
    p=run.design.frame()['profiles'][0]
    for policy in ('q','p1','p3','p4','p5','p7'):
        d=auditor.planning_diagnostics(p,'early-B',policy)
        assert d['own_compatible'] and not d['myopic_compatible'] and not d['group_compatible']
        assert d['benchmark_planning_regret_normalized_exact']=='0'
    d=auditor.planning_diagnostics(p,'early-B','p2')
    assert d['benchmark_planning_regret_normalized_exact']=='7/38'
    assert not d['own_compatible'] and d['myopic_compatible'] and d['group_compatible']
    assert auditor.planning_diagnostics(p,'early-D','q')['benchmark_planning_regret_normalized_exact']=='3/19'


def test_partial_readout_retains_all_assigned_blocks(tmp_path):
    rows=[auditor.profile_readout(tmp_path,i) for i in range(4)]
    assert all(not r['complete'] and r['information_benefit_bounds_exact']==['-1','1'] for r in rows)
    assert [r['replicate'] for r in rows]==[0,0,1,1]


@pytest.mark.parametrize('failure',['normal_invalid','no_reasoning','length_finish'])
def test_normal_content_failures_are_not_reissued(tmp_path,failure):
    store=PilotStore(tmp_path/'profile-0',dict(fake=True),[])
    kwargs=dict(reasoning='' if failure=='no_reasoning' else 'thinking',
                finish='length' if failure=='length_finish' else 'stop')
    lines=stream('{}',**kwargs)
    if failure=='no_reasoning':
        lines=[line.replace('"reasoning_tokens": 40','"reasoning_tokens": 0') for line in lines]
    backend=run.Backend(store,SECRET,'episodes',lambda *a:ok(lines),receipt)
    if failure=='normal_invalid':
        key,raw=run.old.answer(backend,case())
        with pytest.raises(ValueError):
            run.game.game.validate_action(raw,'opening',['q'])
    else:
        with pytest.raises(ValueError):
            run.old.answer(backend,case())
    assert len(backend.rows())==1 and backend.halt is None
