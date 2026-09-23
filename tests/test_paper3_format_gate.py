import copy
import json
import pytest
from experiments import paper3_bonsai_format_gate as study
from analysis.paper3_format_gate_audit import verify_trace


def record(reply, error=None):
    text=json.dumps(reply)
    return dict(generation_error=error, cached_tokens=0, prompt_token_ids=[1], generated_token_ids=[2,3],
        boundary=dict(sampled_output_tokens=2,forced_output_tokens=0),
        response=dict(usage=dict(prompt_tokens=1,completion_tokens=2),choices=[dict(
            finish_reason="stop",message=dict(content="reason\n</think>\n"+text))]))


def test_frozen_matrix_no_answers_in_request_schema():
    cases=study.cases()
    assert len(cases)==16 and len({c['seed'] for c in cases})==16
    assert sum(c['stage']=='selector' for c in cases)==8
    assert {(c['arm'],c['stage'],len(c['candidates'])) for c in cases[8:]} == {
        (a,s,n) for a in ('D','B') for s in ('pairwise','ratification') for n in (1,2)}
    for c in cases:
        changed=copy.deepcopy(c); changed['expected']={'made_up':'answer'}
        assert study.request_for('model',c)==study.request_for('model',changed)
        assert c['schema']['additionalProperties'] is False
        assert study.request_for('model',c)['enable_thinking'] is True


def test_private_exactness_and_pairwise_format_are_distinct():
    for c in study.cases():
        reply=c['expected'] if c['expected'] is not None else {'policy_id':c['candidates'][0]}
        scored=study.score(record(reply),c)
        assert scored['passed'] and scored['valid']
        assert scored['exact'] == (None if c['stage']=='pairwise' else True)
        if c['stage']!='pairwise':
            wrong=copy.deepcopy(reply)
            key=next(iter(wrong['votes'])); wrong['votes'][key]=not wrong['votes'][key]
            bad=study.score(record(wrong),c)
            assert bad['valid'] and bad['exact'] is False and not bad['passed']
        assert not study.score(record(reply,'fixture failure'),c)['passed']


def test_bare_policy_never_repaired():
    c=next(c for c in study.cases() if c['stage']=='pairwise')
    row=record(c['candidates'][0])
    assert not study.score(row,c)['valid']


def test_grammar_trace_catches_early_constraint_and_missing_eos_lookahead():
    row=dict(prompt_token_ids=[4,5], generated_token_ids=[6,7,8,9],grammar_trace=[
        dict(previous_token=t,input_tokens=i+1,active=i>=2,constrained=i>=2)
        for i,t in enumerate([5,6,7,8,9])])
    verify_trace(row,7)
    early=copy.deepcopy(row); early['grammar_trace'][0]['constrained']=True
    with pytest.raises(AssertionError): verify_trace(early,7)
    missing=copy.deepcopy(row); missing['grammar_trace'].pop()
    with pytest.raises(AssertionError): verify_trace(missing,7)


def test_json_schema_never_fixes_correct_booleans():
    for c in study.cases():
        props=c['schema']['properties']
        if 'votes' in props:
            assert all(v=={'type':'boolean'} for v in props['votes']['properties'].values())
        for field in ('selected_policy','policy_id'):
            if field in props: assert props[field]['enum']==c['candidates']
