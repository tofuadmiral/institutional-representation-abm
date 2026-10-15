"""Fresh, engineering-only contexts for the Paper 3 strict-action gate.

These are not repetitions of failed sponsorship episodes and carry no
scientific outcome. The gate tests whether the pinned reasoning route can
return one-key JSON actions under a strict schema.
"""
from __future__ import annotations

from copy import deepcopy

from paper3 import agenda_sponsorship_institution as institution
from paper3 import agenda_sponsorship_opportunity as opportunity
from paper3 import direct_ratification as base


SEED_BASE = 1340000
PROFILE_SEEDS = (2026100300, 2026100301)
ORDER_SEEDS = (2026100400, 2026100401)
OLD_FINAL_INSTRUCTION = "Return only\nthe requested JSON action and reason privately."
NEW_FINAL_INSTRUCTION = (
    "Reason privately in the native reasoning channel. The final answer must "
    "contain only the requested one-key JSON object, without an explanation "
    "or any extra key."
)


def items():
    rows = []
    for index, (profile_seed, order_seed) in enumerate(
            zip(PROFILE_SEEDS, ORDER_SEEDS, strict=True)):
        roles = tuple((index + offset) % 7 for offset in range(7))
        labels = tuple(base.POLICIES[(index + offset) % 3]
                       for offset in range(3))
        item = opportunity.draw("split", ("y_high", "c_high")[index],
                                profile_seed, role_permutation=roles,
                                label_permutation=labels)
        rows.append(opportunity.with_order(item,
                    ("flexible_first", "flexible_last")[index], order_seed))
    return rows


def schema(stage, compromises):
    if stage == "advocacy":
        key, shape = "message", dict(type="string",
                                     description="A concise public advocacy message")
    elif stage == "sponsor":
        key, shape = "policy", dict(type="string",
                                    enum=[*compromises, "none"],
                                    description="The one motion sponsored, or none")
    elif stage == "vote":
        key, shape = "vote", dict(type="boolean",
                                  description="Whether to enact the floor policy")
    else:
        raise ValueError("unknown stage")
    return dict(type="object", properties={key: shape}, required=[key],
                additionalProperties=False)


def _messages(item, arm, actor, stage, group):
    advocacy = [dict(actor=representative,
                     message="I will seek the best enacted outcome for my district.")
                for representative in base.ACTORS]
    y, c = item["compromises"]
    if stage == "advocacy":
        messages = institution.messages(item, arm, actor, stage, None)
    elif stage == "sponsor":
        prefix = [dict(actor=representative, policy=y if index % 2 else c)
                  for index, representative in enumerate(
                      item["sponsor_order"][:(0, 1, 3, 5)[group]])]
        messages = institution.messages(item, arm, actor, stage, advocacy,
                                        prefix)
    else:
        policies = ((y, y, y, y, c, c),
                    (y, y, y, c, c, c),
                    (c, c, c, c, y, y),
                    (y, c, y, c, y, c))[group]
        sponsorships = [dict(actor=representative, policy=policy)
                        for representative, policy in zip(
                            item["sponsor_order"], policies, strict=True)]
        floor = institution.motion(item, sponsorships)["floor_policy"]
        messages = institution.messages(item, arm, actor, stage, advocacy,
                                        sponsorships, floor)
    result = deepcopy(messages)
    system = result[0]["content"]
    if system.count(OLD_FINAL_INSTRUCTION) != 1:
        raise ValueError("ambiguous source instruction changed")
    result[0]["content"] = system.replace(OLD_FINAL_INSTRUCTION,
                                           NEW_FINAL_INSTRUCTION)
    return result


def contexts():
    profiles = items()
    stages = ("advocacy", "sponsor", "vote", "vote") * 4
    rows = []
    for index, stage in enumerate(stages):
        group = index // 4
        item = profiles[index % 2]
        arm = institution.ARMS[group % 2]
        actor = (item["sponsor_order"][(0, 1, 3, 5)[group]]
                 if stage == "sponsor" else base.ACTORS[(index + group) % 7])
        rows.append(dict(id=f"schema-gate-{index:02d}",
                         seed=SEED_BASE + index, stage=stage, arm=arm,
                         profile_id=item["profile"]["id"],
                         compromises=list(item["compromises"]),
                         messages=_messages(item, arm, actor, stage, group)))
    if (len(rows) != 16 or len({row["seed"] for row in rows}) != 16 or
            [row["stage"] for row in rows].count("vote") != 8):
        raise ValueError("gate inventory")
    return rows
