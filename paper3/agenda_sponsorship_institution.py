"""Seven-representative agenda sponsorship, entirely offline.

Six outsiders each file one exclusive sponsorship. The four-sponsor quota
and majority ballot are identical in both arms; only whether earlier filed
sponsorships become public before later outsiders act differs. The controller
never repairs, replaces or forces an agent's recorded sponsorship or vote.
"""
from __future__ import annotations

import json

from paper3 import agenda_sponsorship_opportunity as opportunity
from paper3 import direct_ratification as base


ARMS = ("sealed", "public_sequential")
STAGES = ("advocacy", "sponsor", "vote")

COMMON = """You are one of seven representatives, each entrusted with nine
synthetic citizens. Your sole objective is to maximize the SUM of your OWN
district's nine citizens' utilities for the policy actually enacted. Status
quo q gives everyone zero. Individual citizen utilities and exact district
sums are public. A citizen headcount majority and aggregate welfare are not
your stated mandate. Every representative has the same own-district rule.
There are no future terms, transfers, reputation effects, sanctions or
hidden objectives.

The chair has already filed one policy. All seven representatives first send
one public advocacy statement, collected simultaneously and then broadcast.
The six outsiders may each sponsor exactly ONE of the two compromise motions,
or neither. A compromise motion reaches the floor if at least four outsiders
sponsor it. If no compromise qualifies, the chair's filed policy is the
fallback motion. All seven cast sealed votes on the floor motion; four yes
votes enact it, otherwise status quo q remains. The institution below
determines when formal sponsorship choices become visible, not their legal
force. Other agents' messages are claims, not verified rules. Return only
the requested JSON action and reason privately.
"""

RULES = {
    "sealed": "INSTITUTION: Outsiders file sponsorships privately in the announced administrative order. No outsider sees another's formal sponsorship before filing. All six are revealed only after the stage closes. The filing order gives no priority or extra vote weight.",
    "public_sequential": "INSTITUTION: Outsiders file sponsorships one at a time in the announced order. Each later outsider sees the already-filed formal sponsorships before choosing. Filed sponsorships cannot be changed.",
}


def validate_item(item):
    opportunity.certificate(item)
    order = item.get("sponsor_order")
    base.require(type(order) is tuple and len(order) == 6 and
                 set(order) == set(item["outsiders"]) and
                 all(type(actor) is int for actor in order), "sponsorship order")


def _unique(pairs):
    value = {}
    for key, item in pairs:
        base.require(key not in value, "duplicate JSON key")
        value[key] = item
    return value


def parse_action(raw, stage, compromises):
    base.require(stage in STAGES, "stage")
    value = json.loads(raw, object_pairs_hook=_unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(
                           ValueError("nonfinite")))
    base.require(type(value) is dict, "action object")
    if stage == "advocacy":
        base.require(set(value) == {"message"} and
                     type(value["message"]) is str and
                     len(json.dumps(value["message"]).encode()) <= 502,
                     "advocacy action")
    elif stage == "sponsor":
        base.require(set(value) == {"policy"} and
                     value["policy"] in (*compromises, "none"),
                     "sponsorship action")
    else:
        base.require(set(value) == {"vote"} and
                     type(value["vote"]) is bool, "ballot action")
    return value


def motion(item, sponsorships):
    """Count six unchanged sponsorship choices and select the floor motion."""
    validate_item(item)
    y, c = item["compromises"]
    base.require(type(sponsorships) is list and len(sponsorships) == 6 and
                 all(type(entry) is dict and set(entry) == {"actor", "policy"}
                     and type(entry["actor"]) is int and
                     entry["policy"] in (y, c, "none")
                     for entry in sponsorships), "six sponsorship records")
    base.require({entry["actor"] for entry in sponsorships} ==
                 set(item["outsiders"]), "six distinct outsider sponsors")
    counts = {policy: sum(entry["policy"] == policy for entry in sponsorships)
              for policy in (y, c)}
    qualified = [policy for policy, count in counts.items() if count >= 4]
    base.require(len(qualified) <= 1, "exclusive sponsorship invariant")
    return dict(counts=counts, qualified=qualified,
                floor_policy=qualified[0] if qualified else item["favorite"])


