"""Prospective OFFLINE core: retain failed episodes, never infer decisions.

Explicit fabricated/replay response and persistence functions are required.
This module neither transmits nor allocates, retries, prepares or freezes a run.
A production runner still needs a provenance/physical-attempt ledger adapter,
authority admission, source/qualification guards, durable locking and an audit.
Never attach this to a previously started root or rescore historical failures.
"""
from hashlib import sha256
import json

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_billing_calls as service
from paper3 import retrospective_deepinfra_route_v1 as route
from paper3 import retrospective_message_budget as public_text
from paper3 import retrospective_deepinfra_requests_v1 as requests
from paper3 import retrospective_serialization_contract as grammar

CONFIG = dict(models=[route.MODEL, route.MODEL_ALIAS], provider=route.PROVIDER,
              output_bound=route.OUTPUT_BOUND)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def classify(row, request, game, stage):
    """Recompute instrument safety BEFORE deciding if bad content is local.

    Clean typed/whole-object content failure is episode-local only after exact
    request/bounds/assessment, billing, route, usage, native and channel checks.
    Wrong identity, incomplete/ambiguous stream, unknown billing or provenance
    failure is globally unsafe. A later receipt cannot hide an earlier unknown
    error. Full404-only reservations remain in recomputed evidence.
    """
    result = dict(status="unsafe_failed", action=None, execution=None,
                  instrument_safe=False, assessment=None, channel=None, reason=None)
    try:
        payload = json.loads(request["messages"][1]["content"])
        institution.require(payload["game_id"] == game.game_id and
            type(payload["office_value"]) is int and payload["office_value"] == game.office_value and
            _canonical(payload["chairs"]) == _canonical(list(game.chairs)),
            "exact game office value and chairs")
        actor, term = payload["acting_district"], payload["term"]
        institution.require(type(actor) is int and actor in institution.ACTORS and
            type(term) is int and term in (0, 1) and
            payload["acting_identity"] == payload["occupants"][actor],
            "actual acting district identity and term")
        binding, majority = institution.rules(payload["arm"])
        institution.require(payload["assessment_binding"] is binding and
            payload["selected_assessment"] == ("majority" if majority else "sum") and
            (actor == game.chairs[term] if stage in ("draft", "final") else
             actor != game.chairs[term] if stage == "response" else stage == "vote"),
            "assessment criterion and phase jurisdiction")
        expected = route.request(requests.structured(request["messages"], game, stage),
                                 request["seed"])
        institution.require(_canonical(request) == _canonical(expected),
                            "qualified prompt schema and native envelope")
        bound = route.reservation(request)
        institution.require(type(row) is dict and row.get("status") == "recorded"
            and not row.get("instrument_error"), "completed evidence required")
        institution.require(_canonical(row["request"]) == _canonical(request) and
            row["request_text"] == bound["request_text"] and
            row["request_sha256"] == sha256(bound["request_text"].encode()).hexdigest() and
            type(row["input_token_bound"]) is int and
            row["input_token_bound"] == bound["input_token_bound"] and
            row["reserved_usd"] == bound["reserved_usd"], "exact request and reservation")
        assessment = service.assess(row, CONFIG)
        result["assessment"] = assessment
        institution.require(_canonical(row["assessment"]) == _canonical(assessment),
                            "saved assessment changed")
        native = service.native_evidence(assessment["stream"])
        result["native_evidence"] = native
        institution.require(assessment["passed"] is True and
            assessment["stream"]["finish_reasons"] in (["tool_calls"], ["stop"]) and
            native["present"] is True and native["reported_count_consistent"] is True and
            request["reasoning"] == dict(enabled=True, exclude=False),
            "transport billing native usage or completion")
        # Multiple/dual/partial action channels are unsafe even if they agree.
        channel = grammar.stream_envelope(row["stream"])
        result["channel"] = channel
    except Exception as exc:
        result["reason"] = "instrument:" + type(exc).__name__
        return result
    result["instrument_safe"] = True
    try:
        decision = grammar.decision(row["stream"])
        mapping = public_text.map_action(game, stage, decision["arguments"])
        # Only executed public history is carried into a new UTF-8 request.
        # This is a prospective transport-compatibility check, not a repair.
        if stage != "vote":
            mapping["executed_action"]["message"].encode("utf-8")
        result.update(status="recorded_valid", action=mapping["executed_action"],
                      execution=mapping, reason=None)
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        result.update(status="content_failed", reason="content:" + type(exc).__name__)
    return result
