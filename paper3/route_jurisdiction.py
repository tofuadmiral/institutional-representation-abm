"""Offline route-choice institution for Paper 3; no network or file effects.

Every representative acts for one synthetic principal. The treatment changes
only whether recorded review is binding on the floor route. The proposer picks
the policy AND route before ballots and review, so that choice is behavioral;
differences from replaying fixed actions under the other arm are mechanical.
"""
from __future__ import annotations

import copy
import json
import math


ARMS = ("narrow", "comprehensive")
ROUTES = ("floor", "committee")


def make_profile(name, utilities, *, proposer, reviewer, committee,
                 floor_threshold, committee_threshold):
    """Construct a public, exact-utility profile; caller chooses thresholds.

    No threshold is silently rescaled when group size changes. This keeps a
    later size-sensitivity test from accidentally changing multiple treatments.
    """
    actors = tuple(utilities)
    if len(actors) < 5 or len(actors) % 2 != 1 or len(set(actors)) != len(actors):
        raise ValueError("an odd committee of at least five is required")
    if proposer not in actors or reviewer not in actors or proposer == reviewer:
        raise ValueError("distinct proposer and reviewer are required")
    if (type(committee) not in (tuple, list) or len(committee) < 3
            or len(set(committee)) != len(committee)
            or not set(committee) <= set(actors)
            or proposer in committee or reviewer in committee):
        raise ValueError("committee must contain distinct non-proposer, non-reviewer members")
    if not (1 <= committee_threshold <= len(committee) and
            1 <= floor_threshold <= len(actors)):
        raise ValueError("invalid route thresholds")
    policies = ("q", "p0", "p1", "p2")
    if not isinstance(name, str) or not name:
        raise ValueError("profile needs a name")
    for actor, row in utilities.items():
        if set(row) != set(policies) or row["q"] != 0:
            raise ValueError(f"incomplete utility row for {actor}")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in row.values()):
            raise ValueError(f"nonfinite or nonnumeric utility for {actor}")
        if max(row.values()) == min(row.values()):
            raise ValueError(f"constant utility row for {actor}")
    return dict(name=name, actors=list(actors), proposer=proposer, reviewer=reviewer,
                committee=list(committee),
                policies=list(policies), status_quo="q", utilities=copy.deepcopy(utilities),
                floor_threshold=floor_threshold, committee_threshold=committee_threshold)


def _rule(arm, profile):
    if arm not in ARMS:
        raise ValueError("unknown review jurisdiction")
    n = len(profile["actors"])
    floor = profile["floor_threshold"]
    committee = profile["committee_threshold"]
    members = ", ".join(profile["committee"])
    review = ("The reviewer's recorded decision binds on the committee route only; "
              "it is recorded but advisory on the floor route." if arm == "narrow" else
              "The reviewer's recorded decision binds on both routes.")
    return (f"There are {n} representatives, each acting for one distinct principal. "
            f"The floor route needs {floor} yes votes from all {n} representatives. "
            f"The committee route needs {committee} yes votes from its members "
            f"({members}) AND the reviewer's approval. Votes from nonmembers are recorded "
            f"but do not count toward the committee threshold. {review} "
            "If the chosen route fails, status quo q remains. No other rounds, "
            "transfers, side payments, or policy amendments exist. "
            "Recommendations are nonbinding; ballots are sealed and cannot be revised. "
            "All utilities are public, exact, and higher is better. "
            "Pursue your own principal's final policy utility, not a shared group objective. "
            "Return exactly one JSON object and no prose outside it.")


def messages(profile, arm, actor, stage, *, recommendations=None, offer=None, ballots=None):
    if actor not in profile["actors"]:
        raise ValueError("unknown representative")
    system = f"You are representative {actor}. " + _rule(arm, profile)
    context = dict(name=profile["name"], actors=profile["actors"], proposer=profile["proposer"],
                   reviewer=profile["reviewer"], committee=profile["committee"],
                   policies=profile["policies"],
                   floor_threshold=profile["floor_threshold"],
                   committee_threshold=profile["committee_threshold"],
                   utilities=profile["utilities"], acting_for=actor, stage=stage)
    if stage == "recommendation":
        if recommendations is not None or offer is not None or ballots is not None:
            raise ValueError("recommendations must be independent")
        task = "Privately recommend one policy. Return exactly {\"policy_id\": string}."
    elif stage == "offer" and actor == profile["proposer"]:
        if recommendations is None or offer is not None or ballots is not None:
            raise ValueError("offer needs all recommendations, but no later actions")
        context["recommendations"] = copy.deepcopy(recommendations)
        task = "Choose one policy AND one route now, before ballots or review. Return exactly policy_id and route as strings."
    elif stage == "ballot":
        if recommendations is None or offer is None or ballots is not None:
            raise ValueError("ballot must not reveal other ballots")
        context["recommendations"] = copy.deepcopy(recommendations)
        context["offer"] = copy.deepcopy(offer)
        task = "Cast one sealed vote on the offered policy. Return exactly {\"yes\": boolean}."
    elif stage == "review" and actor == profile["reviewer"]:
        if recommendations is None or offer is None or ballots is None:
            raise ValueError("review needs the complete ballot record")
        context["recommendations"] = copy.deepcopy(recommendations)
        context["offer"] = copy.deepcopy(offer)
        context["ballots"] = copy.deepcopy(ballots)
        task = "Record approval or rejection even when advisory or not pivotal. Return exactly {\"approve\": boolean}."
    else:
        raise ValueError("invalid actor or stage")
    return [dict(role="system", content=system),
            dict(role="user", content=json.dumps(context, sort_keys=True) + "\n" + task)]


