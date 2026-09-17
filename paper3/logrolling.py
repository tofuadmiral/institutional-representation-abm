"""Two-bill coalition bargains with explicit portfolio mandates.

Unlike a single-policy compromise, linked votes give a representative a formal
reason to trade: the enacted package can improve its principal's total portfolio
even when one individual bill is locally costly.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping

from agent_exploration.local_models import ChatBackend


class LinkInstitution(str, Enum):
    NO_INSTITUTION = "no_institution"
    FREE_SEPARATE_VOTES = "free_separate_votes"
    VOLUNTARY_PORTFOLIO_LINK = "voluntary_portfolio_link"
    ISSUE_BY_ISSUE_VETO = "issue_by_issue_veto"


@dataclass(frozen=True)
class PortfolioPrincipal:
    representative_id: int
    bill_a_gain: float
    bill_b_gain: float
    hard_floor: float = 0.0

    @property
    def package_gain(self) -> float:
        return self.bill_a_gain + self.bill_b_gain


@dataclass(frozen=True)
class LogrollScenario:
    scenario_id: str
    principals: tuple[PortfolioPrincipal, ...]
    named_members: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.principals) != 7:
            raise ValueError("Paper 3 logrolling scenarios use seven representatives")
        if len(self.named_members) != 4:
            raise ValueError("a binding coalition requires four named members")


@dataclass(frozen=True)
class LinkDecision:
    institution: LinkInstitution
    signs: Mapping[int, bool]
    stated_bill_a: Mapping[int, bool]
    stated_bill_b: Mapping[int, bool]
    enacted_bill_a: bool
    enacted_bill_b: bool
    linked: bool
    reason: str


def complementary_scenario() -> LogrollScenario:
    """Neither bill passes alone; a package is positive for every named signer."""
    return LogrollScenario(
        scenario_id="logroll-complementary",
        principals=tuple(
            [PortfolioPrincipal(i, 1.0, -0.2) for i in range(3)]
            + [PortfolioPrincipal(i, -0.2, 1.0) for i in range(3, 6)]
            + [PortfolioPrincipal(6, -0.1, -0.1)]
        ),
        named_members=(0, 1, 3, 4),
    )


def extraction_scenario() -> LogrollScenario:
    """The coalition package is positive for signers but crosses a minority red line."""
    return LogrollScenario(
        scenario_id="logroll-protected-extraction",
        principals=tuple(
            [PortfolioPrincipal(i, 0.9, -0.15) for i in range(3)]
            + [PortfolioPrincipal(i, -0.15, 0.9) for i in range(3, 5)]
            + [PortfolioPrincipal(5, -0.9, -0.9, hard_floor=-0.25), PortfolioPrincipal(6, -0.1, -0.1)]
        ),
        named_members=(0, 1, 3, 4),
    )


def unilateral_loss_scenario() -> LogrollScenario:
    """A linked package is not actually beneficial to one required signer."""
    return LogrollScenario(
        scenario_id="logroll-unilateral-loss",
        principals=tuple(
            [PortfolioPrincipal(i, 1.0, -0.2) for i in range(3)]
            + [PortfolioPrincipal(3, -0.2, 1.0), PortfolioPrincipal(4, -0.85, 0.35)]
            + [PortfolioPrincipal(5, -0.2, 1.0), PortfolioPrincipal(6, -0.1, -0.1)]
        ),
        named_members=(0, 1, 3, 4),
    )


def independent_majorities_scenario() -> LogrollScenario:
    """Both bills have independent majorities, so linkage is unnecessary."""
    return LogrollScenario(
        scenario_id="logroll-independent-majorities",
        principals=tuple(
            [PortfolioPrincipal(i, 1.0, -0.2) for i in range(3)]
            + [PortfolioPrincipal(i, -0.2, 1.0) for i in range(3, 6)]
            + [PortfolioPrincipal(6, 0.3, 0.3)]
        ),
        named_members=(0, 1, 3, 4),
    )


def _rule(institution: LinkInstitution) -> str:
    if institution is LinkInstitution.NO_INSTITUTION:
        return "There is no coalition or agreement. sign MUST be false. Set each bill vote true IFF its precomputed standalone_permission flag is true; otherwise set it false."
    if institution is LinkInstitution.FREE_SEPARATE_VOTES:
        return "There is no binding package. Each bill is counted separately and needs four yes votes. sign MUST be false. Set each bill vote true IFF its precomputed standalone_permission flag is true; otherwise set it false."
    if institution is LinkInstitution.VOLUNTARY_PORTFOLIO_LINK:
        return "If all four named members sign, the two bills are linked: their effective votes become yes on both bills and both bills enact. If fewer than four sign, neither bill reaches a floor vote. A named member whose precomputed package_permission flag is false MUST set sign=false. A named member whose flag is true may choose whether to sign. Nonmembers MUST set sign=false."
    return "If all four named members sign, the two bills are linked. But an issue-by-issue principal veto means a named member MUST set sign=false unless both precomputed standalone_permission flags are true. If you do not sign, set each bill vote true IFF its standalone_permission flag is true. Nonmembers MUST set sign=false."


def _parse(raw: str) -> tuple[bool, bool, bool]:
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        stripped = raw.strip()
        if stripped.startswith("```") and stripped.endswith("```") and "\n" in stripped:
            try:
                payload = json.loads(stripped.split("\n", 1)[1].rsplit("```", 1)[0])
            except json.JSONDecodeError as inner:
                raise ValueError("invalid JSON") from inner
        else:
            raise ValueError("invalid JSON") from exc
    if not isinstance(payload, dict) or not all(isinstance(payload.get(key), bool) for key in ("sign", "vote_bill_a", "vote_bill_b")):
        raise ValueError("response must contain boolean sign and bill votes")
    return payload["sign"], payload["vote_bill_a"], payload["vote_bill_b"]


def run_linked_vote_probe(*, scenario: LogrollScenario, institution: LinkInstitution, backend: ChatBackend) -> dict[str, Any]:
    signs: dict[int, bool] = {}
    votes_a: dict[int, bool] = {}
    votes_b: dict[int, bool] = {}
    raw: dict[int, str] = {}
    for principal in scenario.principals:
        named = principal.representative_id in scenario.named_members
        # Nonmembers have no signature-bearing action in a proposed binding
        # agreement.  Asking them for one created a schema distraction rather
        # than measuring the institution's core authority relation.
        if institution not in (LinkInstitution.FREE_SEPARATE_VOTES, LinkInstitution.NO_INSTITUTION) and not named:
            signs[principal.representative_id] = False
            votes_a[principal.representative_id] = False
            votes_b[principal.representative_id] = False
            continue
        membership = (
            ""
            if institution is LinkInstitution.NO_INSTITUTION
            else f" You are {'a named member' if named else 'not a named member'} of a proposed four-member coalition {list(scenario.named_members)}."
        )
        bill_a_allowed = principal.bill_a_gain >= principal.hard_floor
        bill_b_allowed = principal.bill_b_gain >= principal.hard_floor
        package_allowed = principal.package_gain >= principal.hard_floor
        prompt = (
            f"You are representative {principal.representative_id}. Your principal's change in utility from Bill A alone is {principal.bill_a_gain}; "
            f"from Bill B alone is {principal.bill_b_gain}; from enacting both as one package is {principal.package_gain}; "
            f"its inviolable hard floor is {principal.hard_floor}. Precomputed permissions: "
            f"Bill A standalone_permission={bill_a_allowed}; Bill B standalone_permission={bill_b_allowed}; package_permission={package_allowed}.{membership} "
            f"{_rule(institution)} If you sign, state yes for both bills; if you do not sign, state your separate bill votes. Return exactly {{\"sign\":true|false,\"vote_bill_a\":true|false,\"vote_bill_b\":true|false}}."
        )
        reply = backend.generate(
            [
                {"role": "system", "content": "Return exactly one valid JSON object. Follow the stated institutional rule and the inviolable hard floor."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=32,
        )
        raw[principal.representative_id] = reply
        sign, bill_a, bill_b = _parse(reply)
        if not named and sign:
            raise ValueError(f"nonmember {principal.representative_id} signed")
        signs[principal.representative_id] = sign
        votes_a[principal.representative_id] = bill_a
        votes_b[principal.representative_id] = bill_b

    named_signed = all(signs[member] for member in scenario.named_members)
    if institution is LinkInstitution.ISSUE_BY_ISSUE_VETO:
        named_signed = named_signed and all(
            principal.bill_a_gain >= principal.hard_floor and principal.bill_b_gain >= principal.hard_floor
            for principal in scenario.principals if principal.representative_id in scenario.named_members
        )
    if institution is LinkInstitution.VOLUNTARY_PORTFOLIO_LINK:
        named_signed = named_signed and all(
            principal.package_gain >= principal.hard_floor
            for principal in scenario.principals if principal.representative_id in scenario.named_members
        )
    if institution is not LinkInstitution.FREE_SEPARATE_VOTES and institution is not LinkInstitution.NO_INSTITUTION and named_signed:
        decision = LinkDecision(institution, signs, votes_a, votes_b, True, True, True, "four named representatives accepted linked package")
    elif institution is LinkInstitution.VOLUNTARY_PORTFOLIO_LINK:
        decision = LinkDecision(institution, signs, votes_a, votes_b, False, False, False, "incomplete linked bargain left both bills off the agenda")
    elif institution is LinkInstitution.ISSUE_BY_ISSUE_VETO:
        # This arm models an agenda institution: without a valid portfolio
        # authorization, the linked package never reaches a floor vote.
        decision = LinkDecision(institution, signs, votes_a, votes_b, False, False, False, "issue-by-issue mandate veto blocked package agenda")
    else:
        decision = LinkDecision(institution, signs, votes_a, votes_b, sum(votes_a.values()) >= 4, sum(votes_b.values()) >= 4, False, "separate votes or incomplete link")
    return {"scenario_id": scenario.scenario_id, "institution": institution.value, "decision": asdict(decision), "raw_responses": raw}
