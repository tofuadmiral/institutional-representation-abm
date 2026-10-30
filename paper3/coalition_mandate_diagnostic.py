"""Unfrozen, offline-only factual diagnostic design; no inference or credentials.

This tests retrieval under a new question, not strategic competence in the
completed institution. Identical payoff rows cannot identify within-group mixups.
"""
from copy import deepcopy
import json

from paper3 import coalition_contracts as game

ENCODINGS = ("row_array", "principal_id_map")
KEYS = {"own_utilities", "package_utility", "member_active",
        "universal_active", "bound_if_active"}
QUESTION = """This is a factual check, not a vote or consent decision.
Use the supplied hypothetical offer, approvals and institution definitions.
Return exactly one JSON object, without commentary, with these keys:
own_utilities: an object containing YOUR principal's integer A0,A1,B0,B1 utilities;
package_utility: YOUR principal's integer total if both offered projects pass;
member_active: a boolean, whether the member_enforcement agreement activates;
universal_active: a boolean, whether the universal_clearance agreement activates;
bound_if_active: a boolean, whether YOUR representative is among those bound
if this offered binding agreement activates. Do not recommend an action."""


def context(profile_index, actor, encoding):
    game.require(type(profile_index) is int and profile_index in (0, 1), "conflict profile")
    game.require(type(actor) is int and actor in game.ACTORS, "principal id")
    game.require(encoding in ENCODINGS, "table encoding")
    profile = game.fixtures()[profile_index]
    rows = deepcopy(profile["utilities"])
    table = rows if encoding == "row_array" else {str(i): row for i, row in enumerate(rows)}
    offer = dict(projects=dict(A="A0", B="B0"), first="A",
                 coalition=[0, 1, 3, 4], message="")
    approvals = [True] * 7
    if actor % 3 == 1:
        approvals[6] = False  # Outsider refusal separates the two jurisdictions.
    elif actor % 3 == 2:
        approvals[0] = False  # Member refusal prevents activation under either.
    record = dict(representative=actor, principal=actor, proposer=profile["proposer"],
                  utilities_for_all_principals=table,
                  project_menu={key: list(value) for key, value in game.PROJECTS.items()},
                  hypothetical_final_offer=offer, hypothetical_approvals=approvals,
                  institution_definitions={arm: game.ARM_RULES[arm] for arm in
                                           ("member_enforcement", "universal_clearance")})
    events = [dict(type="final", action=offer), dict(type="consent", approvals=approvals)]
    own = profile["utilities"][actor]
    expected = dict(own_utilities=deepcopy(own), package_utility=own["A0"] + own["B0"],
                    member_active=game.contract_state(events, "member_enforcement")["active"],
                    universal_active=game.contract_state(events, "universal_clearance")["active"],
                    bound_if_active=actor in offer["coalition"])
    messages = [dict(role="system", content=game.COMMON_RULES),
                dict(role="user", content=json.dumps(record, separators=(",", ":")) + "\n" + QUESTION)]
    return dict(profile_index=profile_index, actor=actor, encoding=encoding,
                record=record, messages=messages, expected=expected)


def cases(seed_bases):
    """Two caller-supplied fresh bases, paired across encodings; not yet reserved.

    Audit historical schedules and freeze order before these may be submitted.
    No file, model call, budget allocation, source freeze or launch occurs here.
    """
    game.require(len(seed_bases) == 2 and all(type(s) is int and s >= 0 for s in seed_bases),
                 "two nonnegative integer seed bases")
    game.require(not set(range(seed_bases[0], seed_bases[0] + 14)) &
                 set(range(seed_bases[1], seed_bases[1] + 14)), "repeat seeds overlap")
    result = []
    for repeat, base in enumerate(seed_bases):
        for profile in (0, 1):
            for actor in game.ACTORS:
                for encoding in ENCODINGS:
                    result.append(dict(id=f"profile-{profile}-actor-{actor}-{encoding}-repeat-{repeat}",
                                       repeat=repeat, seed=base + profile * 7 + actor,
                                       **context(profile, actor, encoding)))
    return result


def score_content(raw, expected):
    """Content only: transport/reasoning/billing certification remains separate."""
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            game.require(key not in obj, "duplicate JSON key")
            obj[key] = value
        return obj

    try:
        value = json.loads(raw, object_pairs_hook=unique)
        game.require(type(value) is dict and set(value) == KEYS, "answer fields")
        own = value["own_utilities"]
        game.require(type(own) is dict and set(own) == {"A0", "A1", "B0", "B1"}, "utility fields")
        game.require(all(type(v) is int for v in own.values()) and
                     type(value["package_utility"]) is int, "integer utilities")
        game.require(all(type(value[k]) is bool for k in
                         ("member_active", "universal_active", "bound_if_active")), "boolean rules")
    except (ValueError, TypeError) as exc:
        return dict(valid=False, correct=False, fields=None, failure=str(exc))
    fields = {k: value[k] == expected[k] for k in sorted(KEYS)}
    return dict(valid=True, correct=all(fields.values()), fields=fields, failure=None)