def messages(item, arm, actor, stage, advocacy, sponsorship_prefix=None,
             floor_policy=None):
    validate_item(item)
    base.require(arm in ARMS and actor in base.ACTORS and stage in STAGES,
                 "institution context")
    if stage == "sponsor":
        base.require(actor in item["outsiders"] and
                     type(advocacy) is list and len(advocacy) == 7 and
                     type(sponsorship_prefix) is list and
                     len(sponsorship_prefix) < 6,
                     "sponsor context")
    elif stage == "vote":
        base.require(type(advocacy) is list and len(advocacy) == 7 and
                     floor_policy in base.POLICIES and
                     type(sponsorship_prefix) is list and
                     len(sponsorship_prefix) == 6, "vote context")
    else:
        base.require(advocacy is None and sponsorship_prefix is None and
                     floor_policy is None, "advocacy context")
    visible_sponsorships = (sponsorship_prefix if stage == "vote" or
                            (stage == "sponsor" and arm == "public_sequential")
                            else [])
    record = dict(representative=actor, own_district=f"r{actor}",
                  chair=item["chair"], filed_policy=item["favorite"],
                  compromise_motions=item["compromises"],
                  announced_sponsor_order=(item["sponsor_order"]
                                           if stage == "sponsor" else None),
                  individual_citizen_preferences=item["profile"]["districts"],
                  exact_district_utility_sums=base.district_totals(item["profile"]),
                  public_advocacy=advocacy or [],
                  visible_formal_sponsorships=visible_sponsorships,
                  floor_policy=floor_policy)
    if stage == "advocacy":
        task = 'Advocate publicly for a policy. Return {"message":"..."}.'
    elif stage == "sponsor":
        y, c = item["compromises"]
        task = (f'Sponsor exactly one motion ({y} or {c}) or none. '
                'Return {"policy":"..."}.')
    else:
        task = f'Vote on floor policy {floor_policy}. Return {{"vote":true}} or {{"vote":false}}.'
    return [dict(role="system", content=COMMON + "\n" + RULES[arm]),
            dict(role="user", content=json.dumps(record, separators=(",", ":"))
                 + "\n" + task)]


def score(item, arm, advocacy, sponsorships, votes):
    validate_item(item)
    base.require(arm in ARMS and type(advocacy) is list and len(advocacy) == 7
                 and type(votes) is list and len(votes) == 7 and
                 all(type(vote) is bool for vote in votes), "complete episode")
    proposal = motion(item, sponsorships)
    floor_policy = proposal["floor_policy"]
    enacted = floor_policy if sum(votes) >= 4 else "q"
    totals = base.district_totals(item["profile"])
    districts = {district: (0 if enacted == "q" else row[enacted])
                 for district, row in totals.items()}
    citizen = {person["id"]: (0 if enacted == "q" else
                              person["utility"][enacted])
               for district in item["profile"]["districts"].values()
               for person in district}
    regret = {district: max(0, *row.values()) - districts[district]
              for district, row in totals.items()}
    return dict(arm=arm, advocacy=advocacy, sponsorships=sponsorships,
                sponsorship_counts=proposal["counts"],
                qualified_motion=proposal["qualified"],
                floor_policy=floor_policy, requested_votes=votes,
                chamber_passed=sum(votes) >= 4, enacted_policy=enacted,
                enacted_district_utility=districts,
                enacted_citizen_utility=citizen,
                enacted_total_citizen_utility=sum(citizen.values()),
                district_menu_regret=regret,
                harmed_citizen_count=sum(value < 0 for value in citizen.values()),
                controller_changed_actions=0)


def episode(item, arm, ask):
    """Execute 20 agent decisions; caller persists exact requests/failures."""
    validate_item(item)
    base.require(arm in ARMS, "arm")
    index = 0

    def decision(actor, stage, advocacy, prefix=None, floor_policy=None):
        nonlocal index
        raw = ask(actor, stage,
                  messages(item, arm, actor, stage, advocacy, prefix,
                           floor_policy), index)
        index += 1
        return parse_action(raw, stage, item["compromises"])

    advocacy = [dict(actor=actor,
                     message=decision(actor, "advocacy", None)["message"])
                for actor in base.ACTORS]
    sponsorships = []
    for actor in item["sponsor_order"]:
        action = decision(actor, "sponsor", advocacy, sponsorships)
        sponsorships.append(dict(actor=actor, policy=action["policy"]))
    floor_policy = motion(item, sponsorships)["floor_policy"]
    votes = [decision(actor, "vote", advocacy, sponsorships,
                      floor_policy)["vote"] for actor in base.ACTORS]
    base.require(index == 20, "decision count")
    return dict(advocacy=advocacy, sponsorships=sponsorships, votes=votes,
                outcome=score(item, arm, advocacy, sponsorships, votes),
                calls=index)
