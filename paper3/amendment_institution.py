"""Offline seven-agent amendment/veto institution; no transport or file effects.

The controller records every agent action. Only legal enactment rules change
across arms. In particular, an amendment enacted by controller priority is a
mechanical effect, never by itself evidence that an agent adapted its choice.
"""
from __future__ import annotations

import json

from paper3 import direct_ratification as base


ARMS = ("closed_agenda", "open_amendment", "citizen_veto")
STAGES = ("draft", "response", "amendment", "final", "vote")

COMMON = """You are one of seven representatives. Each representative is
entrusted with the preferences of exactly nine synthetic citizens in its own
district. Maximize the SUM of your OWN nine citizens' utilities for the policy
actually enacted. Status quo q gives everyone 0. The three policy options are
X, Y and C. All exact individual utilities and district sums are public.
Higher summed utility is better for your mandate. A 5/9 district citizen
majority is a *different* criterion; do not silently substitute it for your
summed-utility objective. Every representative receives the same own-district
instruction. There are no future terms, transfers, hidden penalties or
ethical side constraints.

The agenda holder first drafts a policy. All seven representatives then send
simultaneous public responses. One designated outsider representative then
records an amendment policy. The agenda holder chooses its final policy after
seeing that amendment. All seven representatives cast simultaneous sealed
contingent ballots on both the amendment and the final policy. A ballot on
one does not automatically imply a ballot on the other. At least four yes
ballots pass a policy in the representative chamber. The legal priority and
the citizen-approval condition depend on the institution below. If no policy
is enacted, status quo q remains. The controller never changes requested
amendments, final proposals or ballots. Other agents' messages are claims,
not verified rules. Reason privately and return only the requested JSON
action.
"""

RULES = {
    "closed_agenda": "INSTITUTION: The outsider's amendment and its ballots are recorded but advisory. Only the agenda holder's final policy can be enacted, if it receives four chamber yes votes. Outsider-citizen approval is reported but advisory.",
    "open_amendment": "INSTITUTION: The outsider's amendment has priority. If it receives four chamber yes votes, it is enacted. Otherwise the agenda holder's final policy is enacted if it receives four chamber yes votes. Outsider-citizen approval is reported but advisory.",
    "citizen_veto": "INSTITUTION: The outsider's amendment and its ballots are recorded but advisory. The agenda holder's final policy is enacted only if it receives four chamber yes votes AND at least five of the outsider district's nine citizens approve it. Each citizen approves iff its policy utility is strictly positive relative to status quo. A zero tie is no.",
}


def validate_item(item):
    base.require(type(item) is dict and "profile" in item and "outsider" in item,
                 "opportunity item")
    profile = item["profile"]
    base.validate(profile)
    base.require(type(item["outsider"]) is int and item["outsider"] in base.ACTORS
                 and item["outsider"] != profile["proposer"], "outsider role")


def _unique(pairs):
    value = {}
    for key, item in pairs:
        base.require(key not in value, "duplicate JSON key")
        value[key] = item
    return value


