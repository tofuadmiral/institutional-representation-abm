"""Offline analysis for the staged reciprocal-exchange pilot.

No model inference or data-dependent case selection. All assigned arms, absent
episodes, seven-principal vectors, finite bounds and controller changes remain
visible. This module does not claim a population or causal effect.
"""
from copy import deepcopy
from fractions import Fraction

from paper3 import coalition_contracts as game
from paper3 import coalition_exchange_design as design


def canonical_outcome(displayed, assignment):
    """Map one completed outcome back to the declared logical principal IDs."""
    game.require(displayed is not None,"complete outcome required")
    result=deepcopy(displayed);form=assignment["form"]
    roles,policies=design.maps(form);inverse={v:k for k,v in policies.items()}
    for key in ("utility","regret","normalized_regret","best_outcome_utility",
                "worst_outcome_utility","final_full_delivery_utility",
                "realized_minus_scripted_independent","consent"):
        result[key]=design.canonical_utilities(result[key],form)
    for key in ("draft_terms","final_terms"):
        result[key]=design.canonical_offer(result[key],form)
    result["final_offer"]=dict(result["final_terms"],
                               message_display_text=displayed["final_offer"]["message"])
    result["passed"]=[inverse[p] for p in result["passed"]]
    result["invited_members"]=result["final_terms"]["coalition"]
    result["invited_member_utility"]=[result["utility"][i] for i in result["invited_members"]]
    result["nonmember_utility"]=[result["utility"][i] for i in game.ACTORS if i not in result["invited_members"]]
    result["status_quo_losers"]=[i for i,x in enumerate(result["utility"]) if x<0]
    result["scripted_independent"]["passed"]=[inverse[p] for p in result["scripted_independent"]["passed"]]
    result["scripted_independent"]["utility"]=design.canonical_utilities(
        result["scripted_independent"]["utility"],form)
    profile=design.fixtures()[assignment["fixture_index"]]
    result["profile"]=profile["id"]
    result["draft_full_delivery_utility"]=game.utility_vector(
        profile,list(result["draft_terms"]["projects"].values()))
    return result


def mechanism(events,assignment):
    """Observed vote paths, not inferred intent or equilibrium counterfactuals."""
    game.require(events is not None,"complete events required")
    by_type={e["type"]:e for e in events}
    game.require(set(by_type)=={"draft","response","final","consent","first_vote","second_vote"}
                 and len(events)==6,"complete six-stage history required")
    first,second=by_type["first_vote"],by_type["second_vote"]
    roles,policies=design.maps(assignment["form"])
    reverse_roles={shown:logical for logical,shown in enumerate(roles)}
    reverse_policies={shown:logical for logical,shown in policies.items()}
    profile=design.fixtures()[assignment["fixture_index"]]
    coalition=design.canonical_offer(by_type["final"]["action"],assignment["form"])["coalition"]
    due=[reverse_roles[i] for i in second["due_members"]]
    second_project=reverse_policies[second["project"]]
    second_requested=design.canonical_utilities(second["requested"],assignment["form"])
    second_executed=design.canonical_utilities(second["executed"],assignment["form"])
    first_requested=design.canonical_utilities(first["requested"],assignment["form"])
    first_executed=design.canonical_utilities(first["executed"],assignment["form"])
    changed_first=sorted(reverse_roles[i] for i in first["changed_ballots"])
    changed_second=sorted(reverse_roles[i] for i in second["changed_ballots"])
    marginal=[profile["utilities"][i][second_project] for i in game.ACTORS]
    pivotal_capable=sorted(i for i in due if marginal[i]<0 and
                           sum(second_requested[j] for j in game.ACTORS if j!=i)==3)
    pivotal_reneging=sorted(i for i in pivotal_capable if not second_requested[i])
    return dict(coalition=coalition,second_project=second_project,
        first_requested=first_requested,first_executed=first_executed,
        second_requested=second_requested,second_executed=second_executed,
        first_passed=first["passed"],second_passed=second["passed"],
        due_members=sorted(due),negative_marginal_signers=sorted(i for i in coalition if marginal[i]<0),
        pivotal_capable_signers=pivotal_capable,pivotal_reneging_signers=pivotal_reneging,
        changed_first_ballots=changed_first,changed_second_ballots=changed_second,
        contract_activated=game.contract_state(events,assignment["arm"])["active"])


