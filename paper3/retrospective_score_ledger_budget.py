"""Offline legal-history byte reservations for a prospective ledger institution.

No network, ledger allocation, run preparation or launch authority. Bounds are
for the pinned native request envelope, not expected bills or token usage.
Never substitute these bounds into a previously frozen protocol.
"""
from copy import deepcopy
from decimal import Decimal
import json

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_contract_route_v2 as route
from paper3 import retrospective_score_ledger as interface

QUALIFIED_TOOL_DESCRIPTION = "Record the requested factual report or institutional action."


def structured(messages, game, stage):
    """Exact tool envelope used by the passed ledger qualification actions.

    The frozen base adapter uses an action-only tool description. Qualification
    uses this common factual/action description. Preserve its exact spelling
    prospectively; do not relax envelope equality or reinterpret old responses.
    """
    fragment = interface.structured(messages, game, stage)
    fragment["tools"][0]["function"]["description"] = QUALIFIED_TOOL_DESCRIPTION
    return fragment


def action_request(game, arm, seed_base, actor, identity, term, stage, context, index):
    institution.require(type(seed_base) is int and seed_base >= 0, "nonnegative base seed")
    institution.require(type(index) is int and 0 <= index < 30, "thirty-action index")
    messages = interface.messages(game, arm, actor, identity, term, stage, context)
    return route.request(structured(messages, game, stage), seed_base + index)


def _long_booleans(value):
    # This deliberately need not be a valid scientific payload. It is never sent.
    if type(value) is bool:
        return False  # JSON false is one byte longer than true at both levels.
    if type(value) is list:
        return [_long_booleans(v) for v in value]
    if type(value) is dict:
        return {k: _long_booleans(v) for k, v in value.items()}
    return value


def padded_reservation(request):
    """Upper-envelope boolean padding, after actual prompt/schema construction."""
    value = deepcopy(request)
    institution.require(len(value["messages"]) == 2 and
        value["messages"][0] == dict(role="system", content=interface.SYSTEM) and
        value["messages"][1]["role"] == "user", "qualified ledger messages")
    payload = json.loads(value["messages"][1]["content"])
    value["messages"][1]["content"] = json.dumps(_long_booleans(payload),
        sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    result = route.reservation(value)
    institution.require(result["input_token_bound"] >=
        route.reservation(request)["input_token_bound"], "monotone envelope padding")
    return result


def legal_history_bounds(game, arm, seed_base):
    """Bound all thirty decisions, including every first-term officeholder state.

    Proof scope: width 2..8 means all free policy IDs have one decimal digit.
    Each public message has <=128 code points; in JSON-inside-JSON, a backslash
    uses four bytes, dominating every legal UTF-8 scalar, quote and allowed
    tab/newline/return. Non-UTF-8-encodable strings cannot form a transport request.
    Support/ballot flags are padded to false. Counts, utility aggregates, scores,
    assessments, null/role structure and tenure are fixed by game/arm/enactment;
    all first enactments, including rejection, are enumerated through the engine.
    Draft/counter/final IDs vary in value but not length. No response or vote is
    newly disclosed to an earlier sealed stage. Second-term enactment is not
    present in any decision's public history.

    This is an upper bound, not a claim that its padded payload is legal or that
    all per-call maxima are simultaneously attained by one bargaining episode.
    """
    institution.validate(game)
    institution.rules(arm)
    maxima = [0] * 30
    width = len(game.utilities[0][0][0])
    histories = [(p, True) for p in range(width)] + [(0, False)]
    for policy, passing in histories:
        def ask(actor, identity, term, stage, context, index):
            request = action_request(game, arm, seed_base, actor, identity, term,
                                     stage, context, index)
            maxima[index] = max(maxima[index],
                padded_reservation(request)["input_token_bound"])
            if stage in ("draft", "final"):
                return dict(policy=policy if term == 0 else width - 1,
                            message="\\" * institution.MAX_MESSAGE)
            if stage == "response":
                return dict(support=False, counter_policy=width - 1,
                            message="\\" * institution.MAX_MESSAGE)
            return dict(vote=actor < 4 if passing else False)
        institution.episode(game, arm, ask)
    costs = tuple((Decimal(bound) * route.PRICE_IN +
                   Decimal(route.OUTPUT_BOUND) * route.PRICE_OUT) / 1000000
                  for bound in maxima)
    institution.require(all(maxima) and
        max(maxima) + route.OUTPUT_BOUND <= route.CONTEXT, "full-history capacity")
    return dict(game_id=game.game_id, arm=arm, seed_base=seed_base,
        input_bounds=tuple(maxima), per_call_reservations_usd=tuple(map(str, costs)),
        logical_calls=30, reservation_usd=str(sum(costs)),
        largest_attempt_usd=str(max(costs)), output_bound=route.OUTPUT_BOUND,
        context_floor=route.CONTEXT, allocation_authorized=False,
        qualification_inherited=False, publication_evidence=False)


def block_bound(assignments, maximum_reissues=0):
    """Price the ENTIRE supplied inventory, without choosing/removing any cases."""
    institution.require(type(assignments) is tuple and bool(assignments),
                        "nonempty fixed assignment inventory")
    institution.require(type(maximum_reissues) is int and maximum_reissues >= 0,
                        "explicit nonnegative retry ceiling")
    ids = [row["id"] for row in assignments]
    institution.require(all(type(i) is str and i for i in ids) and
                        len(ids) == len(set(ids)), "unique assignment identities")
    rows = tuple(dict(id=row["id"], **legal_history_bounds(
        row["game"], row["arm"], row["seed_base"])) for row in assignments)
    primary = sum(Decimal(row["reservation_usd"]) for row in rows)
    retry = maximum_reissues * max(Decimal(row["largest_attempt_usd"]) for row in rows)
    return dict(assignments=rows, logical_calls=30 * len(rows),
        maximum_physical_calls=30 * len(rows) + maximum_reissues,
        primary_reservation_usd=str(primary), retry_reservation_usd=str(retry),
        full_reservation_usd=str(primary + retry),
        allocation_authorized=False, qualification_inherited=False,
        cumulative_authority_extended=False, publication_evidence=False,
        limitation="Offline byte envelope at pinned price ceilings, not expected "
                   "bills. Fresh inventory/qualification replay, authority adapter, "
                   "failure controller and protocol freeze required before calls.")
