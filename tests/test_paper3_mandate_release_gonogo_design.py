from fractions import Fraction
import json

from paper3 import mandate_release_gonogo_design as design
from paper3 import mandate_release_gonogo_interface as interface
from paper3 import mandate_release_rival_opportunity as opportunity


def test_independent_inventory_has_three_distinct_coalition_topologies():
    cases = design.cases()
    assert len(cases) == 6
    assert len({(case.game.before, case.game.after) for case in cases}) == 6
    assert {case.family for case in cases} == set(design.FAMILIES)
    assert {case.stratum for case in cases} == {"pivotal", "nonpivotal"}
    for case in cases:
        facts = design.certificate(case.game, case.family, case.stratum)
        assert facts["overlap"] == int(case.family[-1])
        assert Fraction(facts["pivot_expected_y1"]["irrevocable"]) < 0
        if case.stratum == "pivotal":
            assert Fraction(facts["pivot_expected_y1"]["constituent_release"]) > 0
        else:
            assert len(opportunity.acceptable_coalitions(case.game, "Y1")) == 1
    stress = design.diversity_audit()
    assert stress["unique_profiles"] == 192
    assert all(cell["accepted"] == 32 for cell in stress["cells"].values())


def test_memory_schedule_keeps_shock_and_sealed_responses_private_until_due():
    case = design.cases()[0]
    context = dict(proposer=0, arm="constituent_release")
    messages = interface.messages(case, 0, "draft", context)
    assert "EXPECTED" in messages[0]["content"]
    assert "no " in messages[0]["content"] and "private memory" in messages[0]["content"]
    history = json.loads(messages[1]["content"])["history"]
    assert history == {}
    action = dict(second_project=case.display_projects[0], coalition="none", message="")
    assert interface.decode(case, "draft", json.dumps(action))["coalition"] == []
