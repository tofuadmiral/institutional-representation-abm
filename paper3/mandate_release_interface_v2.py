"""Prospective coalition-token interface for the release-right institution.

The v1 action schema admitted three-member arrays even though the controller
requires either no agreement or four named signers. This separate interface
keeps the institution and information schedule unchanged, but makes the
coalition choice one of 35 valid four-person tokens or ``none``. It does not
reinterpret or repair any v1 record.
"""

from __future__ import annotations

from itertools import combinations
import json

from paper3 import mandate_release_design as design
from paper3 import mandate_release_interface as v1


NONE = "none"
COALITIONS = tuple("-".join(map(str, members))
                   for members in combinations(range(7), 4))
TOKENS = (NONE, *COALITIONS)
MAX_MESSAGE_CHARS = 150
MAX_MESSAGE_JSON_BYTES = 12 * MAX_MESSAGE_CHARS + 2
STAGE_TASKS = v1.STAGE_TASKS


def messages(case: design.Case, actor: int, stage: str,
             context: dict[str, object]) -> list[dict[str, str]]:
    result = v1.messages(case, actor, stage, context)
    if stage in ("draft", "response", "final"):
        result[0]["content"] += (
            "\nKeep the public message at most 150 characters. The structured "
            "choice, not the message, determines the action."
        )
    if stage in ("draft", "final"):
        result[0]["content"] += (
            "\nFor the coalition field, select 'none' or one of the exact "
            "four-representative tokens in the schema. The token names ALL "
            "four signers, including yourself if you intend to sign. "
            "For example, 0-2-3-5 names exactly those four representatives. "
            "Only the token, not your message, names the binding coalition."
        )
    return result


def schema(case: design.Case, stage: str) -> dict[str, object]:
    result = v1.schema(case, stage)
    if stage in ("draft", "final"):
        result["properties"]["coalition"] = dict(type="string", enum=list(TOKENS))
    if stage in ("draft", "response", "final"):
        result["properties"]["message"]["maxLength"] = MAX_MESSAGE_CHARS
    return result


def decode(case: design.Case, stage: str, raw: str) -> dict[str, object]:
    if stage not in ("draft", "final"):
        action = v1.decode(case, stage, raw)
        if "message" in action and len(action["message"]) > MAX_MESSAGE_CHARS:
            raise ValueError("message length")
        return action
    if type(raw) is not str:
        raise ValueError("action must be JSON text")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(
                           ValueError("non-finite JSON")))
    if type(value) is not dict or set(value) != {
        "second_project", "coalition", "message"
    } or type(value["coalition"]) is not str or value["coalition"] not in TOKENS:
        raise ValueError("coalition token")
    if type(value["message"]) is not str or len(value["message"]) > MAX_MESSAGE_CHARS:
        raise ValueError("message length")
    token = value["coalition"]
    value["coalition"] = [] if token == NONE else [int(item) for item in token.split("-")]
    return v1.decode(case, stage, json.dumps(value, ensure_ascii=True))
