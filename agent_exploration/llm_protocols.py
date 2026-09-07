"""Matched LLM protocols for private voting and one-round peer exposure."""

from __future__ import annotations

import json
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Sequence

from agent_exploration.local_models import ChatBackend
from agent_exploration.objective_protocols import (
    OPEN_DELIBERATION,
    PRIVATE_BALLOT,
    collective_choice,
)
from agent_exploration.objectives import (
    AgentAction,
    CollectiveOutcome,
    ObjectiveTask,
    preference_distance,
)
from agent_exploration.representatives import LocalModelRepresentative


PUBLIC_VOTE_EXPOSURE = "public_vote_exposure"
ARGUMENTS_INTENSITY_HIDDEN_MINORITY_FIRST = (
    "arguments_intensity_hidden_minority_first"
)
ARGUMENTS_INTENSITY_HIDDEN_MINORITY_LAST = (
    "arguments_intensity_hidden_minority_last"
)
ARGUMENTS_INTENSITY_SHOWN_MINORITY_FIRST = (
    "arguments_intensity_shown_minority_first"
)
ARGUMENTS_INTENSITY_SHOWN_MINORITY_LAST = (
    "arguments_intensity_shown_minority_last"
)


def generate_model_baseline(
    task: ObjectiveTask,
    backend: ChatBackend,
    *,
    seed: int,
    workers: int = 1,
) -> tuple[ObjectiveTask, list[dict]]:
    """Replace oracle actions with independent model choices made in isolation."""
    _validate_workers(workers)

    def choose(agent_id: int) -> tuple[AgentAction, dict]:
        principal = task.principals[agent_id]
        alternatives = _ordered_alternatives(task, seed * 100_000 + agent_id)
        action = LocalModelRepresentative(
            agent_id, principal, backend
        ).choose_initial_action(alternatives)
        return action, {
            "agent_id": agent_id,
            "principal_id": principal.principal_id,
            "stage": "initial_private_position",
            "institution": "shared_baseline",
            "presented_order": json.dumps(
                [alternative.alternative_id for alternative in alternatives]
            ),
            "peer_order": "[]",
            "initial_choice": action.alternative_id,
            "final_choice": action.alternative_id,
            "changed_choice": False,
            "rationale": action.rationale,
        }

    pairs = _map_agents(choose, len(task.principals), workers)
    actions, logs = zip(*pairs)
    return replace(task, initial_actions=tuple(actions)), list(logs)


def run_model_private_ballot(
    task: ObjectiveTask,
    backend: ChatBackend,
    *,
    seed: int,
    workers: int = 1,
) -> tuple[CollectiveOutcome, list[dict]]:
    """Second independent binding vote, controlling for reconsideration."""
    _validate_workers(workers)

    def vote(agent_id: int) -> tuple[AgentAction, dict]:
        initial = task.action_for_agent(agent_id)
        principal = task.principal_for(initial.principal_id)
        alternatives = _ordered_alternatives(
            task, seed * 100_000 + 10_000 + agent_id
        )
        final = LocalModelRepresentative(agent_id, principal, backend).cast_binding_vote(
            alternatives, initial_action=initial
        )
        return final, _vote_log(
            final,
            initial,
            institution=PRIVATE_BALLOT,
            alternatives=alternatives,
            peers=(),
        )

    pairs = _map_agents(vote, len(task.principals), workers)
    actions, logs = zip(*pairs)
    outcome = CollectiveOutcome(
        institution=PRIVATE_BALLOT,
        final_actions=tuple(actions),
        collective_choice_id=collective_choice(task, actions),
        metadata={
            "protocol_type": "llm",
            "peer_messages": 0,
            "binding_vote": True,
            "reconsideration_call": True,
            "effective_decision_makers": len(actions),
        },
    )
    return outcome, list(logs)


def run_model_open_deliberation(
    task: ObjectiveTask,
    backend: ChatBackend,
    *,
    seed: int,
    workers: int = 1,
) -> tuple[CollectiveOutcome, list[dict]]:
    """Expose each agent to all other initial statements, then bind its vote."""
    return _run_model_peer_exposure(
        task,
        backend,
        seed=seed,
        workers=workers,
        institution=OPEN_DELIBERATION,
        include_peer_rationales=True,
    )


def run_model_public_vote_exposure(
    task: ObjectiveTask,
    backend: ChatBackend,
    *,
    seed: int,
    workers: int = 1,
) -> tuple[CollectiveOutcome, list[dict]]:
    """Expose each agent to peer votes without their arguments."""
    return _run_model_peer_exposure(
        task,
        backend,
        seed=seed,
        workers=workers,
        institution=PUBLIC_VOTE_EXPOSURE,
        include_peer_rationales=False,
    )


def _run_model_peer_exposure(
    task: ObjectiveTask,
    backend: ChatBackend,
    *,
    seed: int,
    workers: int,
    institution: str,
    include_peer_rationales: bool,
) -> tuple[CollectiveOutcome, list[dict]]:
    _validate_workers(workers)

    def vote(agent_id: int) -> tuple[AgentAction, dict]:
        initial = task.action_for_agent(agent_id)
        principal = task.principal_for(initial.principal_id)
        alternatives = _ordered_alternatives(
            task, seed * 100_000 + 10_000 + agent_id
        )
        peers = [
            action for action in task.initial_actions if action.agent_id != agent_id
        ]
        random.Random(seed * 100_000 + 20_000 + agent_id).shuffle(peers)
        final = LocalModelRepresentative(agent_id, principal, backend).cast_binding_vote(
            alternatives,
            initial_action=initial,
            peer_statements=peers,
            include_peer_rationales=include_peer_rationales,
        )
        return final, _vote_log(
            final,
            initial,
            institution=institution,
            alternatives=alternatives,
            peers=peers,
        )

    pairs = _map_agents(vote, len(task.principals), workers)
    actions, logs = zip(*pairs)
    outcome = CollectiveOutcome(
        institution=institution,
        final_actions=tuple(actions),
        collective_choice_id=collective_choice(task, actions),
        metadata={
            "protocol_type": "llm",
            "peer_messages": len(actions) * (len(actions) - 1),
            "peer_arguments": include_peer_rationales,
            "binding_vote": True,
            "reconsideration_call": True,
            "effective_decision_makers": len(actions),
        },
    )
    return outcome, list(logs)


