import copy
import json
from types import SimpleNamespace
from unittest.mock import patch
import sys
import pytest
from experiments import paper3_bonsai_agenda_seed_stability as study
from analysis.paper3_agenda_seed_stability_audit import Replay, paired_readout


class FakeBackend:
    def __init__(self, invalid_at=None):
        self.cases, self.records, self.invalid_at = [], {}, invalid_at

    def call(self, case, base):
        context = json.loads(case['messages'][-1]['content'].split('\n', 1)[0])
        stage = context['stage']
        reply = {'votes': {'p3': True}} if stage == 'ratification' else {'policy_id': 'p3'}
        if stage not in ('pairwise', 'ratification'):
            reply['message'] = 'fixture'
        if len(self.cases) == self.invalid_at:
            reply = 'p3'
        key = str(len(self.cases))
        self.cases.append(copy.deepcopy(case))
        row = dict(request=study.request_for('fake', case), cached_tokens=0,
            prompt_token_ids=[1], generated_token_ids=[2, 3],
            boundary=dict(sampled_output_tokens=2, forced_output_tokens=0),
            response=dict(usage=dict(prompt_tokens=1, completion_tokens=2), choices=[dict(
                finish_reason='stop', message=dict(content='reason\n</think>\n'+json.dumps(reply)))]))
        self.records[key] = json.loads(json.dumps(row, sort_keys=True))
        return key, self.records[key]


def test_fixed_pairs_unchanged_fixture_requests_and_budget():
    specs = study.specifications()
    assert [(s['seed'], s['arm']) for s in specs] == [
        (181000, 'D'), (181000, 'B'), (182000, 'B'),
        (182000, 'D'), (183000, 'D'), (183000, 'B')]
    assert len(specs)*25 == study.MAX_CALLS == 150
    assert study.run_one is study.prior.run_one
    assert study.case_for is study.prior.case_for
    assert study.request_for is study.prior.request_for
    for spec in specs:
        assert spec['profile'] == study.game.profiles()[0]
        case = study.case_for(study.game.messages(spec['profile'], spec['arm'], 'r0', 'opening', []), spec['seed'])
        assert study.request_for('fake', case)['enable_thinking'] is True
    specs[0]['profile']['name'] = 'mutation'
    assert all(s['profile']['name'] == 'conflict39' for s in specs[1:])


def test_exact_replay_recovers_schema_order_and_simultaneous_isolation():
    for spec in study.specifications():
        backend = FakeBackend()
        result = study.run_one(backend, None, spec)
        assert result['status'] == 'completed' and len(backend.cases) == 25
        assert [c['seed'] for c in backend.cases] == list(range(spec['seed'], spec['seed']+25))
        replay = Replay({'model': 'fake'}, backend.records, result, None, None)
        assert study.run_one(replay, None, spec) == result
        assert len(replay.schemas) == 25
        assert list(replay.schemas['0']['properties']) == ['policy_id', 'message']
        assert list(backend.records['0']['request']['response_schema']['properties']) == ['message', 'policy_id']
        contexts = [json.loads(c['messages'][-1]['content'].split('\n', 1)[0]) for c in backend.cases]
        for stage in ('responses', 'pairwise', 'ratification'):
            group = [c for c in contexts if c['stage'] == stage]
            assert len(group) == 7
            assert all(c['official_events'] == group[0]['official_events'] for c in group)
            assert all(e['stage'] != stage for e in group[0]['official_events'])
        backend.records['0']['request']['seed'] += 1
        with pytest.raises(RuntimeError, match='request replay'):
            study.run_one(Replay({'model': 'fake'}, backend.records, result, None, None), None, spec)


def test_failed_episode_no_imputation_or_retry():
    backend = FakeBackend(invalid_at=10)
    spec = study.specifications()[0]
    result = study.run_one(backend, None, spec)
    assert result['status'] == 'failed' and len(result['call_keys']) == 11
    assert 'resolution' not in result and 'metrics' not in result
    pairs = paired_readout({spec['name']: result})
    assert len(pairs) == 3 and all(not p['completed'] for p in pairs)
    assert all('enacted_mean_regret_B_minus_D' not in p for p in pairs)


def test_paired_differences_and_distribution_not_just_favorable_aggregate():
    profile = study.game.profiles()[0]
    sessions = {}
    for arm, policy in [('D', 'p5'), ('B', 'p6')]:
        sessions[f'conflict39-s181000-{arm}'] = dict(status='completed', resolution=policy,
            metrics={k: study.game.metrics(profile, policy) for k in ('locked_proposal', 'enacted')})
    pair = paired_readout(sessions)[0]
    assert pair['completed']
    assert pair['enacted_mean_regret_B_minus_D'] == pytest.approx(-0.07362555703189155)
    assert pair['principals_gaining_B_over_D'] == 2
    assert pair['principals_losing_B_vs_D'] == 5
    assert pair['utility_B_minus_D']['r0'] == -58
    assert not paired_readout(sessions)[1]['completed']


def test_call_cap_and_interrupted_marker_precede_generation(tmp_path):
    core = SimpleNamespace()
    modules = {'mlx': SimpleNamespace(core=core), 'mlx.core': core,
        'mlx_vlm': SimpleNamespace(stream_generate=None),
        'mlx_vlm.structured': SimpleNamespace(ThinkingAwareLogitsProcessor=None, build_json_schema_logits_processor=None)}
    calls = tmp_path / 'calls'
    calls.mkdir()
    case = study.case_for(study.game.messages(study.game.profiles()[0], 'D', 'r0', 'opening', []), 181000)
    fake = SimpleNamespace(path='fake', store=SimpleNamespace(root=tmp_path, protocol_hash='frozen'))
    for i in range(study.MAX_CALLS):
        (calls / f'{i}.json').write_text('{}')
    with patch.dict(sys.modules, modules):
        with pytest.raises(ValueError, match='call limit'):
            study.StructuredBackend.call(fake, case, None)
        key = study.digest(dict(request=study.request_for('fake', case), protocol='frozen'))
        (calls / (key+'.json')).write_text(json.dumps({'status': 'started'}))
        with pytest.raises(RuntimeError, match='not retried'):
            study.StructuredBackend.call(fake, case, None)
