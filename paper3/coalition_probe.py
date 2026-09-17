"""Small, cached local-model probe for Paper 3 coalition institutions.

The runner keeps the task, principals, policies, initial private positions,
formateur identity, message order, and token budget fixed across authority arms.
Only the formal authority rule changes after private positions are collected.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent_exploration.local_models import CachedChatBackend, ChatBackend
from paper3.institution import AuthorityRule, CoalitionContract, DecisionRecord, resolve_contract
from paper3.scenarios import CoalitionScenario


def _policy_records(scenario: CoalitionScenario, representative_id: int) -> list[dict[str, object]]:
    mandate = scenario.mandates[representative_id]
    return [
        {
            "id": policy.policy_id,
            "position": list(policy.position),
            "loss_to_your_principal": round(mandate.loss(policy), 3),
            "within_hard_mandate": mandate.permits(policy),
        }
        for policy in scenario.policies
    ]


def _rule_text(authority: AuthorityRule) -> str:
    if authority is AuthorityRule.FREE_RATIFICATION:
        return (
            "The agreement is non-binding. Every representative's stated final vote is "
            "counted exactly as cast; a policy needs four votes to replace the status quo."
        )
    if authority is AuthorityRule.COALITION_DISCIPLINE:
        return (
            "A four-member agreement is binding on its named members: their effective "
            "votes become the agreement policy even if they state something else. "
            "Nonmembers' stated votes are counted as cast. A policy needs four effective votes."
        )
    return (
        "The agreement is non-binding unless a mandate clerk verifies that its policy is "
        "within the hard mandate of every named coalition member. If that mechanical gate "
        "fails, the status quo remains. If it passes, a policy still needs four stated votes."
    )


def _generate(backend: ChatBackend, prompt: str, max_tokens: int) -> str:
    return backend.generate(
        [
            {
                "role": "system",
                "content": (
                    "You are one representative in a synthetic institutional experiment. "
                    "Follow the stated procedure and return only one valid JSON object. "
                    "Do not invent facts, hidden preferences, or personal career incentives."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=max_tokens,
    )


def _parse_json(raw: str) -> dict[str, Any]:
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        if raw.strip().startswith("```") and raw.strip().endswith("```"):
            body = raw.strip().split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(body)
        else:
            raise ValueError("invalid JSON")
    if not isinstance(result, dict):
        raise ValueError("response must be a JSON object")
    return result


def collect_private_positions(
    *, scenario: CoalitionScenario, backend: ChatBackend
) -> tuple[dict[int, str], dict[int, str]]:
    """Collect initial positions before any authority arm is revealed."""
    positions: dict[int, str] = {}
    raw: dict[int, str] = {}
    allowed = {policy.policy_id for policy in scenario.policies}
    for representative_id, mandate in enumerate(scenario.mandates):
        prompt = (
            f"You represent principal {representative_id}. Their ideal policy is "
            f"{list(mandate.ideal_point)} and their hard mandate is the boolean shown "
            "for each policy. This is a private position before coalition rules are revealed. "
            f"Policies: {json.dumps(_policy_records(scenario, representative_id), sort_keys=True)}. "
            'Choose your private position. Respond exactly as {"choice":"<policy id>"}.'
        )
        response = _generate(backend, prompt, 32)
        raw[representative_id] = response
        choice = _parse_json(response).get("choice")
        if choice not in allowed:
            raise ValueError(f"representative {representative_id} chose invalid private policy {choice!r}")
        positions[representative_id] = choice
    return positions, raw


def run_authority_arm(
    *,
    scenario: CoalitionScenario,
    private_positions: Mapping[int, str],
    formateur_id: int,
    authority: AuthorityRule,
    backend: ChatBackend,
) -> dict[str, Any]:
    """Run one public proposal and a single explicit response round."""
    allowed = {policy.policy_id for policy in scenario.policies}
    public_positions = [
        {"representative": representative_id, "private_position": private_positions[representative_id]}
        for representative_id in sorted(private_positions)
    ]
    proposal_prompt = (
        f"You are representative {formateur_id}, selected by a fixed rotation to form an agreement. "
        f"Public initial positions: {json.dumps(public_positions)}. {_rule_text(authority)} "
        f"Your principal's policy records: {json.dumps(_policy_records(scenario, formateur_id), sort_keys=True)}. "
        "Propose exactly four coalition members including yourself and one available policy. "
        'Respond exactly as {"members":[0,1,2,3],"policy":"<policy id>","reason":"<=12 words"}. '
    )
    raw_proposal = _generate(backend, proposal_prompt, 72)
    proposal = _parse_json(raw_proposal)
    members = proposal.get("members")
    policy_id = proposal.get("policy")
    if (
        not isinstance(members, list)
        or len(members) != 4
        or not all(isinstance(item, int) for item in members)
        or policy_id not in allowed
    ):
        raise ValueError("formateur returned an invalid coalition proposal")
    contract = CoalitionContract(formateur_id, tuple(members), policy_id)
    if not set(contract.members).issubset(range(len(scenario.mandates))):
        raise ValueError("formateur named an unavailable coalition member")

    responses: dict[int, str] = {}
    raw_responses: dict[int, str] = {}
    for representative_id, mandate in enumerate(scenario.mandates):
        prompt = (
            f"You are representative {representative_id}. The proposed agreement is "
            f"members={list(contract.members)}, policy={contract.policy_id}. "
            f"Your earlier private position was {private_positions[representative_id]}. "
            f"Your principal's policy records: {json.dumps(_policy_records(scenario, representative_id), sort_keys=True)}. "
            f"{_rule_text(authority)} Decide your stated final vote. "
            'Respond exactly as {"vote":"<policy id>","support":true|false,"reason":"<=12 words"}. '
        )
        response = _generate(backend, prompt, 72)
        raw_responses[representative_id] = response
        vote = _parse_json(response).get("vote")
        if vote not in allowed:
            raise ValueError(f"representative {representative_id} returned invalid final vote {vote!r}")
        responses[representative_id] = vote

    record: DecisionRecord = resolve_contract(
        mandates=scenario.mandates,
        policies=scenario.policies,
        status_quo_id=scenario.status_quo_id,
        contract=contract,
        requested_votes=responses,
        authority=authority,
    )
    return {
        "scenario_id": scenario.scenario_id,
        "authority": authority.value,
        "formateur_id": formateur_id,
        "private_positions": dict(private_positions),
        "proposal": asdict(contract),
        "requested_votes": responses,
        "record": asdict(record),
        "raw_proposal": raw_proposal,
        "raw_responses": raw_responses,
    }


def run_common_contract_response(
    *,
    scenario: CoalitionScenario,
    private_positions: Mapping[int, str],
    contract: CoalitionContract,
    authority: AuthorityRule,
    backend: ChatBackend,
) -> dict[str, Any]:
    """Test one identical, exogenous contract under alternative authority rules.

    This deliberately removes formateur behaviour from the contrast.  It is a
    response/enforcement probe, not a coalition-formation experiment.
    """
    allowed = {policy.policy_id for policy in scenario.policies}
    if contract.policy_id not in allowed:
        raise ValueError("common contract must name an available policy")
    responses: dict[int, str] = {}
    raw_responses: dict[int, str] = {}
    for representative_id, mandate in enumerate(scenario.mandates):
        prompt = (
            f"You are representative {representative_id}. An exogenous agenda clerk, not a "
            f"representative, has placed this identical contract before every institution: "
            f"members={list(contract.members)}, policy={contract.policy_id}. "
            f"Your earlier private position was {private_positions[representative_id]}. "
            f"Your principal's policy records: {json.dumps(_policy_records(scenario, representative_id), sort_keys=True)}. "
            f"{_rule_text(authority)} Decide your stated final vote. "
            'Respond exactly as {"vote":"<policy id>","support":true|false,"reason":"<=12 words"}. '
        )
        response = _generate(backend, prompt, 72)
        raw_responses[representative_id] = response
        vote = _parse_json(response).get("vote")
        if vote not in allowed:
            raise ValueError(f"representative {representative_id} returned invalid final vote {vote!r}")
        responses[representative_id] = vote
    record = resolve_contract(
        mandates=scenario.mandates,
        policies=scenario.policies,
        status_quo_id=scenario.status_quo_id,
        contract=contract,
        requested_votes=responses,
        authority=authority,
    )
    return {
        "scenario_id": scenario.scenario_id,
        "authority": authority.value,
        "private_positions": dict(private_positions),
        "proposal": asdict(contract),
        "requested_votes": responses,
        "record": asdict(record),
        "raw_responses": raw_responses,
    }


def cached_backend(backend: ChatBackend, cache_dir: Path) -> CachedChatBackend:
    """Name the cache construction to keep probes auditable and restartable."""
    return CachedChatBackend(backend=backend, cache_dir=cache_dir)
