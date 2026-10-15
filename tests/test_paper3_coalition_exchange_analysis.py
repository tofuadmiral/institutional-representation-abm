"""Fabricated complete/missing paths exercise analysis, never model evidence."""
import json

from paper3 import coalition_contracts as game
from paper3 import coalition_exchange_design as design
from paper3 import coalition_exchange_analysis as analysis


def scripted(assignment):
    logical=design.fixtures()[assignment["fixture_index"]]
    shown=design.display_profile(logical,assignment["form"])
    roles,policies=design.maps(assignment["form"])
    selected=(policies["A0"],policies["B0"])
    offer=dict(projects={p[0]:p for p in selected},first=policies["A0"][0],
               coalition=[roles[i] for i in (0,1,2,3)],message="fabricated offer")
    members=set(offer["coalition"]);defector=roles[0]
    def ask(actor,stage,messages,index):
        if stage in ("draft","final"):value=offer
        elif stage=="response":value=dict(**offer,support=True)
        elif stage=="consent":value=dict(consent=not (
            assignment["arm"]=="universal_clearance" and actor==roles[6]))
        elif stage=="first_vote":value=dict(vote=actor in members)
        else:value=dict(vote=actor in members and actor!=defector)
        return json.dumps(value)
    return design.episode(shown,assignment["arm"],ask)


def complete_reports():
    return [analysis.assignment_report(a,**dict(events=(run:=scripted(a))["events"],
                displayed_outcome=run["outcome"])) for a in design.schedule()]


def test_form_mapping_and_pivotal_reneging():
    reports=complete_reports()
    for block in range(8):
        by_arm={r["assignment"]["arm"]:r for r in reports if r["assignment"]["block"]==block}
        public,member,universal=(by_arm[arm] for arm in game.ARMS)
        for row in by_arm.values():
            assert row["status"]=="complete" and row["outcome"]["profile"] in {
                p["id"] for p in design.fixtures()}
            assert row["mechanism"]["coalition"]==[0,1,2,3]
            assert row["mechanism"]["second_project"]=="B0"
            if row["assignment"]["arm"]!="universal_clearance":
                assert row["mechanism"]["pivotal_capable_signers"]==[0]
        assert public["mechanism"]["pivotal_reneging_signers"]==[0]
        assert not public["mechanism"]["changed_second_ballots"]
        assert not public["mechanism"]["second_passed"]
        assert member["mechanism"]["contract_activated"]
        assert member["mechanism"]["changed_second_ballots"]==[0]
        assert member["mechanism"]["second_passed"]
        assert not universal["mechanism"]["contract_activated"]
        assert not universal["mechanism"]["changed_second_ballots"]
        assert universal["mechanism"]["ordinary_vote_bypass_observed"]
    assert analysis.pilot_screen(reports)["treatment_relevance_passed"]


def test_full_cross_and_finite_missingness_bounds():
    reports=complete_reports();contrasts=analysis.contrasts(reports)
    assert len(contrasts)==24 and all(c["paired_complete"] for c in contrasts)
    assert all(len(c["all_principal_realized_difference_bounds"])==7 for c in contrasts)
    selected=[c for c in contrasts if c["contrast"]=="member_enforcement minus public_promise"]
    assert len(selected)==8 and all(c["behavioral_and_distributional"]["all_principal_realized_difference"][0]<0
                                    for c in selected)
    damaged=list(reports)
    removed=next(i for i,r in enumerate(damaged) if r["assignment"]["arm"]=="member_enforcement")
    damaged[removed]=analysis.assignment_report(damaged[removed]["assignment"])
    missing=analysis.contrasts(damaged)
    same_block=[c for c in missing if c["block"]==damaged[removed]["assignment"]["block"]]
    affected=[c for c in same_block if "member_enforcement" in c["contrast"]]
    unaffected=[c for c in same_block if "member_enforcement" not in c["contrast"]]
    assert len(affected)==2 and all(not c["paired_complete"] for c in affected)
    assert len(unaffected)==1 and unaffected[0]["paired_complete"]
    assert all(any(low<high for low,high in c["all_principal_realized_difference_bounds"])
               for c in affected)
    screen=analysis.pilot_screen(damaged)
    assert screen["assigned"]==24 and screen["complete"]==23
    assert not screen["feasibility_passed"] and not screen["treatment_relevance_passed"]


def test_incomplete_assignment_never_imputed():
    assignment=design.schedule()[0]
    row=analysis.assignment_report(assignment)
    assert row["status"]=="incomplete" and row["outcome"] is None and row["mechanism"] is None
