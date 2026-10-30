from collections import Counter
import copy
import json

from experiments.paper3_pivotal_budget import select_cases, replay_checks
from experiments.paper3_pivotal_memory_diagnostic import diagnostic_cases


def test_factor_selection_unchanged_requests_all_views():
    originals = diagnostic_cases()
    saved = copy.deepcopy(originals)
    selected = select_cases(originals)
    assert originals == saved
    assert len(selected) == 24
    assert Counter(c["view"] for c in selected) == dict(transcript=8, event_index=8, registry=8)
    assert Counter(c["profile_seed"] for c in selected) == {863: 12, 947: 12}
    assert Counter(c["base_case"].split("-")[2] for c in selected) == dict(
        active=6, released=6, not_ratified=6, condition_failed=6)
    assert Counter(json.loads(c["messages"][1]["content"].split("\n")[0])["principal"]
                   for c in selected) == {0: 9, 3: 9, 6: 6}
    for c in selected:
        assert c == next(old for old in originals if old["name"] == c["name"])


def test_replay_checks_detect_request_prompt_and_generation_drift():
    old = dict(request=dict(max_tokens=2048, seed=7), prompt_token_ids=[1, 2], generated_token_ids=[3, 4])
    new = dict(request=dict(max_tokens=8192, seed=7), prompt_token_ids=[1, 2], generated_token_ids=[3, 4, 5])
    assert all(replay_checks(old, new).values())
    new["request"]["seed"] = 8
    new["prompt_token_ids"] = [1]
    new["generated_token_ids"] = [3]
    assert not any(replay_checks(old, new).values())
