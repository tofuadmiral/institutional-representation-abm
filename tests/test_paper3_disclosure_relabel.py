"""Fabricated model responses only. No provider calls or credentials."""
import json
from decimal import Decimal
import time
import pytest

from experiments import paper3_disclosure_relabel as run
from analysis import paper3_disclosure_relabel_audit as auditor
from tests.test_paper3_deepseek_disclosure_a3 import fake_model as old_fake, stream, ok, reset, SECRET
from paper3.audit_runtime import PilotStore


fake = old_fake


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
    assert run.PRIOR+run.CAP==Decimal('5.298918542')
    assert run.MAX_CALLS==728
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
    def gate(root,secret):return run.run_gate(root,secret)
    def worker(root,index):
        run.run_shard(root,index,SECRET,transport=fake,generation=receipt)
        return dict(returncode=0)
    run.execute(parent,SECRET,gate_runner=gate,run_worker=worker)
    parent.lock.close()
    return tmp_path


def test_full_fabricated_batch_and_replay(completed):
    report=auditor.audit(completed)
    assert report['integrity_errors']==[]
    assert report['calls']==364 and report['complete_blocks']==4 and report['base_profiles']==2
    assert Decimal(report['accounted_usd'])==Decimal('0.0728')
    for p in report['profiles']:
        assert p['information_benefit_bounds_exact'][0]==p['information_benefit_bounds_exact'][1]
    with pytest.raises(run.base.Halt,match='do not restart'):
        run.execute(run.freeze(completed),SECRET)


def test_audit_rejects_changed_action_even_if_outcome_same(completed):
    path=completed/'profile-0/sessions/early-D.json'
    saved=run.load(path);saved['actions'][0]['action']['message']='different'
    path.write_text(json.dumps(saved))
    assert auditor.audit(completed)['integrity_errors']


def test_gate_is_inherited_with_no_new_inference(tmp_path):
    parent=run.freeze(tmp_path)
    out=run.run_gate(tmp_path,SECRET)
    assert out['passed'] and out['fresh_calls']==0 and out['reference']['checks']==8
    assert out['accounted_usd']=='0' and run.all_rows(tmp_path)==[]
    assert auditor.verify_shard(tmp_path/'gate',None)['calls']==0
    parent.lock.close()


def test_changed_request_configuration_refuses_gate_inheritance(monkeypatch):
    original=run.request_for
    monkeypatch.setattr(run,'request_for',lambda case:dict(original(case),temperature=0.123))
    with pytest.raises(ValueError,match='configuration differs'):
        run.gate_reference()


def test_backend_cannot_make_fresh_gate_calls(tmp_path):
    store=PilotStore(tmp_path/'gate',dict(fake=True),[])
    backend=run.Backend(store,SECRET,'gate',lambda *a:pytest.fail('gate inference'),receipt)
    with pytest.raises(run.base.Halt,match='fresh gate calls'):
        backend.call(case())
    assert run.all_rows(tmp_path)==[]


@pytest.mark.parametrize('failure',['invalid_answer','uncertified_transport','single_reissue'])
def test_partial_or_reissued_shard_replays_without_repair(tmp_path,failure):
    parent=run.freeze(tmp_path)
    run.run_gate(tmp_path,SECRET)
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


def test_changed_inherited_gate_record_refuses_worker(tmp_path):
    parent=run.freeze(tmp_path)
    run.run_gate(tmp_path,SECRET)
    p=tmp_path/'gate/sessions/terminal.json'
    changed=run.load(p);changed['reference']['checks']=7
    p.write_text(json.dumps(changed))
    with pytest.raises(run.base.Halt,match='evidence changed'):
        run.run_shard(tmp_path,0,SECRET,transport=lambda *a:pytest.fail('gate bypass'))
    with pytest.raises(ValueError,match='evidence mismatch'):
        auditor.verify_shard(tmp_path/'gate',None)
    parent.lock.close()


