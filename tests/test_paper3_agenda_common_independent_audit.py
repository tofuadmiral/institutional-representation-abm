"""Offline checks for the post-freeze, non-primary integrity audit."""
from copy import deepcopy

import pytest

from analysis import paper3_agenda_common_independent_audit as audit
from paper3 import agenda_common_design as design
from paper3 import agenda_sponsorship_institution as game


def actions(item, *, choose_first=True):
    advocacy = [dict(actor=actor, message="test") for actor in range(7)]
    policy = item["compromises"][0] if choose_first else "none"
    sponsorships = [dict(actor=actor, policy=policy)
                    for actor in item["sponsor_order"]]
    return advocacy, sponsorships, [True] * 7


def test_independent_person_level_score_matches_controller_and_detects_change():
    item = design.profiles()[0]
    for choose_first in (True, False):
        advocacy, sponsorships, votes = actions(item,
                                                  choose_first=choose_first)
        for arm in game.ARMS:
            independent = audit.independently_score(
                item, arm, advocacy, sponsorships, votes)
            assert independent == game.score(item, arm, advocacy,
                                             sponsorships, votes)
            assert len(independent["enacted_citizen_utility"]) == 63
    invalid = deepcopy(sponsorships)
    invalid[0]["actor"] = item["chair"]
    with pytest.raises(ValueError, match="inventory"):
        audit.independently_score(item, "sealed", advocacy, invalid, votes)


def test_independent_screen_keeps_missing_and_opposite_signs():
    rows = [dict(structure="split", complete=True, floor_changed=True,
                 welfare_delta=18, control_stable=False) for _ in range(8)]
    rows += [dict(structure="aligned", complete=True, floor_changed=False,
                  welfare_delta=0, control_stable=True) for _ in range(4)]
    assert audit.independently_screen(rows)["classification"] == (
        "selected_case_public_benefit_lead")
    rows[0]["welfare_delta"] = -1
    rows[1]["welfare_delta"] = -1
    assert audit.independently_screen(rows)["classification"] == (
        "no_prespecified_constituent_lead")
    rows[2]["complete"] = False
    rows[3]["complete"] = False
    assert audit.independently_screen(rows)["classification"] == (
        "incomplete_or_control_failed")
