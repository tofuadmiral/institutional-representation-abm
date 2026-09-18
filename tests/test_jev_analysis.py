import json
from pathlib import Path
import pytest
from jev_study.replication import make_replication
from jev_study.run_replication import wire_request, MODEL
from jev_study.bill_choice import score
from jev_study.analyze_replication import analyze
from paper3.audit_runtime import PilotStore


def test_analysis_and_provenance(tmp_path):
    cases = json.loads(json.dumps(make_replication()))
    protocol = dict(cases=cases, wire_requests=[wire_request(c) for c in cases], model=MODEL)
    store = PilotStore(tmp_path, protocol, [])
    (tmp_path / 'sources.json').write_text('{}')
    for c, wire in zip(cases, protocol['wire_requests']):
        answer = dict(type='choice', choice=c['expected'], confidence=1.,
                      probabilities={k: float(k == c['expected']) for k in c['policies']})
        response = dict(model=MODEL, answers=dict(bill=answer), usage=dict(input_tokens=10))
        store.save('calls', c['name'], dict(wire_request=wire, response_text=json.dumps(response), protocol_hash=store.protocol_hash))
        store.save('sessions', c['name'], dict(status='completed', metrics=score(c, response)))
    report = analyze(tmp_path)
    assert report['profile_count'] == 120
    assert report['input_tokens'] == 8400
    assert all(a['correct'] == 120 and a['mean_brier'] == 0 for a in report['arms'].values())
    assert report['contrasts']['relabel']['accuracy_difference']['bootstrap_95'] == [0., 0.]
    # Correct choice with rounded/non-normalized probabilities must remain in
    # the choice denominator but be excluded from probability scoring.
    bad_case = cases[0]
    bad_path = tmp_path / 'calls' / (bad_case['name'] + '.json')
    bad_record = json.loads(bad_path.read_text())
    bad_response = json.loads(bad_record['response_text'])
    bad_response['answers']['bill']['probabilities'][bad_case['expected']] = .99
    bad_record['response_text'] = json.dumps(bad_response)
    bad_path.write_text(json.dumps(bad_record))
    store.save('sessions', bad_case['name'], dict(status='failed'))
    report = analyze(tmp_path)
    arm = report['arms'][bad_case['arm']]
    assert len(report['failures']) == 1
    assert arm['valid'] == 119 and arm['choice_correct_all_responses'] == 120
    path = tmp_path / 'calls' / (cases[0]['name'] + '.json')
    record = json.loads(path.read_text())
    record['wire_request'] = '{}'
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='provenance'):
        analyze(tmp_path)