def test_source_closure_includes_indirect_dependencies_and_package_initializers():
    sources={str(p.relative_to(run.ROOT)) for p in run.sources()}
    assert {'paper3/source_closure.py','paper3/agenda_disclosure_canonical.py',
            'paper3/agenda_weak_preferences.py','paper3/agenda_identification.py',
            'paper3/disclosure_identification_design.py','paper3/disclosure_relabel_design.py',
            'experiments/paper3_bonsai_structured_agenda.py',
            'analysis/__init__.py','tests/__init__.py',
            'analysis/paper3_disclosure_identification_audit.py','analysis/paper3_disclosure_relabel_audit.py'} <= sources
    assert '.env.local' not in sources
    assert all(not p.endswith('.zip') for p in sources)


def test_planning_regret_is_exact_and_tie_retaining():
    p=run.design.frame()['profiles'][0]
    for original_policy in ('q','p1','p3','p4','p5','p7'):
        policy=run.design.POLICY_MAPPING[original_policy]
        d=auditor.planning_diagnostics(p,'early-B',policy)
        assert d['own_compatible'] and not d['myopic_compatible'] and not d['group_compatible']
        assert d['benchmark_planning_regret_normalized_exact']=='0'
    d=auditor.planning_diagnostics(p,'early-B',run.design.POLICY_MAPPING['p2'])
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


def test_isomorphism_preserves_all_preference_rows_and_semantic_catalog_positions():
    from paper3 import agenda_rights as game
    before=run.original.design.frame()['profiles']
    after=run.design.frame()['profiles']
    mapping=run.design.POLICY_MAPPING
    assert mapping['q']=='q' and all(mapping[p]!=p for p in mapping if p!='q')
    assert len(set(mapping.values()))==8
    for a,b in zip(before,after):
        for field in ('leader','sponsor','actors','principals','status_quo','name'):
            assert a[field]==b[field]
        for pa,pb in zip(a['catalog'],b['catalog']):
            assert dict(pa,policy_id=mapping[pa['policy_id']])==pb
        for field in ('utilities','losses'):
            assert {r:{mapping[p]:v for p,v in row.items()} for r,row in a[field].items()}==b[field]
        for p in mapping:
            metrics_a=game.metrics(a,p); metrics_b=game.metrics(b,mapping[p])
            assert dict(metrics_a,policy=mapping[p])==metrics_b


def test_inverse_label_readout_and_failure_gate(completed):
    report=auditor.audit(completed)
    assert not report['integrity_errors']
    assert not report['label_robustness_gate']['passed']  # Valid fabricated answers need not fit theory.
    inverse=run.design.INVERSE_MAPPING
    for p in report['profiles']:
        assert p['original_label_locks']=={c:inverse[v] for c,v in p['locked'].items()}
        assert len(p['planning'])==3


def test_robustness_gate_requires_all_blocks_and_exact_distinctions():
    from copy import deepcopy
    rows=[]
    for i in range(4):
        positive=i%2==0
        rows.append(dict(complete=True,stratum='positive' if positive else 'zero_control',
            planning={c:dict(own_compatible=True,group_compatible=False,myopic_compatible=False)
                      for c in ('early-D','early-B','late')},
            original_label_outcomes=({'early':{'D':'p2','B':'q'},'late':{'D':'q','B':'q'}}
                                    if positive else {'early':{'D':'p3','B':'p3'},'late':{'D':'p3','B':'p3'}}),
            information_benefit_bounds_exact=['3/38','3/38'] if positive else ['0','0']))
    assert auditor.robustness_gate(rows,[])['passed']
    assert not auditor.robustness_gate(rows[:-1],[])['passed']
    assert not auditor.robustness_gate(rows,['integrity failure'])['passed']
    bad=deepcopy(rows);bad[0]['planning']['late']['myopic_compatible']=True
    assert not auditor.robustness_gate(bad,[])['passed']
    bad=deepcopy(rows);bad[0]['information_benefit_bounds_exact']=['-1','1']
    assert not auditor.robustness_gate(bad,[])['passed']


def test_missing_usage_is_reported_unknown_not_zero():
    usage=auditor.usage_summary([dict(response=dict(usage=None),outcome='uncertified')])
    assert usage['attempts_with_unknown_tokens']==dict(prompt_tokens=1,completion_tokens=1,reasoning_tokens=1)