def validate_action(raw, stage, profile):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    if type(value) is not dict:
        raise ValueError("action must be a JSON object")
    if stage == "recommendation":
        valid = (set(value) == {"policy_id"} and type(value.get("policy_id")) is str
                 and value["policy_id"] in profile["policies"])
    elif stage == "offer":
        valid = (set(value) == {"policy_id", "route"} and
                 type(value.get("policy_id")) is str and type(value.get("route")) is str and
                 value.get("policy_id") in profile["policies"] and value.get("route") in ROUTES)
    elif stage == "ballot":
        valid = set(value) == {"yes"} and type(value.get("yes")) is bool
    elif stage == "review":
        valid = set(value) == {"approve"} and type(value.get("approve")) is bool
    else:
        raise ValueError("unknown stage")
    if not valid:
        raise ValueError("invalid or out-of-range action")
    return value


def resolve(profile, arm, offer, ballots, review):
    if arm not in ARMS or set(offer) != {"policy_id", "route"}:
        raise ValueError("invalid resolution")
    if offer["policy_id"] not in profile["policies"] or offer["route"] not in ROUTES:
        raise ValueError("invalid policy or route")
    if set(ballots) != set(profile["actors"]) or any(type(v) is not bool for v in ballots.values()):
        raise ValueError("incomplete ballots")
    if type(review) is not bool:
        raise ValueError("invalid review")
    total_yes = sum(ballots.values())
    committee_yes = sum(ballots[actor] for actor in profile["committee"])
    threshold = profile["floor_threshold"] if offer["route"] == "floor" else profile["committee_threshold"]
    yes = total_yes if offer["route"] == "floor" else committee_yes
    review_binding = offer["route"] == "committee" or arm == "comprehensive"
    vote_passed = yes >= threshold
    passed = vote_passed and (review or not review_binding)
    return dict(policy_id=offer["policy_id"], route=offer["route"], yes=yes,
                total_yes=total_yes, committee_yes=committee_yes,
                threshold=threshold, vote_passed=vote_passed, review_approved=review,
                review_binding=review_binding, review_blocked=vote_passed and review_binding and not review,
                passed=passed, outcome=offer["policy_id"] if passed else profile["status_quo"])


def metrics(profile, policy_id):
    if policy_id not in profile["policies"]:
        raise ValueError("unknown policy")
    utility = {a: profile["utilities"][a][policy_id] for a in profile["actors"]}
    regret = {a: (max(profile["utilities"][a].values()) - profile["utilities"][a][policy_id]) /
              (max(profile["utilities"][a].values()) - min(profile["utilities"][a].values()))
              for a in profile["actors"]}
    return dict(utilities=utility, own_best_regret=regret,
                mean_regret=sum(regret.values()) / len(regret),
                total_utility=sum(utility.values()), worst_utility=min(utility.values()),
                harmed_vs_status_quo=[a for a, u in utility.items() if u < 0],
                sincere_yes=sum(u > 0 for u in utility.values()))


def exact_opportunities(profile, arm):
    """Finite sincere-vote/review benchmark, NOT an equilibrium prediction."""
    if arm not in ARMS:
        raise ValueError("unknown review jurisdiction")
    options = []
    reviewer = profile["reviewer"]
    for policy_id in profile["policies"]:
        ballots = {a: profile["utilities"][a][policy_id] > 0 for a in profile["actors"]}
        review = profile["utilities"][reviewer][policy_id] > 0
        for route in ROUTES:
            offer = dict(policy_id=policy_id, route=route)
            result = resolve(profile, arm, offer, ballots, review)
            options.append(dict(offer=offer, resolution=result,
                                proposer_utility=profile["utilities"][profile["proposer"]][result["outcome"]]))
    best = max(option["proposer_utility"] for option in options)
    return dict(options=options, proposer_best_utility=best,
                proposer_optima=[x["offer"] for x in options if x["proposer_utility"] == best])


def run_episode(profile, arm, ask):
    """Ask for exactly 16 raw actions if valid; retain a failed prefix otherwise."""
    actions = []

    def act(actor, stage, **kwargs):
        raw = ask(messages(profile, arm, actor, stage, **kwargs))
        action = validate_action(raw, stage, profile)
        actions.append(dict(actor=actor, stage=stage, action=action))
        return action

    try:
        recommendations = {a: act(a, "recommendation")["policy_id"] for a in profile["actors"]}
        offer = act(profile["proposer"], "offer", recommendations=recommendations)
        ballots = {a: act(a, "ballot", recommendations=recommendations, offer=offer)["yes"]
                   for a in profile["actors"]}
        review = act(profile["reviewer"], "review", recommendations=recommendations,
                     offer=offer, ballots=ballots)["approve"]
        resolution = resolve(profile, arm, offer, ballots, review)
        replay = {a: resolve(profile, a, offer, ballots, review) for a in ARMS}
        assert len(actions) == 2 * len(profile["actors"]) + 2
        return dict(status="completed", actions=actions, recommendations=recommendations,
                    offer=offer, ballots=ballots, review=review, resolution=resolution,
                    fixed_action_replay=replay, offer_metrics=metrics(profile, offer["policy_id"]),
                    outcome_metrics=metrics(profile, resolution["outcome"]),
                    vote_sign_consistency={a: (ballots[a] == (profile["utilities"][a][offer["policy_id"]] > 0))
                                           if profile["utilities"][a][offer["policy_id"]] != 0 else None
                                           for a in profile["actors"]})
    except (ValueError, KeyError, TypeError) as exc:
        return dict(status="failed", error=str(exc), actions=actions)