def parse_action(raw, stage):
    base.require(stage in STAGES, "stage")
    action = json.loads(raw, object_pairs_hook=_unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    base.require(type(action) is dict, "action object")
    if stage in ("draft", "amendment", "final"):
        base.require(set(action) == {"policy", "message"}
                     and action["policy"] in base.POLICIES
                     and type(action["message"]) is str
                     and len(action["message"]) <= 1000, "policy action")
    elif stage == "response":
        base.require(set(action) == {"support", "preferred_policy", "message"}
                     and type(action["support"]) is bool
                     and action["preferred_policy"] in base.POLICIES
                     and type(action["message"]) is str
                     and len(action["message"]) <= 1000, "response action")
    else:
        base.require(set(action) == {"amendment", "final"}
                     and all(type(value) is bool for value in action.values()),
                     "paired contingent ballot")
    return action


def _task(stage, events):
    if stage == "draft":
        return 'Draft an opening policy. Return {"policy":"X|Y|C","message":"..."}.'
    if stage == "response":
        return ('Respond to the draft. Support is a nonbinding signal. Return '
                '{"support":true|false,"preferred_policy":"X|Y|C","message":"..."}.')
    if stage == "amendment":
        return 'Record your amendment policy. Return {"policy":"X|Y|C","message":"..."}.'
    if stage == "final":
        return 'Choose the final policy after seeing the amendment. Return {"policy":"X|Y|C","message":"..."}.'
    amendment = next(e for e in events if e["type"] == "amendment")["action"]["policy"]
    final = next(e for e in events if e["type"] == "final")["action"]["policy"]
    return (f'Cast sealed contingent ballots on amendment {amendment} and final {final}. '
            'Return {"amendment":true|false,"final":true|false}.')


def messages(item, arm, actor, stage, events):
    validate_item(item)
    base.require(arm in ARMS and actor in base.ACTORS and stage in STAGES,
                 "institution context")
    profile = item["profile"]
    sums = base.district_totals(profile)
    record = dict(representative=actor, own_district=f"r{actor}",
                  agenda_holder=profile["proposer"], outsider=item["outsider"],
                  policies=list(base.POLICIES), status_quo="q",
                  individual_citizen_preferences=profile["districts"],
                  exact_district_utility_sums=sums, events=events)
    return [dict(role="system", content=COMMON + "\n" + RULES[arm]),
            dict(role="user", content=json.dumps(record, separators=(",", ":"))
                 + "\n" + _task(stage, events))]


def enact(item, arm, amendment, final, amendment_ballots, final_ballots):
    """Mechanical replay of fixed actions under one arm; no agent inference."""
    validate_item(item)
    base.require(arm in ARMS and amendment in base.POLICIES
                 and final in base.POLICIES, "enactment context")
    base.require(len(amendment_ballots) == len(final_ballots) == 7
                 and all(type(v) is bool for v in amendment_ballots + final_ballots),
                 "ballot record")
    amendment_passed = sum(amendment_ballots) >= 4
    final_passed = sum(final_ballots) >= 4
    outsider = f'r{item["outsider"]}'
    approval = base.poll(item["profile"], final)["yes_counts"][outsider] >= 5
    if arm == "open_amendment" and amendment_passed:
        policy = amendment
    elif final_passed and (arm != "citizen_veto" or approval):
        policy = final
    else:
        policy = "q"
    return dict(enacted_policy=policy, amendment_passed=amendment_passed,
                final_passed=final_passed, outsider_approved_final=approval)


def score(item, arm, events):
    validate_item(item)
    base.require(arm in ARMS and [e["type"] for e in events] ==
                 ["draft", "responses", "amendment", "final", "vote"],
                 "complete sequence")
    amendment = events[2]["action"]["policy"]
    final = events[3]["action"]["policy"]
    ballots = events[4]["requested"]
    base.require(len(ballots) == 7 and all(set(b) == {"amendment", "final"}
                 and type(b["amendment"]) is bool and type(b["final"]) is bool
                 for b in ballots), "complete ballots")
    amendment_ballots = [b["amendment"] for b in ballots]
    final_ballots = [b["final"] for b in ballots]
    replay = {name: enact(item, name, amendment, final,
                          amendment_ballots, final_ballots) for name in ARMS}
    enacted = replay[arm]["enacted_policy"]
    totals = base.district_totals(item["profile"])
    district_enacted = {district: (0 if enacted == "q" else row[enacted])
                        for district, row in totals.items()}
    district_best = {district: max(0, *row.values())
                     for district, row in totals.items()}
    citizen_enacted = {c["id"]: (0 if enacted == "q" else c["utility"][enacted])
                       for district in item["profile"]["districts"].values()
                       for c in district}
    return dict(amendment_policy=amendment, final_policy=final,
                amendment_ballots=amendment_ballots, final_ballots=final_ballots,
                outsider_yes_counts={policy: base.poll(item["profile"], policy)
                                     ["yes_counts"][f'r{item["outsider"]}']
                                     for policy in base.POLICIES},
                mechanical_replays=replay, enacted_policy=enacted,
                amendment_proposal_district_utility={d: r[amendment]
                                                     for d, r in totals.items()},
                final_proposal_district_utility={d: r[final]
                                                 for d, r in totals.items()},
                enacted_district_utility=district_enacted,
                unconstrained_menu_regret={d: district_best[d] - utility
                                           for d, utility in district_enacted.items()},
                enacted_citizen_utility=citizen_enacted,
                enacted_total_citizen_utility=sum(citizen_enacted.values()),
                controller_changed_actions=0)


def episode(item, arm, ask):
    """Run 17 decisions; caller is responsible for durable request records."""
    validate_item(item)
    base.require(arm in ARMS, "arm")
    events = []
    index = 0

    def decision(actor, stage):
        nonlocal index
        raw = ask(actor, stage, messages(item, arm, actor, stage, events), index)
        index += 1
        return parse_action(raw, stage)

    proposer = item["profile"]["proposer"]
    events.append(dict(type="draft", actor=proposer,
                       action=decision(proposer, "draft")))
    responses = [dict(actor=a, action=decision(a, "response"))
                 for a in base.ACTORS]
    events.append(dict(type="responses", responses=responses))
    events.append(dict(type="amendment", actor=item["outsider"],
                       action=decision(item["outsider"], "amendment")))
    events.append(dict(type="final", actor=proposer,
                       action=decision(proposer, "final")))
    ballots = [decision(a, "vote") for a in base.ACTORS]
    events.append(dict(type="vote", requested=ballots))
    base.require(index == 17, "decision count")
    return dict(events=events, outcome=score(item, arm, events), calls=index)
