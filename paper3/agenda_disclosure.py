"""Authority x disclosure-timing engine; no inference or filesystem effects.

Early arms are the unchanged agenda_rights episodes. The late condition runs one
shared nine-decision prefix under a publicly known fair lottery over the two
selectors, announces the draw after the locked proposal, and clones the prefix
into two fresh interacting sixteen-decision continuations (D and B). Agents are
never told a definite rule that is later switched. Branches share history by
construction; they are not independent draws.
"""
from __future__ import annotations

import copy
from fractions import Fraction

from paper3 import agenda_rights as game
from paper3.agenda_benchmarks import generated_profile
from paper3.agenda_disclosure_benchmarks import disclosure_benchmark

PREFIX_DECISIONS = 9  # opening, seven responses, locked proposal
LOTTERY = ("Which selection rule applies is not yet decided. After the leader's locked proposal and before the "
           "sponsor acts, a public fair draw (probability 1/2 each) fixes one of the two rules below for the rest "
           "of this episode, and everyone is told the result. Possible leader rule: {D} Possible ballot rule: {B}")
DRAWN = {"D": "The public draw has occurred: the leader rule applies.",
         "B": "The public draw has occurred: the ballot rule applies."}


def rule_parts():
    """Split the frozen rule text into shared prefix, per-arm selector, shared suffix."""
    d, b = game.rules("D"), game.rules("B")
    i = 0
    while d[i] == b[i]:
        i += 1
    j = 0
    while d[-1 - j] == b[-1 - j]:
        j += 1
    # Snap to sentence boundaries so each selector is whole sentences.
    i = d.rindex(". ", 0, i) + 2
    j = len(d) - d.index(". ", len(d) - j - 1) - 1
    return d[:i], {"D": d[i:len(d) - j], "B": b[i:len(b) - j]}, d[len(d) - j:]


def rules_late(revealed):
    prefix, selectors, suffix = rule_parts()
    text = prefix + LOTTERY.format(D=selectors["D"].strip(), B=selectors["B"].strip()) + suffix
    if revealed is None:
        return text
    if revealed not in game.ARMS:
        raise ValueError("unknown authority rule")
    return text + " " + DRAWN[revealed]


def messages_late(profile, actor, stage, events, revealed, candidates=None):
    # Identical to the early messages except the rule text.
    messages = game.messages(profile, "D", actor, stage, events, candidates)
    system = messages[0]["content"]
    assert system.count(game.rules("D")) == 1
    messages[0]["content"] = system.replace(game.rules("D"), rules_late(revealed))
    return messages


def _continuation(profile, arm, ask, prefix_events, prefix_actions, locked):
    events = copy.deepcopy(prefix_events) + [dict(stage="authority_draw", rule=arm)]
    actions = copy.deepcopy(prefix_actions)
    catalog = [p["policy_id"] for p in profile["catalog"]]
    def act(actor, stage, candidates=None):
        raw = ask(messages_late(profile, actor, stage, events, arm, candidates), len(actions))
        value = game.validate_action(raw, stage, candidates if candidates is not None else catalog)
        actions.append(dict(actor=actor, stage=stage, action=value,
                            overlong_message=len(value.get("message", "")) > 400))
        return value
    try:
        amendment = act(profile["sponsor"], "amendment")
        events.append(dict(stage="amendment", actor=profile["sponsor"], action=amendment))
        p, a = locked["policy_id"], amendment["policy_id"]
        candidates = list(dict.fromkeys([p, a]))
        ballots = {r: act(r, "pairwise", candidates)["policy_id"] for r in game.ROLES}
        events.append(dict(stage="pairwise", ballots=ballots))
        choice = act(profile["leader"], "leader_selection", candidates)
        events.append(dict(stage="leader_selection", actor=profile["leader"], action=choice))
        cards = {r: act(r, "ratification", candidates)["votes"] for r in game.ROLES}
        events.append(dict(stage="ratification", cards=cards))
        outcome = game.resolve(profile, arm, p, a, ballots, choice["policy_id"], cards)
        assert len(actions) == 25
        return dict(status="completed", events=events, actions=actions, resolution=outcome,
                    metrics={stage: game.metrics(profile, policy) for stage, policy in
                             (("locked_proposal", p), ("enacted", outcome["outcome"]))})
    except (ValueError, KeyError) as exc:
        return dict(status="failed", error=str(exc), events=events, actions=actions)


