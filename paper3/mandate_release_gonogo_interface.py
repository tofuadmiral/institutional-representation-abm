"""Prospective expected-utility clarification; no persistent private memory."""
from paper3 import mandate_release_interface_v2 as previous

MAX_MESSAGE_CHARS = 128
MAX_MESSAGE_JSON_BYTES = 12 * MAX_MESSAGE_CHARS + 2
STAGE_TASKS = previous.STAGE_TASKS


def schema(case, stage):
    result = previous.schema(case, stage)
    if "message" in result["properties"]:
        result["properties"]["message"]["maxLength"] = MAX_MESSAGE_CHARS
    return result


def decode(case, stage, raw):
    action = previous.decode(case, stage, raw)
    if "message" in action and len(action["message"]) > MAX_MESSAGE_CHARS:
        raise ValueError("message length")
    return action


def messages(case, actor, stage, context):
    result = previous.messages(case, actor, stage, context)
    result[0]["content"] = result[0]["content"].replace("150 characters", "128 characters")
    result[0]["content"] += (
        "\nBefore the shock is revealed, compare EXPECTED realized district "
        "sums using its stated probability; after revelation, use the realized "
        "state. An initially positive bundle can have a negative expected sum. "
        "Use the reasoning channel to evaluate the choices and keep the analysis "
        "concise. The supplied history is your episode memory; there is no "
        "private memory carried from a previous call or any earlier episode."
    )
    return result
