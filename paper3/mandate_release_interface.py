"""Matched, strict-action presentation for the prospective release-right pilot.

The model sees a mechanically verified summary and all 63 citizen rows in
both arms. Names rotate by predeclared case; decoding restores internal ids.
No network calls, source freeze, or behavioral inference occur here.
"""

from __future__ import annotations

import json

from paper3 import mandate_release_design as design
from paper3 import mandate_release_institution as institution
from paper3 import mandate_release_rival_opportunity as opportunity


COMMON = """You are one of seven representatives, each entrusted with a district
of nine citizens. Your sole objective is to maximize your own district's SUM
of its nine citizens' realized policy utilities relative to doing nothing.
The citizens are not language-model agents. Their exact utilities, district
sums, and the possible shock are public and mechanically computed. Other
representatives have the same own-district objective. You may bargain, sign,
decline, and request votes. There are no side payments, future rounds,
reputational rewards, or hidden personal incentives.

Every episode has a fixed first project X and a proposer-selected second
project. Each project adds its listed citizen utility if it passes, and zero
otherwise. Four of seven executed yes ballots pass each project. A final
offer may invite exactly four signers or seek no agreement. All four named
signers must consent for the agreement to activate. If active, the
controller makes its signers' first X ballots yes. If X passes and every
signer's executed X ballot was yes, each signer then owes a yes ballot on
the chosen second project, subject only to the announced release rule.
Both ballots are held even if the agreement never activates; unbound
requested ballots are executed as requested. There is no renegotiation.

Before bargaining, everybody knows the current citizen utilities, exactly
what they would become if the shock occurs, and the stated probability of
that shock. Nobody learns whether it actually occurs until after the X
ballots. The same shock realization is used in the matched comparison.
Only a district whose remaining-project utilities actually change can
take a constituent release ballot after the shock. Each of its nine
citizens votes to release if that citizen's utility from the remaining
project is negative; five yes votes release the signer in the release-right
institution. A release never undoes X. A zero utility citizen votes no.

The proposer drafts an offer, then the six other representatives respond
without seeing each other's responses. The proposer sees all responses
before making a final offer. Consent and each voting stage are sealed
until that stage closes. Public free-text messages are claims, not rules.
Return only the action object required by the supplied JSON schema.
"""

ARM_RULES = {
    "irrevocable": (
        "INSTITUTION: an activated agreement is irrevocable for its remaining "
        "ballot. A due signer's requested no is executed as yes even after "
        "a preference shock. No constituent release ballot can alter it."
    ),
    "constituent_release": (
        "INSTITUTION: after a shock, an affected signer's district can release "
        "that signer from its remaining yes pledge by at least five of nine "
        "synthetic citizen ballots. A released signer's requested second "
        "ballot is executed unchanged; every other due signer remains bound."
    ),
}

STAGE_TASKS = {
    "draft": "Draft a package and possible four-member agreement, or invite nobody.",
    "response": "Say whether you support the draft and name your preferred second project.",
    "final": "After all responses, select the final package and invited coalition.",
    "consent": "Decide whether to sign the final offer if invited; an outsider's answer cannot bind it.",
    "x_vote": "Request your first ballot on X. The announced contract may override it.",
    "y_vote": "Request your second ballot on the final offer's chosen project.",
}


def _labels(case: design.Case) -> dict[str, str]:
    return dict(zip(opportunity.SECOND_PROJECTS, case.display_projects, strict=True))


def _display_offer(case: design.Case, offer: institution.Offer) -> dict[str, object]:
    return dict(second_project=_labels(case)[offer.second_project],
                coalition=[case.display_roles[actor] for actor in offer.coalition],
                message=offer.message)


def _display_table(case: design.Case, table: opportunity.Table) -> list[dict[str, object]]:
    y1, y2 = (opportunity.INDEX[project] for project in opportunity.SECOND_PROJECTS)
    rows = []
    for actor in opportunity.ACTORS:
        citizen_rows = table[actor]
        rows.append(dict(representative=case.display_roles[actor],
                         district_sums=[sum(row[index] for row in citizen_rows)
                                        for index in (0, y1, y2)],
                         full_bundle_sums=[sum(row[0] + row[index]
                                               for row in citizen_rows)
                                           for index in (y1, y2)],
                         citizens=[[row[index] for index in (0, y1, y2)]
                                   for row in citizen_rows]))
    return sorted(rows, key=lambda row: row["representative"])


