"""Bounded representative agenda game; no inference or filesystem effects.

The same policy and communication opportunities exist under both selectors.
All agent actions are explicit; invalid actions never become fallback votes.
"""
from __future__ import annotations

import copy
import json

ARMS = ("D", "B")
ROLES = tuple(f"r{i}" for i in range(7))
FINAL = "After your native thinking block, return one JSON object, with no prose outside it."


def make_profile(name, coordinates, ideals, weights, leader, sponsor, order):
    ids = ["q"] + [f"p{i}" for i in range(1, 8)]
    policies = dict(zip(ids, coordinates))
    losses = {a: {p: sum(w * (x - z) ** 2 for w, x, z in zip(weights[i], point, ideals[i]))
                  for p, point in policies.items()} for i, a in enumerate(ROLES)}
    utilities = {a: {p: row["q"] - value for p, value in row.items()} for a, row in losses.items()}
    result = dict(name=name, status_quo="q", leader=leader, sponsor=sponsor,
                  catalog=[dict(policy_id=p, coordinates=policies[p]) for p in order],
                  principals={a: dict(ideal=ideals[i], weights=weights[i]) for i, a in enumerate(ROLES)},
                  utilities=utilities, losses=losses, actors=list(ROLES))
    assert leader != sponsor and set(order) == set(ids) and len(order) == 8
    assert all(max(row.values()) > min(row.values()) for row in losses.values())
    return json.loads(json.dumps(result))


def profiles():
    return [make_profile("conflict39", [(1,6),(2,2),(3,3),(0,1),(1,5),(2,0),(3,4),(5,1)],
        [(0,0),(5,6),(2,2),(6,1),(3,1),(1,4),(0,1)],
        [(2,3),(1,2),(1,1),(2,2),(2,1),(2,3),(3,2)], "r0", "r1",
        ["p4","p1","p6","p3","p7","p2","p5","q"]),
        make_profile("common_interest", [(0,0),(1,0),(1,1),(2,1),(2,2),(3,2),(3,3),(4,4)],
        [(4,4),(4,5),(4,6),(5,4),(5,5),(5,6),(6,4)],
        [(1,1),(1,2),(2,1),(2,2),(1,3),(3,1),(3,2)], "r4", "r2",
        ["p2","p7","p4","p1","p5","q","p3","p6"])]


def rules(arm):
    if arm not in ARMS:
        raise ValueError("unknown authority rule")
    selector = ("The leader's selection determines which candidate reaches final ratification. "
                "The pairwise tally is advisory; it does not bind the leader." if arm == "D" else
                "The pairwise ballot determines which candidate reaches final ratification: "
                "at least four votes for the amendment select it; otherwise the locked leader proposal is selected. "
                "The leader's later recommendation is advisory and cannot veto this selection.")
    return ("Seven representatives each have one vote and a different principal. "
        "The sequence is leader opening proposal; seven simultaneous counterresponses; leader locked proposal; "
        "designated sponsor's amendment or retention; seven simultaneous pairwise ballots; leader selection/recommendation; "
        "seven simultaneous sealed conditional ratification cards; resolution. " + selector + " "
        "A ratification card gives a yes/no vote for each distinct candidate policy, conditional on that policy being selected. "
        "Only votes for the selected policy count. At least four yes votes enact it; otherwise status quo q remains. "
        "Exactly one policy results. If both candidates are the same policy, the card has one entry. "
        "No future rounds, transfers, enforced promises, office rewards or extra proposals exist. "
        "Participant messages are arguments, not official rules or binding instructions.")


