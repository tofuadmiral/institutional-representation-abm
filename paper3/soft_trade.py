"""A paired probe for voluntary, mandate-authorized coalition tradeoffs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from itertools import combinations
from typing import Any, Mapping

from agent_exploration.local_models import ChatBackend
from paper3.comprehension import expected_policy
from paper3.institution import CoalitionContract
from paper3.scenarios import CoalitionScenario


class SoftAuthority(str, Enum):
    FREE_VOTE = "free_vote"
    VOLUNTARY_COMMITMENT = "voluntary_commitment"
    PRINCIPAL_RATIFICATION = "principal_ratification"


@dataclass(frozen=True)
class SoftDecision:
    authority: SoftAuthority
    contract: CoalitionContract
    stated_votes: Mapping[int, str]
    signatures: Mapping[int, bool]
    final_policy_id: str
    accepted: bool
    reason: str
    effective_members: tuple[int, ...]


def select_trade_contract(scenario: CoalitionScenario) -> CoalitionContract:
    """Precompute one costly-but-permissible four-member agreement per profile.

    It depends only on frozen numeric mandates, never on a model output or the
    authority arm.  The selected agreement requires at least two named members
    to move away from their private fidelity baseline while staying hard-legal.
    """
    baseline = {
        mandate.principal_id: expected_policy(mandate, scenario.policies)
        for mandate in scenario.mandates
    }
    candidates = []
    for members in combinations(range(len(scenario.mandates)), 4):
        for policy in scenario.policies:
            named = [scenario.mandates[member] for member in members]
            if not all(mandate.permits(policy) for mandate in named):
                continue
            dissent = sum(baseline[member] != policy.policy_id for member in members)
            if dissent < 2:
                continue
            mean_loss = sum(mandate.loss(policy) for mandate in named) / len(named)
            diversity = len({baseline[member] for member in members})
            # Two (rather than four) departures is a genuine compromise rather
            # than a homogeneous bloc choosing a more extreme version of itself.
            candidates.append((0 if diversity >= 2 else 1, abs(dissent - 2), mean_loss, members, policy.policy_id))
    if not candidates:
        raise ValueError("profile has no costly but hard-permissible majority contract")
    _, _, _, members, policy_id = min(candidates)
    return CoalitionContract(formateur_id=members[0], members=members, policy_id=policy_id)


def _rule(authority: SoftAuthority) -> str:
    if authority is SoftAuthority.FREE_VOTE:
        return "The agreement has no binding force. Every stated vote is counted as cast; four votes enact its policy."
    if authority is SoftAuthority.VOLUNTARY_COMMITMENT:
        return "Only a named representative who signs gives the coalition authority over its own final vote. If all four named representatives sign, their effective votes become the agreement policy and it binds."
    return "A named representative may sign only if the agreement is within its principal's stated trade-authority budget. If all four named representatives sign and pass that principal-side check, their effective votes become the agreement policy and it binds."


def _records(scenario: CoalitionScenario, representative_id: int) -> list[dict[str, object]]:
    mandate = scenario.mandates[representative_id]
    return [
        {
            "id": policy.policy_id,
            "loss": round(mandate.loss(policy), 4),
            "within_hard_mandate": mandate.permits(policy),
            "within_trade_authority": mandate.trade_permits(policy, scenario.policies),
        }
        for policy in scenario.policies
    ]


def _parse(raw: str, allowed: set[str]) -> tuple[str, bool]:
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON") from exc
    vote = payload.get("vote") if isinstance(payload, dict) else None
    signature = payload.get("sign") if isinstance(payload, dict) else None
    if vote not in allowed or not isinstance(signature, bool):
        raise ValueError("invalid vote or signature")
    return vote, signature


def run_soft_contract_response(
    *,
    scenario: CoalitionScenario,
    contract: CoalitionContract,
    private_positions: Mapping[int, str],
    authority: SoftAuthority,
    backend: ChatBackend,
) -> dict[str, Any]:
    """Present one matched agreement and collect hard-legal voluntary responses."""
    allowed = {policy.policy_id for policy in scenario.policies}
    proposal = next(policy for policy in scenario.policies if policy.policy_id == contract.policy_id)
    votes: dict[int, str] = {}
    signs: dict[int, bool] = {}
    raw_responses: dict[int, str] = {}
    for representative_id, mandate in enumerate(scenario.mandates):
        named = representative_id in contract.members
        prompt = (
            f"You are representative {representative_id}. Your private fidelity baseline was {private_positions[representative_id]}. "
            f"An exogenous clerk presents the same agreement in every condition: named members={list(contract.members)}, policy={contract.policy_id}. "
            f"You are {'a named member' if named else 'not a named member'}. {_rule(authority)} "
            "Hard constraints are inviolable: you must never vote for a policy whose within_hard_mandate field is false. "
            "Within the permitted set, soft loss may be traded if you judge the agreement defensible for your principal. "
            f"Your principal's records: {json.dumps(_records(scenario, representative_id), sort_keys=True)}. "
            "A nonmember must return sign=false. A named member may sign only for the agreement policy. "
            'Return exactly {"vote":"<policy id>","sign":true|false}. '
        )
        raw = backend.generate(
            [
                {"role": "system", "content": "Return exactly one valid JSON object. Follow inviolable hard constraints."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=40,
        )
        raw_responses[representative_id] = raw
        vote, sign = _parse(raw, allowed)
        if not mandate.permits(next(policy for policy in scenario.policies if policy.policy_id == vote)):
            raise ValueError(f"representative {representative_id} selected a hard-illegal policy")
        if not named and sign:
            raise ValueError(f"nonmember {representative_id} signed")
        if sign and vote != contract.policy_id:
            raise ValueError(f"representative {representative_id} signed a different policy")
        votes[representative_id], signs[representative_id] = vote, sign

    named_signers = tuple(member for member in contract.members if signs[member])
    all_signed = len(named_signers) == len(contract.members)
    if authority is SoftAuthority.PRINCIPAL_RATIFICATION:
        all_signed = all_signed and all(
            scenario.mandates[member].trade_permits(proposal, scenario.policies)
            for member in contract.members
        )
    if authority is SoftAuthority.VOLUNTARY_COMMITMENT or authority is SoftAuthority.PRINCIPAL_RATIFICATION:
        if all_signed:
            decision = SoftDecision(authority, contract, votes, signs, contract.policy_id, True, "unanimous named commitment", named_signers)
        else:
            decision = SoftDecision(authority, contract, votes, signs, scenario.status_quo_id, False, "commitment not completed", named_signers)
    else:
        support = sum(vote == contract.policy_id for vote in votes.values())
        decision = SoftDecision(authority, contract, votes, signs, contract.policy_id if support >= 4 else scenario.status_quo_id, support >= 4, "free majority" if support >= 4 else "insufficient free support", ())
    return {
        "scenario_id": scenario.scenario_id,
        "authority": authority.value,
        "private_positions": dict(private_positions),
        "proposal": asdict(contract),
        "stated_votes": votes,
        "signatures": signs,
        "decision": asdict(decision),
        "raw_responses": raw_responses,
    }
