"""Prospective output-channel normalization, not a change to legal actions.

Accept one bare JSON object or one entire Markdown JSON fence. Reject prose,
multiple blocks and malformed objects. The old frozen gates are never rescored.
"""
from __future__ import annotations

import re

from paper3 import constituent_b_gate as substantive_gate


FENCE = re.compile(r"\A```(?:json)?[ \t]*\r?\n(.*?)\r?\n```\Z",
                   flags=re.IGNORECASE | re.DOTALL)


def json_body(raw):
    if type(raw) is not str:
        raise ValueError("text response required")
    value = raw.strip()
    if not value:
        raise ValueError("empty response")
    if value.startswith("```"):
        match = FENCE.fullmatch(value)
        if match is None:
            raise ValueError("not one entire JSON fence")
        value = match.group(1).strip()
    if not value.startswith("{") or not value.endswith("}"):
        raise ValueError("one JSON object required")
    return value


def score(raw, case):
    try:
        return substantive_gate.score(json_body(raw), case)
    except (ValueError, TypeError) as exc:
        return dict(status="failed", exact=False, error=str(exc))