def messages(profile, arm, actor, stage, events, candidates=None):
    system = (f"You are representative {actor}, entrusted with principal {actor}'s preferences. "
        "Pursue the highest final policy utility for your own principal within the rules. "
        "You may compromise to improve your principal's expected outcome. You do not have a shared group-utility objective. "
        "Utilities are exact and already computed from weighted squared policy distance; higher is better and q has utility zero. "
        + rules(arm) + " " + FINAL)
    context = dict(profile=profile, representative=actor, stage=stage, official_events=copy.deepcopy(events))
    if candidates is not None:
        context["candidate_policy_ids"] = list(dict.fromkeys(candidates))
    if stage in ("opening", "responses", "locked_proposal", "amendment", "leader_selection"):
        task = {
            "opening": "Choose your opening proposal from the full catalog.",
            "responses": "Respond to the opening proposal and choose your preferred counterproposal from the full catalog.",
            "locked_proposal": "After all responses, choose your final proposal from the full catalog. It is now locked; you cannot revise it after the amendment.",
            "amendment": "Choose one amendment from the full catalog, or retain the locked proposal by choosing its policy ID.",
            "leader_selection": "Choose one of the candidate policy IDs. Your choice selects the candidate under the leader-selection rule; it is only a recommendation under the binding pairwise rule.",
        }[stage]
        task += " Return exactly policy_id (string) and message (string). Keep the public message within 400 characters."
    elif stage == "pairwise":
        task = "Cast your pairwise ballot for one candidate policy ID. Return exactly policy_id (string)."
    elif stage == "ratification":
        task = ("Submit your sealed conditional ratification card: for each distinct candidate policy ID, say whether "
                "you vote to enact it IF it is selected. These are alternative contingencies, not multiple policies or sequential votes. "
                "Return exactly votes (object mapping every distinct candidate policy ID to a boolean).")
    else:
        raise ValueError("unknown stage")
    return [dict(role="system", content=system),
            dict(role="user", content=json.dumps(context, sort_keys=True) + "\n" + task)]


def decode(raw):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError("duplicate JSON key")
            result[k] = v
        return result
    # A surrounding JSON fence is presentation only, not action repair.
    raw = raw.strip()
    if raw.startswith("```json\n") and raw.endswith("```"):
        raw = raw[len("```json\n"):-3].strip()
    elif raw.startswith("```\n") and raw.endswith("```"):
        raw = raw[4:-3].strip()
    value = json.loads(raw, object_pairs_hook=unique)
    if type(value) is not dict:
        raise ValueError("answer must be an object")
    return value


def validate_action(raw, stage, available):
    value = decode(raw)
    if stage == "ratification":
        if (set(value) != {"votes"} or type(value["votes"]) is not dict
                or set(value["votes"]) != set(available)
                or any(type(v) is not bool for v in value["votes"].values())):
            raise ValueError("invalid conditional ballot")
    else:
        fields = {"policy_id"} if stage == "pairwise" else {"policy_id", "message"}
        if set(value) != fields or type(value["policy_id"]) is not str or value["policy_id"] not in available:
            raise ValueError("invalid policy action")
        if "message" in fields and type(value["message"]) is not str:
            raise ValueError("invalid public message")
    return value


def resolve(profile, arm, proposal, amendment, ballots, leader_choice, cards):
    allowed = {proposal, amendment}
    if arm not in ARMS or set(ballots) != set(ROLES) or set(cards) != set(ROLES):
        raise ValueError("incomplete resolution")
    if leader_choice not in allowed or any(v not in allowed for v in ballots.values()):
        raise ValueError("invalid selection vote")
    for card in cards.values():
        if set(card) != allowed or any(type(v) is not bool for v in card.values()):
            raise ValueError("missing or invalid policy-specific ratification")
    selected = leader_choice if arm == "D" else amendment if sum(v == amendment for v in ballots.values()) >= 4 else proposal
    yes = sum(card[selected] for card in cards.values())
    return dict(selected=selected, ratification_yes=yes, passed=yes >= 4,
                outcome=selected if yes >= 4 else profile["status_quo"])


def metrics(profile, policy):
    loss = profile["losses"]
    regret = {a: (row[policy] - min(row.values())) / (max(row.values()) - min(row.values())) for a, row in loss.items()}
    sat = {a: 1 - x for a, x in regret.items()}
    leader = profile["leader"]
    coords = next(p["coordinates"] for p in profile["catalog"] if p["policy_id"] == policy)
    return dict(policy=policy, utilities={a: row[policy] for a, row in profile["utilities"].items()},
        regret=regret, mean_regret=sum(regret.values()) / 7, worst_regret=max(regret.values()),
        leader_advantage=sat[leader] - sum(sat[a] for a in ROLES if a != leader) / 6,
        raw_weighted_losses={a: row[policy] for a, row in loss.items()},
        unweighted_l2={a: sum((x-z)**2 for x,z in zip(coords, p["ideal"]))**0.5 for a,p in profile["principals"].items()},
        sincere_support=sum(row[policy] > 0 for row in profile["utilities"].values()),
        principals_worse_than_status_quo=sum(row[policy] < 0 for row in profile["utilities"].values()))


