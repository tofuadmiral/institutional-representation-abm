import pytest

from experiments.paper3_ministral_reasoning_gate import cases, final_answer, NATIVE_SYSTEM
from experiments.paper3_minimal_choice_audit import choice_case
from paper3.commitment_memory import parse


def test_native_ministral_boundary_and_json():
    raw = '[THINK]scratch work[/THINK]{"accept":false,"principal_utility_if_accepted":-3}'
    assert parse(final_answer(raw), {"accept": bool, "principal_utility_if_accepted": int})["accept"] is False
    for raw in ('{}', '[THINK]unfinished', '[THINK][/THINK]{}', '[THINK]x[/THINK]',
                '[THINK]x[/THINK][THINK]y[/THINK]{}', 'prose[THINK]x[/THINK]{}', '<think>x</think>{}'):
        with pytest.raises(ValueError):
            final_answer(raw)


def test_balanced_cases_and_native_prompt_scope():
    screen, fresh = cases()
    for stage in (screen, fresh):
        assert len(stage) == len({c['name'] for c in stage}) == 16
        assert sum(c['expected']['principal_utility_if_accepted'] < 0 for c in stage) == 8
        for case in stage:
            system = case['messages'][0]['content']
            assert NATIVE_SYSTEM in system
            assert system.endswith('After your [/THINK] boundary, return one JSON object, with no prose outside it.')
    original, _, expected = choice_case(2, -1, 'own', 'boolean')
    assert screen[0]['messages'][1] == original[1]
    assert screen[0]['expected'] == expected
    assert original[0]['content'].endswith('Return one JSON object, with no prose outside it.')
