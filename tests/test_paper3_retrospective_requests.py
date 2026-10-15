from copy import deepcopy
from decimal import Decimal
import json

import pytest

from paper3 import retrospective_requests as requests


def endpoint():
    return dict(data=dict(id=requests.MODEL, endpoints=[dict(tag=requests.TAG,
        provider_name=requests.PROVIDER, model_id=requests.MODEL, name="DeepInfra | " + requests.MODEL_ALIAS,
        quantization="fp8", status=0, context_length=40960, max_completion_tokens=16384,
        supported_parameters=["reasoning", "max_tokens", "temperature", "top_p", "top_k", "min_p",
                              "seed", "presence_penalty", "repetition_penalty", "tools", "tool_choice"],
        supports_tool_choice=dict(auto=True, function=False),
        pricing=dict(prompt="0.00000008", completion="0.00000028"))]))


def test_gate_and_discovery_bounds_fit_joint_cap_without_allocation():
    report = requests.legal_history_bounds()
    assert report["max_calls"] == 498
    assert len(report["assignments"]) == 16
    assert Decimal(report["joint_reserve_usd"]) <= requests.CAP
    assert max(bound for row in report["assignments"] for bound in row["input_bounds"]) + (
        requests.OUTPUT_BOUND) <= requests.CONTEXT
    for row in requests.gate_requests():
        assert row["request"]["reasoning"] == dict(enabled=True, exclude=False)
        assert row["request"]["tool_choice"] == "auto"
        assert json.loads(row["request_text"]) == row["request"]
        assert row["request"]["provider"]["allow_fallbacks"] is False


def test_blinded_game_ids_and_deliberately_paired_request_seeds():
    rows = requests.assignments()
    assert len({row["game"].game_id for row in rows}) == 4
    assert all("aligned" not in row["game"].game_id and "conflict" not in row["game"].game_id for row in rows)
    for seed in requests.FRAME_SEEDS:
        block = [row for row in rows if row["seed"] == seed]
        assert len(block) == 8 and len({row["seed_base"] for row in block}) == 1
        assert len({row["game"].chairs for row in block}) == 1
    assert len({row["seed_base"] for row in rows}) == 2


def test_metadata_requires_auto_tools_identity_and_capacity_not_forced_support():
    assert requests.check_endpoint(endpoint())["supports_tool_choice"]["function"] is False
    for change in (dict(status=-2), dict(context_length=8192),
                   dict(supported_parameters=["reasoning"]),
                   dict(supports_tool_choice=dict(auto=False, function=True)),
                   dict(pricing=dict(prompt="0.00001", completion="0.00001"))):
        bad = deepcopy(endpoint())
        bad["data"]["endpoints"][0].update(change)
        with pytest.raises(ValueError):
            requests.check_endpoint(bad)