def run_model_argument_mechanism(
    task: ObjectiveTask,
    backend: ChatBackend,
    *,
    seed: int,
    intensity_visible: bool,
    minority_last: bool,
    workers: int = 1,
) -> tuple[CollectiveOutcome, list[dict]]:
    """Counterbalance standardized argument content and minority speaking order."""
    _validate_workers(workers)
    groups = {principal.group for principal in task.principals}
    if "intense_minority" not in groups or "majority" not in groups:
        raise ValueError("argument mechanism probe requires an intense-minority task")

    if intensity_visible and minority_last:
        institution = ARGUMENTS_INTENSITY_SHOWN_MINORITY_LAST
    elif intensity_visible:
        institution = ARGUMENTS_INTENSITY_SHOWN_MINORITY_FIRST
    elif minority_last:
        institution = ARGUMENTS_INTENSITY_HIDDEN_MINORITY_LAST
    else:
        institution = ARGUMENTS_INTENSITY_HIDDEN_MINORITY_FIRST

    standardized = {
        action.agent_id: AgentAction(
            action.agent_id,
            action.principal_id,
            action.alternative_id,
            _standardized_argument(task, action, intensity_visible=intensity_visible),
        )
        for action in task.initial_actions
    }

    def vote(agent_id: int) -> tuple[AgentAction, dict]:
        initial = task.action_for_agent(agent_id)
        principal = task.principal_for(initial.principal_id)
        alternatives = _ordered_alternatives(
            task, seed * 100_000 + 10_000 + agent_id
        )
        peers = [
            standardized[action.agent_id]
            for action in task.initial_actions
            if action.agent_id != agent_id
        ]
        minority = [
            peer
            for peer in peers
            if task.principal_for(peer.principal_id).group == "intense_minority"
        ]
        majority = [
            peer
            for peer in peers
            if task.principal_for(peer.principal_id).group == "majority"
        ]
        random.Random(seed * 100_000 + 30_000 + agent_id).shuffle(minority)
        random.Random(seed * 100_000 + 40_000 + agent_id).shuffle(majority)
        ordered_peers = majority + minority if minority_last else minority + majority
        final = LocalModelRepresentative(agent_id, principal, backend).cast_binding_vote(
            alternatives,
            initial_action=initial,
            peer_statements=ordered_peers,
            include_peer_rationales=True,
        )
        return final, _vote_log(
            final,
            initial,
            institution=institution,
            alternatives=alternatives,
            peers=ordered_peers,
        )

    pairs = _map_agents(vote, len(task.principals), workers)
    actions, logs = zip(*pairs)
    outcome = CollectiveOutcome(
        institution=institution,
        final_actions=tuple(actions),
        collective_choice_id=collective_choice(task, actions),
        metadata={
            "protocol_type": "llm_mechanism_probe",
            "peer_messages": len(actions) * (len(actions) - 1),
            "peer_arguments": True,
            "intensity_visible": intensity_visible,
            "minority_last": minority_last,
            "binding_vote": True,
            "effective_decision_makers": len(actions),
        },
    )
    return outcome, list(logs)


def _standardized_argument(
    task: ObjectiveTask,
    action: AgentAction,
    *,
    intensity_visible: bool,
) -> str:
    principal = task.principal_for(action.principal_id)
    if not intensity_visible:
        return (
            f"I support {action.alternative_id}. It is my principal's most-preferred "
            "available policy."
        )
    chosen = task.alternative_for(action.alternative_id)
    chosen_loss = principal.weight * preference_distance(
        principal.ideal_point, chosen.position
    )
    other_losses = [
        principal.weight
        * preference_distance(principal.ideal_point, alternative.position)
        for alternative in task.alternatives
        if alternative.alternative_id != action.alternative_id
    ]
    return (
        f"I support {action.alternative_id}. My principal's priority weight is "
        f"{principal.weight}. Its weighted loss for this policy is {chosen_loss:.6f}; "
        f"its next-lowest available weighted loss is {min(other_losses):.6f}."
    )


def _ordered_alternatives(task: ObjectiveTask, seed: int) -> list:
    alternatives = list(task.alternatives)
    random.Random(seed).shuffle(alternatives)
    return alternatives


def _vote_log(
    final: AgentAction,
    initial: AgentAction,
    *,
    institution: str,
    alternatives: Sequence,
    peers: Sequence[AgentAction],
) -> dict:
    return {
        "agent_id": final.agent_id,
        "principal_id": final.principal_id,
        "stage": "binding_vote",
        "institution": institution,
        "presented_order": json.dumps(
            [alternative.alternative_id for alternative in alternatives]
        ),
        "peer_order": json.dumps([peer.agent_id for peer in peers]),
        "initial_choice": initial.alternative_id,
        "final_choice": final.alternative_id,
        "changed_choice": final.alternative_id != initial.alternative_id,
        "rationale": final.rationale,
    }


def _map_agents(function, count: int, workers: int):
    if workers == 1:
        return [function(agent_id) for agent_id in range(count)]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(function, range(count)))


def _validate_workers(workers: int) -> None:
    if workers < 1:
        raise ValueError("workers must be positive")