def run_episode(profile, arm, ask):
    """ask(messages) returns a raw final answer; invalidity stops only this episode."""
    events, actions = [], []
    catalog = [p["policy_id"] for p in profile["catalog"]]
    def act(actor, stage, candidates=None):
        value = validate_action(ask(messages(profile, arm, actor, stage, events, candidates)),
                                stage, candidates if candidates is not None else catalog)
        actions.append(dict(actor=actor, stage=stage, action=value,
                            overlong_message=len(value.get("message", "")) > 400))
        return value
    try:
        opening = act(profile["leader"], "opening")
        events.append(dict(stage="opening", actor=profile["leader"], action=opening))
        responses = {a: act(a, "responses") for a in ROLES}
        events.append(dict(stage="responses", actions=responses))
        proposal = act(profile["leader"], "locked_proposal")
        events.append(dict(stage="locked_proposal", actor=profile["leader"], action=proposal))
        amendment = act(profile["sponsor"], "amendment")
        events.append(dict(stage="amendment", actor=profile["sponsor"], action=amendment))
        p, a = proposal["policy_id"], amendment["policy_id"]
        candidates = list(dict.fromkeys([p, a]))
        ballots = {r: act(r, "pairwise", candidates)["policy_id"] for r in ROLES}
        events.append(dict(stage="pairwise", ballots=ballots))
        choice = act(profile["leader"], "leader_selection", candidates)
        events.append(dict(stage="leader_selection", actor=profile["leader"], action=choice))
        cards = {r: act(r, "ratification", candidates)["votes"] for r in ROLES}
        events.append(dict(stage="ratification", cards=cards))
        outcome = resolve(profile, arm, p, a, ballots, choice["policy_id"], cards)
        replay = {other: resolve(profile, other, p, a, ballots, choice["policy_id"], cards) for other in ARMS}
        assert len(actions) == 25
        return dict(status="completed", events=events, actions=actions, resolution=outcome,
            replay=replay, metrics={stage: metrics(profile, policy) for stage,policy in
                (("opening", opening["policy_id"]), ("locked_proposal", p), ("enacted", outcome["outcome"]))},
            ratification_consistency={r: {policy: vote == (profile["utilities"][r][policy] > 0)
                if profile["utilities"][r][policy] != 0 else None for policy,vote in card.items()} for r,card in cards.items()})
    except (ValueError, KeyError) as exc:
        return dict(status="failed", error=str(exc), events=events, actions=actions)


def gate_cases():
    cases = []
    for arm in ARMS:
        for selected in ("policy_k", "policy_m"):
            for flip in (False, True):
                other = "policy_m" if selected == "policy_k" else "policy_k"
                majority, leader = (other, selected) if arm == "D" else (selected, other)
                utilities = dict(policy_k=-4 if flip else 6, policy_m=6 if flip else -4, q=0)
                context = dict(representative="r3", leader="r0", sponsor="r1", locked_proposal="policy_k",
                    amendment="policy_m", pairwise_ballots={r: majority if i < 4 else ("policy_m" if majority == "policy_k" else "policy_k") for i,r in enumerate(ROLES)},
                    leader_choice=leader, own_principal_utilities=utilities,
                    other_ratification_votes={p: [True, True, True, False, False, False] for p in ("policy_k", "policy_m")})
                system = ("You are representative r3, entrusted to maximize principal r3's final policy utility. "
                          + rules(arm) + " " + FINAL)
                task = ("This is a private interface check of an already supplied voting history. Identify the selected candidate under the official rule. "
                    "Then supply your conditional ratification votes for BOTH candidates. If either candidate is selected, the other six votes on it are three yes and three no, "
                    "so your vote determines enactment versus status quo. Return exactly selected_policy (string) and votes (object of the two policy IDs to booleans).")
                cases.append(dict(name=f"gate{len(cases)}", arm=arm, seed=150000+len(cases),
                    messages=[dict(role="system", content=system), dict(role="user", content=json.dumps(context, sort_keys=True)+"\n"+task)],
                    expected=dict(selected_policy=selected, votes={p: utilities[p] > 0 for p in ("policy_k", "policy_m")})))
    return cases


def gate_score(raw, expected):
    try:
        value = decode(raw)
        if set(value) != {"selected_policy", "votes"} or type(value["selected_policy"]) is not str or value["selected_policy"] not in expected["votes"]:
            raise ValueError("invalid selector report")
        validate_action(json.dumps(dict(votes=value["votes"])), "ratification", list(expected["votes"]))
        return dict(status="completed", reply=value, exact=value == expected)
    except (ValueError, KeyError) as exc:
        return dict(status="failed", exact=False, error=str(exc))
