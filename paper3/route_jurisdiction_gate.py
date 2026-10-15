"""Prospective, offline route-interface gate cases; no inference or billing.

Eight exact rule-arithmetic cases and four actual-stage action controls. This
tests a prerequisite for a later pilot, not a scientific institutional effect.
The runner must separately verify native reasoning, model/provider identity,
complete usage receipts, conservative reservations, and the fresh protocol.
"""
from __future__ import annotations

import json

from paper3 import route_jurisdiction as game


def _profile():
    rows = {
        "r0": [6, -4, 2], "r1": [4, 2, -3], "r2": [3, -1, 5],
        "r3": [-2, 4, 1], "r4": [-5, 3, 2], "r5": [2, -4, 3],
        "r6": [-3, 1, 4],
    }
    return game.make_profile("gate-only", {
        a: dict(q=0, p0=v[0], p1=v[1], p2=v[2]) for a, v in rows.items()
    }, proposer="r0", reviewer="r6", committee=["r1", "r2", "r3"],
       floor_threshold=5, committee_threshold=2)


def _aligned_profile():
    return game.make_profile("aligned-gate-only", {
        f"r{i}": dict(q=0, p0=10 - i, p1=2, p2=-2) for i in range(7)
    }, proposer="r0", reviewer="r6", committee=["r1", "r2", "r3"],
       floor_threshold=5, committee_threshold=2)


def cases():
    profile = _profile()
    # Distinct boundary and jurisdiction checks; no case is copied from the
    # discovery frame. Each context supplies the actions whose result is asked.
    configurations = (
        ("narrow", "floor", ("r0", "r1", "r2", "r4", "r5"), False, "r0"),
        ("comprehensive", "floor", ("r0", "r1", "r2", "r4", "r5"), False, "r3"),
        ("narrow", "floor", ("r0", "r1", "r3", "r6"), True, "r2"),
        ("comprehensive", "floor", ("r0", "r1", "r3", "r6"), True, "r4"),
        ("narrow", "committee", ("r0", "r1", "r3", "r6"), True, "r5"),
        ("comprehensive", "committee", ("r0", "r1", "r3", "r6"), True, "r6"),
        ("narrow", "committee", ("r0", "r1", "r3", "r6"), False, "r1"),
        ("comprehensive", "committee", ("r0", "r1", "r4", "r5", "r6"), True, "r2"),
    )
    result = []
    for i, (arm, route, yes_actors, review, actor) in enumerate(configurations):
        ballots = {a: a in yes_actors for a in profile["actors"]}
        offer = dict(policy_id="p0", route=route)
        resolution = game.resolve(profile, arm, offer, ballots, review)
        row = profile["utilities"][actor]
        own_best = max(profile["policies"], key=lambda p: row[p])
        context = dict(actors=profile["actors"], proposer=profile["proposer"], reviewer=profile["reviewer"],
                       utilities=profile["utilities"], committee=profile["committee"],
                       floor_threshold=profile["floor_threshold"],
                       committee_threshold=profile["committee_threshold"], acting_for=actor,
                       fixed_offer=offer, fixed_ballots=ballots, fixed_recorded_review=review)
        prompt = ("The offer, ballots and review above are already fixed. Apply the official rule, then identify "
                  "the highest-utility policy for your own principal from the public utility table. "
                  "Return exactly outcome (policy ID string), review_binding (boolean), "
                  "and own_best_policy (policy ID string) in one JSON object.")
        result.append(dict(name=f"rule-{i:02d}", kind="rule", arm=arm,
                           messages=[dict(role="system", content=f"You are representative {actor}. "
                                          + game._rule(arm, profile)),
                                     dict(role="user", content=json.dumps(context, sort_keys=True) + "\n" + prompt)],
                           expected=dict(outcome=resolution["outcome"],
                                         review_binding=resolution["review_binding"],
                                         own_best_policy=own_best)))

    aligned = _aligned_profile()
    recommendations = {a: "p0" for a in aligned["actors"]}
    offer = dict(policy_id="p0", route="floor")
    controls = (
        ("recommendation", aligned, "narrow", "r3", {}, dict(policy_id="p0")),
        ("offer", aligned, "narrow", "r0", dict(recommendations=recommendations),
         dict(policy_id="p0")),
        ("ballot", aligned, "comprehensive", "r4",
         dict(recommendations=recommendations, offer=offer), dict(yes=True)),
        ("review", profile, "comprehensive", "r6",
         dict(recommendations={a: "p0" for a in profile["actors"]}, offer=offer,
              ballots={a: j < 5 for j, a in enumerate(profile["actors"])}),
         dict(approve=False)),
    )
    for stage, p, arm, actor, kwargs, expected in controls:
        result.append(dict(name=f"action-{stage}", kind="action", arm=arm, stage=stage,
                           messages=game.messages(p, arm, actor, stage, **kwargs),
                           profile=p, expected=expected))
    assert len(result) == 12
    return result


def score(raw, case):
    """No output repair or partial credit; runner adds transport/receipt checks."""
    try:
        if case["kind"] == "action":
            value = game.validate_action(raw, case["stage"], case["profile"])
            correct = all(value.get(k) == v for k, v in case["expected"].items())
        elif case["kind"] == "rule":
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate JSON key")
                    result[key] = value
                return result
            value = json.loads(raw, object_pairs_hook=unique)
            expected = case["expected"]
            if (type(value) is not dict or set(value) != set(expected)
                    or type(value["outcome"]) is not str
                    or type(value["own_best_policy"]) is not str
                    or type(value["review_binding"]) is not bool):
                raise ValueError("invalid rule report")
            correct = value == expected
        else:
            raise ValueError("unknown case kind")
        return dict(status="completed", exact=correct, reply=value)
    except (ValueError, KeyError, TypeError) as exc:
        return dict(status="failed", exact=False, error=str(exc))
