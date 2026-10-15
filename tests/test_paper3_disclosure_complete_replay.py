"""Fabricated completions only; never new model calls."""
import json
import pytest

from analysis.paper3_disclosure_complete_replay import audit
from experiments import paper3_deepseek_disclosure_a3 as run
from tests.test_paper3_deepseek_disclosure_a3 import fake_model, gen_ok, SECRET


@pytest.fixture
def complete(tmp_path):
    run.run_gate(tmp_path, SECRET, transport=fake_model, generation=gen_ok())
    for i in range(run.SHARDS):
        run.run_shard(tmp_path, i, SECRET, transport=fake_model, generation=gen_ok())
    return tmp_path


def test_complete_exact_replay(complete):
    result = audit(complete)
    assert result["integrity_errors"] == []
    assert result["calls"] == 372


@pytest.mark.parametrize("change", ["wire", "stream", "cost", "action", "manifest", "snapshot", "gate"])
def test_detects_tampering(complete, change):
    shard = complete / "profile-0"
    path = next((shard / "calls").glob("*.json"))
    if change == "action":
        path = shard / "sessions/early-D.json"
    elif change in {"manifest", "snapshot"}:
        path = shard / ("manifest.json" if change == "manifest" else "sources.json")
    elif change == "gate":
        path = complete / "gate/sessions/lottery0.json"
    value = json.loads(path.read_text())
    if change == "wire":
        value["request_text"] += " "  # same parsed JSON; different transmitted bytes
    elif change == "stream":
        value["stream_lines"] = []
    elif change == "cost":
        value["verified_cost_usd"] = "0.0001"
    elif change == "action":
        value["actions"][0]["action"]["message"] = "altered, with identical resolution"
    elif change == "manifest":
        value["protocol"]["design"] = "altered"
    elif change == "snapshot":
        value[next(iter(value))] += "\n# changed\n"
    elif change == "gate":
        value["reply"]["expected_utility"] = "999"
    path.write_text(json.dumps(value))
    assert audit(complete)["integrity_errors"]


def test_extra_call_rejected(complete):
    path = next((complete / "profile-0/calls").glob("*.json"))
    (path.parent / ("0" * 64 + ".json")).write_bytes(path.read_bytes())
    assert audit(complete)["integrity_errors"]
