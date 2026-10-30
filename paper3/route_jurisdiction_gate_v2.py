"""Clearer route-jurisdiction prerequisite; not an institutional result.

The old gate asked for `review_binding`, which one answer plausibly read as
the reviewer's *decision* rather than the authority of that decision. This
separate prospective instrument asks whether a veto legally applies to the
chosen route, even if the recorded reviewer decision is approval. It keeps
the old failed responses and scores untouched.
"""
from __future__ import annotations

import copy
import json

from paper3 import route_jurisdiction as game
from paper3 import route_jurisdiction_gate as old_gate


RULE_TASK = (
    "The offer, ballots and review above are already fixed. Apply the official "
    "rule, then identify the highest-utility policy for your own principal "
    "from the public utility table. Return one JSON object with outcome "
    "(enacted policy ID), review_veto_applies (boolean), and own_best_policy "
    "(policy ID). Set review_veto_applies to true exactly when a rejection "
    "by the reviewer could block this route after its vote threshold is met; "
    "set it to false when review is merely advisory on this route. This field "
    "is about legal authority, NOT whether the reviewer actually approved."
)


def cases():
    rows = copy.deepcopy(old_gate.cases())
    for row in rows:
        if row["kind"] != "rule":
            continue
        user = row["messages"][1]["content"]
        context = user.split("\n", 1)[0]
        row["messages"][1]["content"] = context + "\n" + RULE_TASK
        expected = row["expected"]
        row["expected"] = dict(outcome=expected["outcome"],
                               review_veto_applies=expected["review_binding"],
                               own_best_policy=expected["own_best_policy"])
    assert len(rows) == 12
    return rows


def _json_object(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(
                           ValueError("nonfinite JSON")))
    if type(value) is not dict:
        raise ValueError("action must be JSON object")
    return value


def score(raw, case):
    """Project only prospectively declared fields; do not infer missing ones."""
    try:
        value = _json_object(raw)
        if case["kind"] == "rule":
            fields = case["expected"]
            if (type(value.get("outcome")) is not str or
                    type(value.get("own_best_policy")) is not str or
                    type(value.get("review_veto_applies")) is not bool):
                raise ValueError("invalid rule fields")
            action = {key: value[key] for key in fields}
        elif case["kind"] == "action":
            stage, profile = case["stage"], case["profile"]
            if stage == "recommendation":
                if type(value.get("policy_id")) is not str or value["policy_id"] not in profile["policies"]:
                    raise ValueError("invalid recommendation")
                action = {"policy_id": value["policy_id"]}
            elif stage == "offer":
                if (type(value.get("policy_id")) is not str or
                        value["policy_id"] not in profile["policies"] or
                        type(value.get("route")) is not str or
                        value["route"] not in game.ROUTES):
                    raise ValueError("invalid offer")
                action = {"policy_id": value["policy_id"], "route": value["route"]}
            elif stage == "ballot":
                if type(value.get("yes")) is not bool:
                    raise ValueError("invalid ballot")
                action = {"yes": value["yes"]}
            elif stage == "review":
                if type(value.get("approve")) is not bool:
                    raise ValueError("invalid review")
                action = {"approve": value["approve"]}
            else:
                raise ValueError("unknown action stage")
            fields = case["expected"]
        else:
            raise ValueError("unknown case kind")
        return dict(status="completed", exact=all(action.get(key) == expected
                                                   for key, expected in fields.items()),
                    reply=action)
    except (ValueError, KeyError, TypeError) as exc:
        return dict(status="failed", exact=False, error=type(exc).__name__)
