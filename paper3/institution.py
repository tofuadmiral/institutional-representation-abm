"""Auditable coalition, mandate, and continuation rules for Paper 3."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from math import dist
from typing import Iterable, Mapping, Sequence


class AuthorityRule(str, Enum):
    """How a proposed coalition agreement enters the final decision."""

    FREE_RATIFICATION = "free_ratification"
    COALITION_DISCIPLINE = "coalition_discipline"
    MANDATE_VETO = "mandate_veto"


@dataclass(frozen=True)
class Policy:
    policy_id: str
    position: tuple[float, ...]


@dataclass(frozen=True)
class Mandate:
    principal_id: int
    ideal_point: tuple[float, ...]
    hard_loss_limit: float
    weight: float = 1.0
    group: str = "default"
    trade_loss_budget: float | None = None

    def loss(self, policy: Policy) -> float:
        return dist(self.ideal_point, policy.position)

    def permits(self, policy: Policy) -> bool:
        return self.loss(policy) <= self.hard_loss_limit

    def trade_permits(self, policy: Policy, policies: Sequence[Policy]) -> bool:
        """Whether a permissible policy is inside a principal's trade authority."""
        if not self.permits(policy):
            return False
        if self.trade_loss_budget is None:
            return True
        best = min(self.loss(candidate) for candidate in policies if self.permits(candidate))
        return self.loss(policy) <= best + self.trade_loss_budget


@dataclass(frozen=True)
class CoalitionContract:
    """A formateur's explicit proposed coalition and policy."""

    formateur_id: int
    members: tuple[int, ...]
    policy_id: str

    def __post_init__(self) -> None:
        if self.formateur_id not in self.members:
            raise ValueError("the formateur must be a named coalition member")
        if len(self.members) != len(set(self.members)):
            raise ValueError("coalition members must be unique")


@dataclass(frozen=True)
class DecisionRecord:
    authority: AuthorityRule
    contract: CoalitionContract
    final_policy_id: str
    requested_votes: Mapping[int, str]
    effective_votes: Mapping[int, str]
    accepted: bool
    reason: str
    overridden_members: tuple[int, ...]


@dataclass(frozen=True)
class TermLedger:
    """A compact, fixed-schema record supplied to a later term.

    It records previous institutional facts; it does not assume an agent learned or
    acquired an intrinsic taste for re-election.
    """

    term: int
    prior_policy_id: str | None
    prior_contract_members: tuple[int, ...]
    principal_reauthorized: Mapping[int, bool]

    def context_for(self, representative_id: int) -> dict[str, object]:
        """Equal-schema context for a model prompt, including a neutral first term."""
        return {
            "term": self.term,
            "prior_policy_id": self.prior_policy_id or "NONE",
            "prior_contract_members": list(self.prior_contract_members),
            "principal_reauthorized": bool(
                self.principal_reauthorized.get(representative_id, True)
            ),
        }


def resolve_contract(
    *,
    mandates: Sequence[Mandate],
    policies: Sequence[Policy],
    status_quo_id: str,
    contract: CoalitionContract,
    requested_votes: Mapping[int, str],
    authority: AuthorityRule,
    majority: int | None = None,
) -> DecisionRecord:
    """Resolve one proposal with transparent, frozen authority semantics.

    Free ratification requires an explicit majority for the proposed policy.
    Discipline makes the contract policy the effective vote of named members.
    Mandate veto adds a mechanically checkable constraint: every named member's
    principal must permit the policy. It is a guardrail benchmark, *not* evidence
    that an LLM itself respects a mandate.
    """
    mandate_by_id = {mandate.principal_id: mandate for mandate in mandates}
    policy_by_id = {policy.policy_id: policy for policy in policies}
    representative_ids = set(mandate_by_id)
    if not representative_ids or set(requested_votes) != representative_ids:
        raise ValueError("one requested vote is required for every representative")
    if status_quo_id not in policy_by_id or contract.policy_id not in policy_by_id:
        raise ValueError("contract and status quo must name available policies")
    if not set(contract.members).issubset(representative_ids):
        raise ValueError("contract names an unavailable representative")
    majority = majority or len(representative_ids) // 2 + 1

    effective = dict(requested_votes)
    overridden: tuple[int, ...] = ()
    if authority is AuthorityRule.COALITION_DISCIPLINE:
        overridden = tuple(
            member
            for member in contract.members
            if effective[member] != contract.policy_id
        )
        for member in contract.members:
            effective[member] = contract.policy_id

    mandate_permitted = all(
        mandate_by_id[member].permits(policy_by_id[contract.policy_id])
        for member in contract.members
    )
    support = sum(vote == contract.policy_id for vote in effective.values())
    accepted = support >= majority
    reason = "majority ratification"
    if authority is AuthorityRule.MANDATE_VETO and not mandate_permitted:
        accepted = False
        reason = "mandate veto"
    elif not accepted:
        reason = "insufficient effective support"

    return DecisionRecord(
        authority=authority,
        contract=contract,
        final_policy_id=contract.policy_id if accepted else status_quo_id,
        requested_votes=dict(requested_votes),
        effective_votes=effective,
        accepted=accepted,
        reason=reason,
        overridden_members=overridden,
    )


def reauthorization_ledger(
    *,
    term: int,
    record: DecisionRecord,
    mandates: Sequence[Mandate],
    policies: Sequence[Policy],
) -> TermLedger:
    """Apply a predeclared procedural renewal rule after a completed term.

    Renewal means eligibility to retain the representative role in a later task.
    It is intentionally not called an election: there is no model of voter choice
    or competing candidates in this first extension.
    """
    policy_by_id = {policy.policy_id: policy for policy in policies}
    chosen = policy_by_id[record.final_policy_id]
    return TermLedger(
        term=term,
        prior_policy_id=record.final_policy_id,
        prior_contract_members=record.contract.members,
        principal_reauthorized={
            mandate.principal_id: mandate.permits(chosen) for mandate in mandates
        },
    )


def contract_space(
    representative_ids: Iterable[int], policies: Iterable[Policy], majority: int) -> list[CoalitionContract]:
    """Enumerate possible majority contracts for deterministic design checks."""
    ids = tuple(sorted(representative_ids))
    return [
        CoalitionContract(formateur_id=members[0], members=members, policy_id=policy.policy_id)
        for members in combinations(ids, majority)
        for policy in policies
    ]


def outcome_metrics(
    *, mandates: Sequence[Mandate], policies: Sequence[Policy], record: DecisionRecord
) -> dict[str, float | int]:
    policy = {item.policy_id: item for item in policies}[record.final_policy_id]
    losses = [mandate.loss(policy) for mandate in mandates]
    weighted = sum(m.weight * loss for m, loss in zip(mandates, losses)) / sum(
        mandate.weight for mandate in mandates
    )
    return {
        "mean_loss": weighted,
        "worst_loss": max(losses),
        "hard_mandate_violations": sum(not mandate.permits(policy) for mandate in mandates),
        "overridden_members": len(record.overridden_members),
    }
