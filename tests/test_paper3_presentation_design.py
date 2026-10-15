"""Presentation pairing and inference-scope checks; no model calls."""
from copy import deepcopy
import pytest

from experiments import paper3_disclosure_presentation as run
from analysis import paper3_disclosure_presentation_audit as audit
from paper3 import agenda_rights as game


def theory_rows():
    rows=[]
    for i in range(8):
        b=run.design.assignment(i)
        rows.append(dict(block_index=i,pair=b['pair'],form=b['form'],
            inference_seed=b['inference_seed'],complete=True,
            planning={c:dict(own_compatible=True,group_compatible=False,myopic_compatible=False)
                for c in ('early-D','early-B','late')},
            original_label_outcomes={'early':{'D':'p2','B':'q'},'late':{'D':'q','B':'q'}},
            information_benefit_bounds_exact=['3/38','3/38']))
    return rows


def test_both_forms_benchmark_fit_is_not_an_equivalence_claim():
    out=audit.paired_readout(theory_rows(),[])
    assert out['mean_paired_difference_bounds_exact']==['0','0']
    assert out['paired_difference_sign']=='all_zero'
    assert out['interpretation']=='both_forms_reproduce_at_all_four_sampled_seeds_not_equivalence'
    assert all(f['benchmark_reproducing_blocks']==4 for f in out['forms'].values())


@pytest.mark.parametrize('form',['original','mapped'])
def test_form_failure_changes_predeclared_descriptive_classification(form):
    rows=theory_rows()
    for p in rows:
        if p['form']==form:p['information_benefit_bounds_exact']=['0','0']
    out=audit.paired_readout(rows,[])
    assert out['forms'][form]['benchmark_reproducing_blocks']==0
    if form=='original':
        assert out['paired_difference_sign']=='positive'
        assert out['mean_paired_difference_bounds_exact']==['3/38','3/38']
        assert out['interpretation'].startswith('original_not_stable')
    else:
        assert out['paired_difference_sign']=='negative'
        assert out['mean_paired_difference_bounds_exact']==['-3/38','-3/38']
        assert out['interpretation'].startswith('original_reproduces_mapped_does_not')


def test_all_assigned_missing_bounds_are_retained(tmp_path):
    rows=[audit.profile_readout(tmp_path,i) for i in range(8)]
    out=audit.paired_readout(rows,[])
    assert len(out['pairs'])==4
    assert out['mean_paired_difference_bounds_exact']==['-2','2']
    assert out['paired_difference_sign'] is None
    assert out['interpretation'].startswith('incomplete_or_integrity')
    assert all(f['assigned_blocks']==4 and f['complete_blocks']==0
               and f['mean_benefit_bounds_exact']==['-1','1'] for f in out['forms'].values())


def test_single_missing_block_widens_bounds_without_dropping_its_pair(tmp_path):
    rows=theory_rows()
    rows[0]=audit.profile_readout(tmp_path,0)
    out=audit.paired_readout(rows,[])
    assert len(out['pairs'])==4 and sum(p['complete'] for p in out['pairs'])==3
    assert out['mean_paired_difference_bounds_exact']==['-35/152','41/152']
    assert out['paired_difference_sign'] is None


def test_integrity_failure_cannot_be_scientific_success():
    out=audit.paired_readout(theory_rows(),['fabricated integrity error'])
    assert not out['all_assigned_complete_and_clean']
    assert out['interpretation'].startswith('incomplete_or_integrity')
    assert out['paired_difference_sign'] is None


def test_mixed_repeats_are_retained_not_voted_into_a_passing_gate():
    rows=theory_rows()
    rows[0]['information_benefit_bounds_exact']=['0','0']
    out=audit.paired_readout(rows,[])
    assert out['paired_difference_sign']=='mixed_or_tied'
    assert out['forms']['original']['observed_benefits_exact']==['0','3/38']
    assert out['forms']['original']['benchmark_reproducing_blocks']==3
    assert out['interpretation'].startswith('original_not_stable')


def test_profile_and_comparator_isomorphism_for_every_pair():
    frame=run.design.frame()
    mapping=run.design.POLICY_MAPPING
    for pair in range(4):
        profiles={frame['blocks'][i]['form']:frame['profiles'][i] for i in (pair,pair+4)}
        original,mapped=profiles['original'],profiles['mapped']
        for field in ('leader','sponsor','actors','principals','status_quo','name'):
            assert original[field]==mapped[field]
        for a,b in zip(original['catalog'],mapped['catalog']):
            assert dict(a,policy_id=mapping[a['policy_id']])==b
        for field in ('utilities','losses'):
            assert {r:{mapping[p]:v for p,v in row.items()} for r,row in original[field].items()}==mapped[field]
        for p in mapping:
            assert dict(game.metrics(original,p),policy=mapping[p])==game.metrics(mapped,mapping[p])
    a,b=(frame['predictions'][f]['predictions'] for f in run.design.FORMS)
    for field in ('own_best','group_best'):
        for condition,choices in a[field].items():
            assert {mapping[p] for p in choices}==set(b[field][condition])


def test_wave_admission_waits_for_all_first_wave_workers(tmp_path,monkeypatch):
    import json,time
    from threading import Lock
    parent=run.freeze(tmp_path)
    (tmp_path/'network_preflight.json').write_text(json.dumps(dict(passed=True,finished_unix=time.time())))
    finished=set();guard=Lock()
    def gate(root,secret):return dict(passed=True)
    def worker(root,index):
        started=time.time()
        if index>=4:
            with guard:assert {0,1,2,3}<=finished
        else:
            time.sleep(0.01*(4-index))
        (root/f'profile-{index}/sessions/terminal.json').write_text('{}')
        with guard:finished.add(index)
        return dict(returncode=0,started_unix=started,finished_unix=time.time())
    result=run.execute(parent,'synthetic-not-a-key',gate_runner=gate,run_worker=worker)
    parent.lock.close()
    assert result['stop_reason'] is None and result['launched_indices']==list(range(8))
    first_end=max(result['workers'][str(i)]['finished_unix'] for i in range(4))
    assert all(run.load(tmp_path/f'sessions/launch-{i}.json')['admitted_unix']>=first_end for i in range(4,8))