def assignment_report(assignment,events=None,displayed_outcome=None):
    """Preserve the entire assignment even when no finite outcome was observed."""
    if events is None or displayed_outcome is None:
        game.require(events is None and displayed_outcome is None,"partial outcome is not complete")
        return dict(assignment=assignment,status="incomplete",outcome=None,mechanism=None)
    outcome=canonical_outcome(displayed_outcome,assignment)
    path=mechanism(events,assignment)
    exposed=design.EX_ANTE_EXPOSED[assignment["fixture_index"]]
    path["exposed_final_proposed_mean"]=str(sum(Fraction(outcome["final_full_delivery_utility"][i]) for i in exposed)/len(exposed))
    path["exposed_realized_mean"]=str(sum(Fraction(outcome["utility"][i]) for i in exposed)/len(exposed))
    path["ordinary_vote_bypass_observed"]=(assignment["arm"]=="universal_clearance" and
        not path["contract_activated"] and bool(outcome["passed"]) and
        any(outcome["utility"][i]<0 for i in exposed))
    return dict(assignment=assignment,status="complete",outcome=outcome,mechanism=path)


def contrasts(reports):
    game.require(len(reports)==24 and {r["assignment"]["id"] for r in reports}==
                 {a["id"] for a in design.schedule()},"all24 assignments required")
    out=[];fixtures=design.fixtures()
    for block in range(8):
        selected=[r for r in reports if r["assignment"]["block"]==block]
        game.require(len(selected)==3 and {r["assignment"]["arm"] for r in selected}==set(game.ARMS),
                     "one of each arm per block")
        profile_index=selected[0]["assignment"]["fixture_index"]
        profile=fixtures[profile_index]
        found={r["assignment"]["arm"]:r for r in selected}
        realized=[game.utility_vector(profile,passed) for passed in game.all_outcomes()]
        proposed=[game.utility_vector(profile,[a,b]) for a in game.PROJECTS["A"] for b in game.PROJECTS["B"]]
        possible=lambda space:[(min(v[i] for v in space),max(v[i] for v in space)) for i in game.ACTORS]
        for left_arm,right_arm in (("public_promise","member_enforcement"),
                                   ("member_enforcement","universal_clearance"),
                                   ("public_promise","universal_clearance")):
            left,right=found[left_arm],found[right_arm]
            def bounds(key,space):
                cells=[[(v,v) for v in r["outcome"][key]] if r["outcome"] else possible(space)
                       for r in (left,right)]
                return [[y[0]-x[1],y[1]-x[0]] for x,y in zip(*cells)]
            utility=bounds("utility",realized)
            final=bounds("final_full_delivery_utility",proposed)
            draft=bounds("draft_full_delivery_utility",proposed)
            exposed=design.EX_ANTE_EXPOSED[profile_index]
            mean=lambda vectors:[str(sum(Fraction(vectors[i][j]) for i in exposed)/len(exposed)) for j in (0,1)]
            paired=left["outcome"] is not None and right["outcome"] is not None
            behavioral=None
            if paired:
                a,b=left["outcome"],right["outcome"]
                behavioral=dict(final_projects_changed=a["final_terms"]["projects"]!=b["final_terms"]["projects"],
                    final_coalition_changed=a["final_terms"]["coalition"]!=b["final_terms"]["coalition"],
                    final_order_changed=a["final_terms"]["first"]!=b["final_terms"]["first"],
                    consent_changed=a["consent"]!=b["consent"],
                    all_principal_realized_difference=[y-x for x,y in zip(a["utility"],b["utility"])],
                    all_principal_final_proposed_difference=[y-x for x,y in zip(a["final_full_delivery_utility"],b["final_full_delivery_utility"])])
            out.append(dict(block=block,fixture=profile["id"],fixture_index=profile_index,
                form=selected[0]["assignment"]["form"],repeat=selected[0]["assignment"]["repeat"],
                contrast=right_arm+" minus "+left_arm,paired_complete=paired,
                all_principal_realized_difference_bounds=utility,
                all_principal_final_proposed_difference_bounds=final,
                all_principal_draft_proposed_difference_bounds=draft,
                exposed_realized_mean_difference_bounds=mean(utility),
                exposed_final_mean_difference_bounds=mean(final),
                behavioral_and_distributional=behavioral))
    return out


def pilot_screen(reports):
    """Feasibility and treatment opportunity, never a publication gate."""
    game.require(len(reports)==24,"all assignments required")
    complete=sum(r["status"]=="complete" for r in reports)
    relevance={}
    for i,profile in enumerate(design.fixtures()):
        selected=[r for r in reports if r["assignment"]["fixture_index"]==i and
                  r["assignment"]["arm"]=="member_enforcement"]
        relevance[profile["id"]]=any(r["mechanism"] is not None and
            r["mechanism"]["contract_activated"] and
            bool(r["mechanism"]["pivotal_capable_signers"]) for r in selected)
    return dict(assigned=len(reports),complete=complete,feasibility_passed=complete==24,
                treatment_relevance_by_fixture=relevance,
                treatment_relevance_passed=complete==24 and all(relevance.values()),
                caveat="Opportunity does not require an actual controller flip. Neither feasibility nor relevance is a scientific effect or publication threshold.")
