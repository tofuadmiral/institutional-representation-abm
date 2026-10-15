"""Offline opportunity and blocking checks; no model calls."""
from collections import Counter
import json

from paper3 import coalition_contracts as game
from paper3 import coalition_exchange_design as d
from paper3 import coalition_jurisdiction_design as old


def test_fresh_profiles_have_real_but_not_guaranteed_opportunities():
    profiles=d.fixtures()
    assert len(profiles)==2
    assert {p["id"] for p in profiles}.isdisjoint({p["id"] for p in old.fixtures()})
    expected=((2,2,4,3,1),(3,3,6,1,15))
    for p,want in zip(profiles,expected):
        got=d.opportunities(p)
        assert (got["positive_A0"],got["positive_B0"],len(got["package_positive"]),
            len(got["outsider_package_loss"]),len(got["eligible_coalitions"]))==want
        assert all(v>0 for v in got["inclusive_alternative"])
        assert got["pivotal_second_vote_opportunities"]
        for opportunity in got["pivotal_second_vote_opportunities"]:
            c=opportunity["coalition"];i=opportunity["defector"]
            assert i in c and p["utilities"][i]["B0"]<0
            assert sum(p["utilities"][j]["B0"]>0 for j in game.ACTORS if j not in c)+3==3


def test_schedule_fully_crosses_form_and_seed_within_profiles():
    schedule=d.schedule();assert len(schedule)==24 and len({a["id"] for a in schedule})==24
    by_cell=Counter((a["fixture_index"],a["form"],a["repeat"]) for a in schedule)
    assert len(by_cell)==8 and set(by_cell.values())=={3}
    for profile in range(2):
        for repeat in range(2):
            selected=[a for a in schedule if a["fixture_index"]==profile and a["repeat"]==repeat]
            assert len(selected)==6 and len({a["seed_base"] for a in selected})==1
            assert Counter(a["arm"] for a in selected)=={arm:2 for arm in game.ARMS}
    assert len({a["seed_base"] for a in schedule})==4


def test_display_mapping_preserves_all_principal_utilities():
    for p in d.fixtures():
        for form in (0,1):
            shown=d.display_profile(p,form)
            role_map,policy_map=d.maps(form)
            for logical in game.ACTORS:
                displayed=role_map[logical]
                assert all(shown["utilities"][displayed][policy_map[k]]==p["utilities"][logical][k]
                           for k in p["utilities"][logical])
            for arm in game.ARMS:
                messages=game.messages(shown,arm,shown["proposer"],"draft",[])
                labelled=d.labelled_messages(messages)
                assert labelled[0]==messages[0]
                record=json.loads(labelled[1]["content"].split("\n",1)[0])
                assert record["utilities_for_all_principals"]=={
                    str(i):row for i,row in enumerate(shown["utilities"])}


def test_controller_has_pivotal_opportunity_without_guaranteeing_agent_choice():
    for profile in d.fixtures():
        opportunity=d.opportunities(profile)["pivotal_second_vote_opportunities"][0]
        coalition=opportunity["coalition"];defector=opportunity["defector"]
        offer=dict(projects=dict(A="A0",B="B0"),first="A",coalition=coalition,message="")
        events=[dict(type="final",actor=0,action=offer),
                dict(type="consent",approvals=[True]*6+[False])]
        assert game.contract_state(events,"member_enforcement")["active"]
        assert not game.contract_state(events,"universal_clearance")["active"]
        first_request=[i in coalition or profile["utilities"][i]["A0"]>0 for i in game.ACTORS]
        first=game.resolve_vote(events,"member_enforcement",first_request,"first_vote")
        assert first["passed"] and not first["changed_ballots"]
        events.append(first)
        second_request=[(i in coalition and i!=defector) or
            (i not in coalition and profile["utilities"][i]["B0"]>0) for i in game.ACTORS]
        binding=game.resolve_vote(events,"member_enforcement",second_request,"second_vote")
        promise=game.resolve_vote(events,"public_promise",second_request,"second_vote")
        assert binding["changed_ballots"]==[defector] and binding["passed"]
        assert not promise["changed_ballots"] and not promise["passed"]
