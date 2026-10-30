"""Offline common-advocacy sponsorship institution.

Agents write advocacy before learning which visibility rule will govern
sponsorship. That exact seven-message transcript is then supplied to both
arms, isolating the later formal-filing information channel conditional on
the shared transcript. This is a controlled mechanism study, not a claim
about institutions with endogenous pre-rule advocacy.
"""
from __future__ import annotations

from copy import deepcopy

from paper3 import agenda_schema_interface as interface
from paper3 import agenda_sponsorship_institution as game
from paper3 import direct_ratification as base


NEUTRAL_RULE = (
    "INSTITUTION AT ADVOCACY: The binding sponsorship visibility rule will "
    "be announced after all seven advocacy messages are collected and "
    "broadcast. It may be private filing or public sequential filing. "
    "You do not know which rule will apply now. The six outsiders will "
    "still each file one irrevocable sponsorship or none, four matching "
    "filings will qualify a motion, and seven sealed ballots will decide "
    "enactment."
)


def messages(item, arm, actor, stage, advocacy=None, prefix=None, floor=None):
    if stage == "advocacy":
        if arm is not None or advocacy is not None or prefix is not None or floor is not None:
            raise ValueError("advocacy must be arm-blind")
        result = game.messages(item, "sealed", actor, stage, None)
        if result[0]["content"].count(game.RULES["sealed"]) != 1:
            raise ValueError("source rule changed")
        result = deepcopy(result)
        result[0]["content"] = result[0]["content"].replace(
            game.RULES["sealed"], NEUTRAL_RULE)
    else:
        if arm not in game.ARMS or stage not in ("sponsor", "vote"):
            raise ValueError("known institutional arm required")
        result = game.messages(item, arm, actor, stage, advocacy, prefix, floor)
        result = deepcopy(result)
    system = result[0]["content"]
    if system.count(interface.OLD_FINAL_INSTRUCTION) != 1:
        raise ValueError("source output instruction changed")
    result[0]["content"] = system.replace(interface.OLD_FINAL_INSTRUCTION,
                                           interface.NEW_FINAL_INSTRUCTION)
    return result


def advocacy(item, ask):
    """ask(actor, stage, messages, index) returns exact final-answer text."""
    game.validate_item(item)
    result = []
    for index, actor in enumerate(base.ACTORS):
        raw = ask(actor, "advocacy", messages(item, None, actor, "advocacy"),
                  index)
        action = game.parse_action(raw, "advocacy", item["compromises"])
        result.append(dict(actor=actor, message=action["message"]))
    return result


def arm_episode(item, arm, common_advocacy, ask):
    """Run 13 binding sponsor/ballot actions after shared advocacy.

    ask(actor, stage, messages, index) receives index 0..12. The caller
    owns persistence, missingness and the exact cross-arm seed schedule.
    """
    game.validate_item(item)
    base.require(arm in game.ARMS and type(common_advocacy) is list and
                 len(common_advocacy) == 7 and
                 [entry["actor"] for entry in common_advocacy] ==
                 list(base.ACTORS), "common advocacy inventory")
    index = 0
    sponsorships = []
    for actor in item["sponsor_order"]:
        raw = ask(actor, "sponsor",
                  messages(item, arm, actor, "sponsor", common_advocacy,
                           sponsorships), index)
        action = game.parse_action(raw, "sponsor", item["compromises"])
        sponsorships.append(dict(actor=actor, policy=action["policy"]))
        index += 1
    floor = game.motion(item, sponsorships)["floor_policy"]
    votes = []
    for actor in base.ACTORS:
        raw = ask(actor, "vote",
                  messages(item, arm, actor, "vote", common_advocacy,
                           sponsorships, floor), index)
        action = game.parse_action(raw, "vote", item["compromises"])
        votes.append(action["vote"])
        index += 1
    base.require(index == 13, "arm action count")
    return dict(arm=arm, sponsorships=sponsorships, votes=votes,
                outcome=game.score(item, arm, common_advocacy,
                                   sponsorships, votes), calls=index)