def run_late(profile, ask, order):
    """ask(messages, position) returns a raw final answer; position is 0..24 along a path."""
    if sorted(order) != sorted(game.ARMS):
        raise ValueError("branch order must contain D and B once")
    events, actions = [], []
    catalog = [p["policy_id"] for p in profile["catalog"]]
    def act(actor, stage):
        raw = ask(messages_late(profile, actor, stage, events, None), len(actions))
        value = game.validate_action(raw, stage, catalog)
        actions.append(dict(actor=actor, stage=stage, action=value,
                            overlong_message=len(value.get("message", "")) > 400))
        return value
    try:
        opening = act(profile["leader"], "opening")
        events.append(dict(stage="opening", actor=profile["leader"], action=opening))
        responses = {r: act(r, "responses") for r in game.ROLES}
        events.append(dict(stage="responses", actions=responses))
        locked = act(profile["leader"], "locked_proposal")
        events.append(dict(stage="locked_proposal", actor=profile["leader"], action=locked))
    except (ValueError, KeyError) as exc:
        failed = dict(status="failed", error="prefix failed: " + str(exc))
        return dict(status="failed", error=str(exc), prefix_events=events, prefix_actions=actions,
                    branch_order=list(order), branches={a: dict(failed) for a in game.ARMS})
    assert len(actions) == PREFIX_DECISIONS
    branches = {arm: _continuation(profile, arm, ask, events, actions, locked) for arm in order}
    done = [b["status"] == "completed" for b in branches.values()]
    return dict(status="completed" if all(done) else "partial" if any(done) else "failed",
                prefix_events=events, prefix_actions=actions, branch_order=list(order),
                locked_proposal=locked["policy_id"],
                prefix_metrics=dict(opening=game.metrics(profile, opening["policy_id"]),
                                    locked_proposal=game.metrics(profile, locked["policy_id"])),
                branches=branches)


def interaction(profile, outcomes):
    """(late B - late D) - (early B - early D) on enacted-policy metrics; all four cells required."""
    if any(set(outcomes.get(c, {})) != set(game.ARMS) for c in ("early", "late")):
        raise ValueError("interaction needs all four enacted outcomes; never impute")
    m = {c: {a: game.metrics(profile, p) for a, p in v.items()} for c, v in outcomes.items()}
    def contrast(get):
        return (get(m["late"]["B"]) - get(m["late"]["D"])) - (get(m["early"]["B"]) - get(m["early"]["D"]))
    return dict(outcomes=outcomes,
                mean_regret_interaction=contrast(lambda x: x["mean_regret"]),
                leader_advantage_interaction=contrast(lambda x: x["leader_advantage"]),
                worst_regret_interaction=contrast(lambda x: x["worst_regret"]),
                principal_utility_interaction={r: contrast(lambda x, r=r: x["utilities"][r]) for r in game.ROLES},
                scope="one paired profile; branch continuations share a prefix; descriptive, not natural mediation")


POSITIVE_MIN = Fraction(1, 20)


def select_profiles(start=1004000, per_stratum=2, limit=1000):
    """Prospective theory-only stratification; never uses LLM behaviour or outcomes.

    positive: normalized leader information value >= 1/20.
    zero_control: information value 0 and the leader's own-optimal set under each
    known rule is a proper subset of the menu (leader not indifferent to all).
    Seeds are scanned in increasing order; the first qualifying seeds are taken.
    """
    positive, zero, scanned = [], [], []
    for seed in range(start, start + limit):
        result = disclosure_benchmark(generated_profile(seed))
        value = Fraction(result["leader_value_of_information_normalized_exact"])
        early = result["early_own_best_proposals"]
        scanned.append(dict(seed=seed, normalized_information_value=str(value)))
        if value >= POSITIVE_MIN and len(positive) < per_stratum:
            positive.append(seed)
        elif value == 0 and all(len(s) < 8 for s in early.values()) and len(zero) < per_stratum:
            zero.append(seed)
        if len(positive) == per_stratum and len(zero) == per_stratum:
            break
    return dict(positive=positive, zero_control=zero, scanned=scanned,
                rule="scan seeds upward from %d; positive: normalized value >= %s; zero_control: value 0 "
                     "and leader strictly prefers a proper subset under each known rule" % (start, POSITIVE_MIN))
