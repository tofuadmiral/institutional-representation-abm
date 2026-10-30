"""One prospective, action-only capability diagnostic on fresh B contexts.

The controller's legal action set and parser are unchanged. Only redundant
server-side JSON-Schema constraints are removed from the forced tool; the
local validator remains authoritative. No old gate is rescored.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

from paper3 import coalition_contracts as game
from paper3 import constituent_b_design as design
from paper3 import constituent_b_gptoss_requests as base
from paper3 import constituent_b_institution as institution


FRAME_SEED = 663000
SEED_BASE = 664000
CAP = Decimal("0.05")
MODEL = base.MODEL
PROVIDER_TAG = base.PROVIDER_TAG
PROVIDER_NAME = base.PROVIDER_NAME
PRICE_INPUT_PER_M = base.PRICE_INPUT_PER_M
PRICE_OUTPUT_PER_M = base.PRICE_OUTPUT_PER_M
OUTPUT_CAP = base.OUTPUT_CAP
OUTPUT_BILLABLE_BOUND = base.OUTPUT_BILLABLE_BOUND
INPUT_BOUND = base.INPUT_BOUND
TOOL_NAME = base.TOOL_NAME


def contexts():
    prepared = design.frame(FRAME_SEED)[0]["prepared"]
    proposer = prepared["contract_profile"]["proposer"]
    offer = dict(projects=dict(A="A0", B="B1"), first="A",
                 coalition=[0, 1, 3, 5], message="fixed action-gate offer")
    draft = dict(name="new-action-draft", kind="action", stage="draft",
                 messages=institution.messages(prepared, "member_enforcement",
                                               proposer, "draft", []))
    history = [dict(type="draft", actor=proposer, action=offer)]
    response = dict(name="new-action-response", kind="action", stage="response",
                    messages=institution.messages(prepared, "member_enforcement",
                                                  (proposer + 2) % 7,
                                                  "response", history))
    history.append(dict(type="final", actor=proposer, action=offer))
    history.append(dict(type="consent", approvals=[True] * 7))
    vote = dict(name="new-action-first-vote", kind="action", stage="first_vote",
                messages=institution.messages(prepared, "member_enforcement",
                                              (proposer + 4) % 7,
                                              "first_vote", history))
    return [draft, response, vote]


def simplified_schema(case):
    original = deepcopy(base.schema(case))
    if case["stage"] in ("draft", "response"):
        projects = original["properties"]["projects"]["properties"]
        for project in projects.values():
            project.pop("enum")
        original["properties"]["first"].pop("enum")
        coalition = original["properties"]["coalition"]
        for constraint in ("minItems", "maxItems", "uniqueItems"):
            coalition.pop(constraint)
        for constraint in ("minimum", "maximum"):
            coalition["items"].pop(constraint)
        original["properties"]["message"].pop("maxLength")
    return original


def request(case, seed):
    value = base.request(case, seed)
    value["tools"][0]["function"]["parameters"] = simplified_schema(case)
    return value


def cases():
    result = []
    for index, case in enumerate(contexts()):
        value = request(case, SEED_BASE + index)
        result.append(dict(id=case["name"], context=case, request=value,
                           **base.reservation(value)))
    if len(result) != 3 or sum(Decimal(row["reserved_usd"])
                               for row in result) > CAP:
        raise ValueError("action diagnostic exceeds cap")
    return result
