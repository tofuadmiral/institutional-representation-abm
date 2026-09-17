import json
import pytest

from paper3.native_inference import final_answer
from paper3.commitment_memory import parse, contract_state
from experiments.paper3_native_validation import stages


def test_unique_closure_allows_opening_mentions_not_json_repair():
    assert parse(final_answer('[THINK]mention [THINK] before answering[/THINK]{"vote":false}'), {"vote": bool}) == {"vote": False}
    for raw in ('{}', '[THINK]{}', '[THINK][/THINK]{}', '[THINK]x[/THINK]{}[/THINK]{}',
                '[THINK]x[/THINK][THINK]{}', 'prose[THINK]x[/THINK]{}'):
        with pytest.raises(ValueError):
            final_answer(raw)
    for answer in ('{}{}', 'prose {"vote":true}', '{"vote":1}', '{"vote":true,"extra":1}'):
        with pytest.raises(ValueError):
            parse(final_answer('[THINK]x[/THINK]' + answer), {"vote": bool})


def test_validation_cases_are_deterministic_and_independently_scored():
    all_stages = stages()
    assert all_stages == stages()
    assert {k: len(v) for k, v in all_stages.items()} == dict(fresh=16, authorization=24, state=24)
    assert len({c['name'] for rows in all_stages.values() for c in rows}) == 64
    for stage, cases in all_stages.items():
        for c in cases:
            r = json.loads(c['messages'][1]['content'].split('\n')[0])
            expected = c['expected']
            if stage != 'state':
                own = (r.get('utilities_by_principal') or r.get('utilities_for_all_principals'))[str(r['principal_id'])]
                gain = sum(own[p] for p in r['offered_projects'])
                assert expected['principal_utility_if_accepted'] == gain
                assert expected.get('accept', expected.get('action') == 'accept') == (gain > 0)
            else:
                actor = r['principal']
                state = contract_state(r['events'])
                assert expected['obligation_due'] == (actor in state['signers'] and state['status'] == 'second_vote_due')
                assert expected['package_A0_B0_total'] == sum(r['utilities_for_all_principals'][str(actor)][p] for p in ('A0', 'B0'))
    assert sum(c['expected']['obligation_due'] for c in all_stages['state']) == 4
