import json
import pytest

from experiments.paper3_qwen_reasoning_gate import final_answer, followup_cases


def test_native_reasoning_boundary_is_strict():
    assert final_answer('<think>analysis</think> {"accept":false}', True) == '{"accept":false}'
    assert final_answer('{"accept":true}', False) == '{"accept":true}'
    for raw in ('<think>incomplete', '{"accept":true}', '<think>x</think><think>y</think>{}'):
        with pytest.raises(ValueError):
            final_answer(raw, True)
    with pytest.raises(ValueError):
        final_answer('<think>x</think>{}', False)


def test_fresh_gate_is_balanced_and_orders_preserve_total():
    cases = followup_cases()
    assert len(cases) == len({c["name"] for c in cases}) == 16
    assert sum(c["expected"]["action"] == "accept" for c in cases) == 8
    for c in cases:
        record = json.loads(c["messages"][1]["content"].split("\n")[0])
        actor = record["principal_id"]
        assert actor in (1, 4)
        assert f"principal {actor}" in c["messages"][0]["content"]
        gain = sum(record["utilities_by_principal"][str(actor)].values())
        assert gain == c["expected"]["principal_utility_if_accepted"]
        assert c["expected"]["action"] == ("accept" if gain > 0 else "decline")