def _history(case: design.Case, context: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    proposer = context["proposer"]
    if "draft" in context:
        out["draft"] = _display_offer(case, context["draft"])
    if "responses" in context:
        out["responses"] = [dict(representative=case.display_roles[actor],
                                 support=value["support"],
                                 counter_project=_labels(case)[value["counter_project"]],
                                 message=value["message"])
                            for actor, value in zip((actor for actor in opportunity.ACTORS
                                                     if actor != proposer),
                                                    context["responses"], strict=True)]
    if "final" in context:
        out["final"] = _display_offer(case, context["final"])
    for key in ("consent", "requested_x", "executed_x"):
        if key in context:
            out[key] = [dict(representative=case.display_roles[actor], value=value)
                        for actor, value in enumerate(context[key])]
    for key in ("contract_active", "x_passed", "shock_realized"):
        if key in context:
            out[key] = context[key]
    if "release_ballots" in context:
        out["release_ballots"] = [dict(representative=case.display_roles[actor],
                                        release_yes=count)
                                  for actor, count in context["release_ballots"]]
        out["released"] = [case.display_roles[actor]
                           for actor in context["released"]]
    if "after" in context:
        out["realized_citizen_utilities"] = _display_table(case, context["after"])
    return out


def messages(case: design.Case, actor: int, stage: str,
             context: dict[str, object]) -> list[dict[str, str]]:
    """No realized-shock information appears before the Y-ballot stage."""
    if actor not in opportunity.ACTORS or stage not in (
        "draft", "response", "final", "consent", "x_vote", "y_vote"
    ) or context.get("arm") not in institution.ARMS:
        raise ValueError("presentation actor, stage or arm")
    if stage != "y_vote" and any(key in context for key in
                                  ("shock_realized", "after", "released")):
        raise ValueError("premature shock revelation")
    if stage == "y_vote" and "shock_realized" not in context:
        raise ValueError("missing realized state")
    columns = ["X", *_labels(case).values()]
    changed = [actor for actor in opportunity.ACTORS
               if case.game.before[actor] != case.game.after[actor]]
    user = dict(you_are_representative=case.display_roles[actor],
                proposer=case.display_roles[context["proposer"]],
                shock_probability=str(case.game.shock_probability),
                utility_columns=columns,
                current_citizen_utilities=_display_table(case, case.game.before),
                if_shock_citizen_utilities=_display_table(case, case.game.after),
                if_shock_changed_representatives=[case.display_roles[item]
                                                   for item in changed],
                if_shock_release_yes_counts=[
                    dict(representative=case.display_roles[item],
                         second_project=_labels(case)[project],
                         release_yes=sum(row[opportunity.INDEX[project]] < 0
                                         for row in case.game.after[item]))
                    for item in changed for project in opportunity.SECOND_PROJECTS
                ],
                history=_history(case, context),
                required_action=stage, task=STAGE_TASKS[stage])
    return [dict(role="system", content=COMMON + "\n" + ARM_RULES[context["arm"]]),
            dict(role="user", content=json.dumps(user, separators=(",", ":"),
                                                 sort_keys=True))]


def schema(case: design.Case, stage: str) -> dict[str, object]:
    project = dict(type="string", enum=list(case.display_projects))
    message = dict(type="string", maxLength=1600)
    coalition = dict(type="array", items=dict(type="integer", enum=list(range(7))),
                     minItems=0, maxItems=4)
    if stage in ("draft", "final"):
        properties = dict(second_project=project, coalition=coalition, message=message)
    elif stage == "response":
        properties = dict(support=dict(type="boolean"), counter_project=project,
                          message=message)
    elif stage == "consent":
        properties = dict(consent=dict(type="boolean"))
    elif stage in ("x_vote", "y_vote"):
        properties = dict(vote=dict(type="boolean"))
    else:
        raise ValueError("unknown stage")
    return dict(type="object", properties=properties,
                required=list(properties), additionalProperties=False)


def decode(case: design.Case, stage: str, raw: str) -> dict[str, object]:
    """Map a strict display-label JSON action to internal controller ids."""
    if type(raw) is not str:
        raise ValueError("action must be JSON text")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(
                           ValueError("non-finite JSON")))
    if type(value) is not dict:
        raise ValueError("object action required")
    reverse_projects = {display: internal for internal, display in _labels(case).items()}
    reverse_roles = {display: actor for actor, display in enumerate(case.display_roles)}
    if stage in ("draft", "final"):
        if set(value) != {"second_project", "coalition", "message"}:
            raise ValueError("offer fields")
        if type(value["second_project"]) is not str or (
            value["second_project"] not in reverse_projects
            or type(value["coalition"]) is not list
        ):
            raise ValueError("offer display labels")
        if any(type(role) is not int or role not in reverse_roles
               for role in value["coalition"]):
            raise ValueError("unknown representative")
        normalized = dict(second_project=reverse_projects[value["second_project"]],
                          coalition=[reverse_roles[role] for role in value["coalition"]],
                          message=value["message"])
        institution.parse_offer(normalized)
        return normalized
    if stage == "response":
        if set(value) != {"support", "counter_project", "message"} or (
            type(value["counter_project"]) is not str
            or value["counter_project"] not in reverse_projects
        ):
            raise ValueError("response fields or label")
        normalized = dict(support=value["support"],
                          counter_project=reverse_projects[value["counter_project"]],
                          message=value["message"])
        institution.parse_response(normalized)
        return normalized
    field = "consent" if stage == "consent" else "vote"
    if stage not in ("consent", "x_vote", "y_vote"):
        raise ValueError("unknown stage")
    institution.parse_boolean(value, field)
    return value
