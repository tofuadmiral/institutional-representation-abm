"""Prospective axis/ballot clarification; original frozen interface is unchanged.

Adds a common data legend, not decisions, expected answers or extra information.
The same legend must be used for all four arms and actual institutional actions.
"""
from copy import deepcopy
import json

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_interface as original

SYSTEM = original.SYSTEM + """
Data convention: every array uses zero-based IDs. In utilities[t][d][c][p],
t is legislative term (0 first, 1 terminal), d is district, c is citizen,
and p is policy. A citizen row lists that ONE citizen's utility across policies;
it is not a policy's utilities across citizens. Sum utilities[t][d][c][p]
over citizens c to get district d's utility for policy p in term t.
menu_assessments[d][p] lists both assessment results for the CURRENT term.
Its citizen_ballots[c] is citizen c's retrospective approval, not a
representative's legislative policy ballot.
A representative's yes/no ballot is ONE of seven policy ballots. It does not
by itself mean enact/reject. Compute passage from all seven policy ballots:
at least four yes votes enact the final policy, otherwise policy 0.
"""


def clarify(messages, game):
    institution.validate(game)
    institution.require(type(messages) is list and len(messages) == 2 and
                        messages[0] == dict(role="system", content=original.SYSTEM) and
                        messages[1]["role"] == "user", "unaltered base messages required")
    result = deepcopy(messages)
    value = json.loads(result[1]["content"])
    institution.require(value["utilities"] == json.loads(json.dumps(game.utilities)),
                        "legend cannot change utility data")
    value["data_layout"] = dict(
        utilities_axes=["term", "district", "citizen", "policy"],
        utilities_shape=[2, 7, 9, len(game.utilities[0][0][0])],
        term_ids=[0, 1], district_ids=list(range(7)), citizen_ids=list(range(9)),
        policy_ids=list(range(len(game.utilities[0][0][0]))),
        menu_assessments_axes=["district", "policy"],
        menu_assessments_term=value["term"],
        citizen_ballots_axis="citizen", representative_ballots_axis="district",
        status_quo_policy=0, policy_passage_yes_threshold=4)
    result[0]["content"] = SYSTEM
    result[1]["content"] = json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=False)
    return result


def messages(game, arm, actor, identity, term, stage, context):
    return clarify(original.messages(game, arm, actor, identity, term, stage, context), game)


def structured(messages_value, game, stage):
    result = original.structured(messages_value, game, stage)
    if stage == "vote":
        result["tools"][0]["function"]["parameters"]["properties"]["vote"]["description"] = (
            "Your own legislative ballot on the final policy, not a prediction of passage.")
    return result


decode = original.decode
