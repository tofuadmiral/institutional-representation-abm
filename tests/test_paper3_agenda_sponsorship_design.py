"""Offline schedule and all-assignment triage tests."""
from __future__ import annotations

from paper3 import agenda_sponsorship_design as design


def test_schedule_is_unique_and_bounded():
    rows = design.assignments()
    assert len(rows) == 12
    assert sum(row["intended_calls"] for row in rows) == 240
    assert len({row["profile_id"] for row in rows}) == 6
    assert len({row["seed_base"] + i for row in rows
                for i in range(design.CALLS_PER_EPISODE)}) == 240
    assert len({(row["profile_id"], row["arm"]) for row in rows}) == 12
    items = design.profiles()
    assert len({item["chair"] for item in items}) == 6
    assert sorted(item["favorite"] for item in items) == ["C", "C", "X", "X", "Y", "Y"]


def _outcomes(late, early, controls=(True, True)):
    values = {}
    for item in design.profiles():
        pid = item["profile"]["id"]
        if item["structure"] == "split":
            public_only = (late if item["order_stratum"] == "flexible_last"
                           else early)
            sealed, public = (False, True) if public_only else (True, True)
        else:
            control = controls[0] if item["structure"] == "aligned_y" else controls[1]
            sealed = public = control
        qualified = item["compromises"][0]
        values[(pid, "sealed")] = dict(qualified_motion=[qualified] if sealed else [])
        values[(pid, "public_sequential")] = dict(
            qualified_motion=[qualified] if public else [])
    return values


def test_order_sensitive_and_general_leads_are_predeclared():
    order = design.screen(_outcomes(late=True, early=False))
    assert order["classification"] == "selected_case_order_sensitive_lead"
    assert len(order["rows"]) == 6
    general = design.screen(_outcomes(late=True, early=True))
    assert general["classification"] == "selected_case_general_sequential_lead"
    assert design.screen(_outcomes(late=False, early=False))[
        "classification"] == "no_prespecified_action_lead"


def test_missingness_and_controls_cannot_create_a_lead():
    values = _outcomes(late=True, early=False)
    split = next(item for item in design.profiles()
                 if item["structure"] == "split")
    values.pop((split["profile"]["id"], "sealed"))
    result = design.screen(values)
    assert result["classification"] == "incomplete_or_control_failed"
    assert len(result["rows"]) == 6
    assert result["complete_split_pairs"] == 3
    bad_controls = design.screen(_outcomes(late=True, early=False,
                                           controls=(False, False)))
    assert bad_controls["classification"] == "incomplete_or_control_failed"
