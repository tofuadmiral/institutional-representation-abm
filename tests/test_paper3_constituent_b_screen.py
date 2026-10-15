from analysis import paper3_constituent_b_screen as screen
from paper3 import constituent_b_design, constituent_b_qwen_design


def _prepared():
    return constituent_b_design.frame(672100)[0]["prepared"]


def _offer(a="A0", b="B0"):
    return dict(projects=dict(A=a, B=b), first="A", coalition=[0, 1, 2, 3], message="")


def _cell(draft=None, final=None, passed=None, requested=None, changed=0,
          arm="member_enforcement"):
    draft = _offer() if draft is None else draft
    final = _offer() if final is None else final
    passed = ["A0"] if passed is None else passed
    requested = [[True] * 7, [False] * 7] if requested is None else requested
    return dict(status="completed", arm=arm, draft_action=draft, final_action=final,
                consent=[True] * 7,
                votes=[dict(project=final["projects"]["A"], requested=requested[0]),
                       dict(project=final["projects"]["B"], requested=requested[1])],
                outcome=dict(passed=passed, enforcement_changes=changed))


def test_final_proposal_change_with_citizen_effect_is_discovery_lead():
    result = screen.contrast(_prepared(), _cell(), _cell(final=_offer(a="A1")))
    assert result["discovery_lead"]
    assert result["final"]["full_delivery_policy_changed"]


def test_controller_only_outcome_difference_cannot_pass():
    result = screen.contrast(_prepared(), _cell(),
                             _cell(passed=["A0", "B0"], changed=1))
    assert not result["discovery_lead"]
    assert result["enacted_citizen_comparison"]["overall"]["citizen_count"] == 63


def test_voluntary_requested_ballot_difference_with_citizen_effect_can_pass():
    altered = [[False] + [True] * 6, [False] * 7]
    result = screen.contrast(_prepared(), _cell(),
                             _cell(passed=["A0", "B0"], requested=altered))
    assert result["requested_changed_same_projects"]
    assert result["discovery_lead"]


def test_same_offer_changed_consent_with_citizen_effect_can_pass():
    right = _cell(passed=["A0", "B0"])
    right["consent"][0] = False
    result = screen.contrast(_prepared(), _cell(), right)
    assert result["consent_changed_same_terms"]
    assert result["consent_pivotal_under_fixed_rule"]
    assert result["discovery_lead"]


def test_nonpivotal_consent_difference_cannot_pass_on_mechanical_outcome():
    right = _cell(passed=["A0", "B0"], changed=1)
    right["consent"][6] = False  # outsider under member-only rule
    result = screen.contrast(_prepared(), _cell(), right)
    assert result["consent_changed_same_terms"]
    assert not result["consent_pivotal_under_fixed_rule"]
    assert not result["discovery_lead"]


def test_incidental_requested_ballot_difference_cannot_launder_forced_outcome():
    altered = [[False] + [True] * 6, [False] * 7]
    result = screen.contrast(_prepared(), _cell(),
                             _cell(passed=["A0", "B0"], requested=altered,
                                   changed=1))
    assert result["requested_changed_same_projects"]
    assert not result["no_forced_ballots"]
    assert not result["discovery_lead"]


def test_ballots_on_different_projects_are_not_compared_as_vote_shift():
    right = _cell(passed=["A0", "B0"], requested=[[False] * 7, [True] * 7])
    right["votes"] = list(reversed(right["votes"]))
    result = screen.contrast(_prepared(), _cell(), right)
    assert not result["same_vote_projects"]
    assert not result["requested_changed_same_projects"]
    assert not result["discovery_lead"]


def test_incomplete_allocation_is_indeterminate_not_scientific_null():
    assignments = constituent_b_qwen_design.assignments()
    rows = constituent_b_qwen_design.profiles()
    saved = {a["id"]: dict(status="not_started") for a in assignments}
    result = screen.report(rows, assignments, saved)
    assert result["complete_episodes"] == 0
    assert result["candidate_screen"] is None
    assert len(result["profiles"]) == 7
