import copy

import pytest

from analysis import paper3_constituent_b_inventory as inventory


def _fixture():
    assignments = [dict(id=f"episode-{i:02d}", profile_id=f"p{i}",
                        arm="member_enforcement", seed_base=700000 + 100 * i,
                        intended_calls=30)
                   for i in range(21)]
    row = dict(case=dict(id="episode-00-00",
                         context=dict(index=0, profile_id="p0",
                                      arm="member_enforcement"),
                         request=dict(seed=700000)),
               result=dict(status="recorded"))
    return dict(protocol=dict(assignments=assignments)), row


def test_valid_prefix_and_empty_assignments_retained():
    manifest, first = _fixture()
    second = copy.deepcopy(first)
    second["case"]["id"] = "episode-00-01"
    second["case"]["context"]["index"] = 1
    second["case"]["request"]["seed"] = 700001
    report = inventory.check(manifest, [first, second], terminal=True)
    assert report["scheduled_episodes"] == 21
    assert report["recorded_decisions"] == 2
    assert report["episode_prefix_lengths"]["episode-20"] == 0


@pytest.mark.parametrize("mutation", ["unknown", "wrong_seed", "hole", "wrong_arm"])
def test_unplanned_or_corrupt_case_rejected(mutation):
    manifest, saved = _fixture()
    if mutation == "unknown":
        saved["case"]["id"] = "episode-99-00"
    elif mutation == "wrong_seed":
        saved["case"]["request"]["seed"] += 1
    elif mutation == "hole":
        saved["case"]["id"] = "episode-00-01"
        saved["case"]["context"]["index"] = 1
        saved["case"]["request"]["seed"] += 1
    else:
        saved["case"]["context"]["arm"] = "public_promise"
    with pytest.raises(ValueError):
        inventory.check(manifest, [saved])


def test_prepared_allowed_live_but_not_terminal():
    manifest, saved = _fixture()
    saved["result"]["status"] = "prepared"
    assert inventory.check(manifest, [saved])["recorded_decisions"] == 1
    with pytest.raises(ValueError):
        inventory.check(manifest, [saved], terminal=True)
