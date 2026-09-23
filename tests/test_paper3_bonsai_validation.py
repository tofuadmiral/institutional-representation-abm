from types import SimpleNamespace
import pytest

from experiments.paper3_bonsai_validation import stages, final_answer, append_generated_token
from experiments.paper3_pivotal_budget import select_cases
from experiments.paper3_pivotal_memory_diagnostic import diagnostic_cases


def test_bonsai_cases_preserve_task_and_expected_answers():
    groups = stages()
    assert {k: len(v) for k, v in groups.items()} == dict(smoke=1, private=16, pivotal=24)
    for old, new in zip(select_cases(diagnostic_cases()), groups["pivotal"]):
        assert old["expected"] == new["expected"]
        assert old["messages"][1] == new["messages"][1]
        assert "[THINK]" not in new["messages"][0]["content"]


def test_bonsai_closure_parser_does_not_repair_invalid_reasoning():
    assert final_answer('calculation</think> {"result":323}') == '{"result":323}'
    for invalid in ('{"result":323}', '</think>{"result":323}', 'a</think>b</think>c', 'a</think><think>b'):
        with pytest.raises(ValueError):
            final_answer(invalid)


def test_vlm_terminal_chunk_deduplication_preserves_eos():
    tokens = []
    for token, count in ((10, 1), (11, 2), (11, 2)):
        append_generated_token(tokens, SimpleNamespace(token=token, generation_tokens=count))
    assert tokens == [10, 11]
    append_generated_token(tokens, SimpleNamespace(token=99, generation_tokens=3))
    assert tokens == [10, 11, 99]
