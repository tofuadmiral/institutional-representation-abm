"""Prospective OFFLINE core: retain failed episodes, never infer decisions.

Explicit fabricated/replay response and persistence functions are required.
This module neither transmits nor allocates, retries, prepares or freezes a run.
A production runner still needs a provenance/physical-attempt ledger adapter,
authority admission, source/qualification guards, durable locking and an audit.
Never attach this to a previously started root or rescore historical failures.
"""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_billing_calls as service
from paper3 import retrospective_contract_route_v2 as route
from paper3 import retrospective_joint_outcome_bounds as outcomes
from paper3 import retrospective_message_budget as public_text
from paper3 import retrospective_score_ledger_budget as requests
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


class _LocalFailure(Exception):
    pass


class _GlobalFailure(Exception):
    pass


def _guard(verify):
    institution.require(verify() is not False, "verification rejected")


def execute(assignments, *, respond, verify, persist):
    """One serial pass through the ENTIRE inventory; no restart/replacement.

    respond(request, logical_id) must return a complete scientific evidence row
    with that exact logical id. It does NOT license a live transport. Persisted
    call evidence precedes any action execution. Production spending/attempts and
    irreversible persistence must be enforced by the separately frozen runner.
    Exceptions with unknown safety stop this block; safe completed content
    failures end only their own episode. Every unexecuted slot stays explicit.
    """
    institution.require(type(assignments) is tuple and bool(assignments), "fixed inventory")
    institution.require(all(callable(f) for f in (respond, verify, persist)),
                        "explicit response verification and persistence required")
    ids = [a["id"] for a in assignments]
    institution.require(all(type(i) is str and i for i in ids) and
        len(ids) == len(set(ids)), "unique assignment ids")
    for a in assignments:
        institution.validate(a["game"])
        institution.rules(a["arm"])
        institution.require(type(a["seed_base"]) is int and a["seed_base"] >= 0,
                            "assigned base seed")
    records = [dict(id=a["id"], arm=a["arm"], seed_base=a["seed_base"],
        game=asdict(a["game"]), status="not_started", terms=[None, None], outcome=None,
        logicals=[dict(id=a["id"] + f"-{i:02d}", index=i, status="not_started",
                      request=None, evidence=None, classification=None) for i in range(30)])
        for a in assignments]
    persist(dict(event="inventory", assignments=deepcopy(records)))
    stopped = False
    stop_reason = None
    for assignment, record in zip(assignments, records, strict=True):
        if not stopped:
            record["status"] = "in_progress"
            try:
                _guard(verify)
                envelope = requests.legal_history_bounds(assignment["game"],
                    assignment["arm"], assignment["seed_base"])

                def on_term(term):
                    record["terms"][term.index] = term
                    persist(dict(event="term", id=record["id"], term=deepcopy(term)))

                def ask(actor, identity, term, stage, context, index):
                    slot = record["logicals"][index]
                    try:
                        _guard(verify)
                        request = requests.action_request(assignment["game"], assignment["arm"],
                            assignment["seed_base"], actor, identity, term, stage, context, index)
                        institution.require(route.reservation(request)["input_token_bound"] <=
                            envelope["input_bounds"][index], "frozen history capacity")
                        slot.update(status="prepared", request=deepcopy(request), actor=actor,
                                    identity=identity, term=term, stage=stage)
                        persist(dict(event="prepared", slot=deepcopy(slot)))
                        _guard(verify)  # Last integrity barrier before response.
                        row = respond(deepcopy(request), slot["id"])
                        slot.update(status="evidence_received", evidence=deepcopy(row))
                        persist(dict(event="evidence", slot=deepcopy(slot)))
                        _guard(verify)  # Preserve evidence even on source divergence.
                        institution.require(type(row) is dict and row.get("id") == slot["id"],
                                            "logical response identity")
                        verdict = classify(row, request, assignment["game"], stage)
                        slot.update(status=verdict["status"], classification=verdict)
                        persist(dict(event="decision", slot=deepcopy(slot)))
                    except Exception as exc:
                        slot.update(status="unsafe_failed", error_type=type(exc).__name__)
                        raise _GlobalFailure("response_provenance_or_controller") from exc
                    if verdict["status"] == "content_failed":
                        raise _LocalFailure(verdict["reason"])
                    if verdict["status"] != "recorded_valid":
                        raise _GlobalFailure(verdict["reason"])
                    return deepcopy(verdict["action"])

                record["outcome"] = institution.episode(assignment["game"], assignment["arm"],
                                                       ask, on_term)
                _guard(verify)
                record["status"] = "completed"
            except _LocalFailure as exc:
                record.update(status="content_failed", reason=str(exc))
            except Exception as exc:
                # Unknown persistence, controller or verification failures are
                # never reclassified as harmless content failures.
                stopped = True
                stop_reason = type(exc).__name__
                record.update(status="unsafe_failed", error_type=stop_reason)
        observed = tuple(record["terms"])
        record["first_term"] = outcomes.first_term_bounds(
            assignment["game"], assignment["arm"], observed)
        record["two_term"] = outcomes.bounds(assignment["game"], assignment["arm"], observed)
        persist(dict(event="episode", record=deepcopy(record)))
    report = dict(assignments=tuple(records), assigned=len(records),
        completed=sum(r["status"] == "completed" for r in records),
        content_failed=sum(r["status"] == "content_failed" for r in records),
        global_safety_stop=stopped, stop_reason=stop_reason,
        logical_attempts=sum(s["evidence"] is not None for r in records for s in r["logicals"]),
        allocation_authorized=False, publication_evidence=False,
        limitation="Offline execution core only. No financial/provenance adapter, "
                   "fresh run locking, protocol freeze, qualification inheritance "
                   "or scientific success screen is supplied by this component.")
    persist(dict(event="terminal", report=deepcopy(report)))
    return report
