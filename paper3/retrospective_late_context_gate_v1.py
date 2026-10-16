"""One fresh sixteen-action, late-term feasibility check; no model/ledger I/O.

All four phases and arms with full seven-district/63-citizen information.
Synthetic legal maximal public messages are fixed, never model-selected.
Success is only legal final-action feasibility, not strategic or scale evidence.
"""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from functools import cache

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as electorates
from paper3 import retrospective_score_ledger_budget as wire
from paper3 import retrospective_contract_route_v2 as route
from paper3 import retrospective_message_budget as public_text
from paper3 import retrospective_serialization_contract as grammar

FRAME_SEED = 2026101601
SEED_BASE = 2026101700
CAP = Decimal(".40")
MAX_WIRE_BYTES = 49152
MAX_PHYSICAL = 17


@cache
def game():
    return replace(electorates.generate(FRAME_SEED).conflict,
                   game_id="resource-late-context-qualification-v1")


@cache
def cases():
    value, rows = game(), []
    for arm_index, arm in enumerate(institution.ARMS):
        contexts = {}

        def ask(actor, identity, term, stage, context, index):
            if term == 1:
                contexts[(stage, actor)] = dict(identity=identity, context=deepcopy(context),
                                                 index=index)
            if stage in ("draft", "final"):
                return dict(policy=1, message="\\" * 128)
            if stage == "response":
                return dict(support=False, counter_policy=2, message="\\" * 128)
            return dict(vote=actor < 4)

        institution.episode(value, arm, ask)
        chair = value.chairs[1]
        for stage in ("draft", "response", "final", "vote"):
            actor = (chair if stage in ("draft", "final") else
                     (chair + arm_index + 1) % 7 if stage == "response" else arm_index)
            saved = contexts[(stage, actor)]
            request = wire.action_request(value, arm, SEED_BASE + len(rows), actor,
                saved["identity"], 1, stage, saved["context"], 0)
            bound = route.reservation(request)
            if len(bound["request_text"].encode()) > MAX_WIRE_BYTES:
                raise ValueError("whole request exceeds approved gate wire bound")
            rows.append(dict(id=f"late-{arm}-{stage}", kind="action", game=value, arm=arm, actor=actor,
                identity=saved["identity"], term=1, stage=stage,
                context=deepcopy(saved["context"]), request=request, **bound))
    if len(rows) != 16 or len({r["id"] for r in rows}) != 16:
        raise ValueError("sixteen independent fixed tasks")
    return tuple(rows)


def bound():
    values = [Decimal(r["reserved_usd"]) for r in cases()]
    total = sum(values) + max(values)  # One identical-wire reissue TOTAL.
    if total > CAP:
        raise ValueError("gate cap exceeded before any calls")
    return dict(logical_calls=16, maximum_physical_calls=MAX_PHYSICAL,
        maximum_reissues=1, cooldown_seconds=300, workers=1,
        stage_cap_usd=str(CAP), full_reservation_usd=str(total),
        largest_wire_bytes=max(len(r["request_text"].encode()) for r in cases()),
        model_calls_authorized_by_module=False, inherited_passes=0,
        all_sixteen_must_pass=True, publication_evidence=False)


def requests():
    return tuple(dict(id=row["id"], request=deepcopy(row["request"]),
                      context=dict(case_id=row["id"])) for row in cases())


def score(case, trace):
    result = dict(exact=False, valid_action=False, stream_integrity=False, action=None)
    try:
        decision = grammar.decision(trace)
        result["stream_integrity"] = True
        mapping = public_text.map_action(case["game"], case["stage"], decision["arguments"])
        if case["stage"] != "vote":
            mapping["executed_action"]["message"].encode("utf-8")
        result.update(exact=True, valid_action=True, action=mapping["executed_action"],
                      execution=mapping, channel=decision["channel"])
    except (KeyError, ValueError, TypeError, UnicodeError):
        pass
    return result
