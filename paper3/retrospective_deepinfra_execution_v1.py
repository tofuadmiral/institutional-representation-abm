"""Prospective resource-isolating OFFLINE executor, never an old-run repair.

Same institution, legal-history bounds, persistence barriers and missingness as
its frozen predecessor. This component cannot transmit or authorize a pilot.
"""
from copy import deepcopy
from dataclasses import asdict

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_deepinfra_requests_v1 as requests
from paper3 import retrospective_deepinfra_route_v1 as route
from paper3 import retrospective_joint_outcome_bounds as outcomes
from paper3.retrospective_deepinfra_failure_v1 import classify


class _LocalFailure(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


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
    and verified resource failures end only their own episode. Every unexecuted slot stays explicit.
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
                    if verdict["status"] in ("content_failed", "resource_failed"):
                        raise _LocalFailure(verdict["status"], verdict["reason"])
                    if verdict["status"] != "recorded_valid":
                        raise _GlobalFailure(verdict["reason"])
                    return deepcopy(verdict["action"])

                record["outcome"] = institution.episode(assignment["game"], assignment["arm"],
                                                       ask, on_term)
                _guard(verify)
                record["status"] = "completed"
            except _LocalFailure as exc:
                record.update(status=exc.status, reason=str(exc))
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
        resource_failed=sum(r["status"] == "resource_failed" for r in records),
        global_safety_stop=stopped, stop_reason=stop_reason,
        logical_attempts=sum(s["evidence"] is not None for r in records for s in r["logicals"]),
        allocation_authorized=False, publication_evidence=False,
        limitation="Offline execution core only. No financial/provenance adapter, "
                   "fresh run locking, protocol freeze, qualification inheritance "
                   "or scientific success screen is supplied by this component.")
    persist(dict(event="terminal", report=deepcopy(report)))
    return report
