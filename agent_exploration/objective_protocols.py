"""Institutional treatments for delegated preference profiles."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable, Sequence

from agent_exploration.objectives import AgentAction, CollectiveOutcome, ObjectiveTask


PRIVATE_BALLOT = "private_ballot"
OPEN_DELIBERATION = "open_deliberation"
DELEGATED_LEADER = "delegated_leader"
COALITION_DISCIPLINE = "coalition_discipline"

INSTITUTIONS = (
    PRIVATE_BALLOT,
    OPEN_DELIBERATION,
    DELEGATED_LEADER,
    COALITION_DISCIPLINE,
)


def collective_choice(task: ObjectiveTask, actions: Sequence[AgentAction]) -> str:
    """Plurality selection with the declared status quo as the tie rule."""
    counts = Counter(action.alternative_id for action in actions)
    highest = max(counts.values())
    winners = [choice for choice, count in counts.items() if count == highest]
    return winners[0] if len(winners) == 1 else task.status_quo_id


def private_ballot(task: ObjectiveTask) -> CollectiveOutcome:
    actions = task.initial_actions
    return CollectiveOutcome(
        institution=PRIVATE_BALLOT,
        final_actions=actions,
        collective_choice_id=collective_choice(task, actions),
        metadata={"peer_messages": 0, "effective_decision_makers": len(actions)},
    )


def open_deliberation(
    task: ObjectiveTask,
    *,
    compromise_tolerance: float = 1.0,
) -> CollectiveOutcome:
    """Move agents to the plurality proposal when its extra loss is tolerable.

    This deterministic rule is an identification fixture, not the assumed LLM
    behavior. In the generative phase, the model will decide whether to change
    its action after seeing peer arguments.
    """
    if compromise_tolerance < 0:
        raise ValueError("compromise_tolerance must be non-negative")
    proposal = collective_choice(task, task.initial_actions)
    proposal_position = task.alternative_for(proposal).position
    actions = []
    changed = 0
    for initial in task.initial_actions:
        principal = task.principal_for(initial.principal_id)
        initial_position = task.alternative_for(initial.alternative_id).position
        initial_loss = _distance(principal.ideal_point, initial_position)
        proposal_loss = _distance(principal.ideal_point, proposal_position)
        if proposal_loss - initial_loss <= compromise_tolerance:
            choice = proposal
        else:
            choice = initial.alternative_id
        changed += choice != initial.alternative_id
        actions.append(
            AgentAction(initial.agent_id, initial.principal_id, choice, "deliberative compromise")
        )
    return CollectiveOutcome(
        institution=OPEN_DELIBERATION,
        final_actions=tuple(actions),
        collective_choice_id=collective_choice(task, actions),
        metadata={
            "peer_messages": len(actions),
            "changed_actions": changed,
            "compromise_tolerance": compromise_tolerance,
            "effective_decision_makers": len(actions),
        },
    )


def delegated_leader(task: ObjectiveTask) -> CollectiveOutcome:
    leader = task.action_for_agent(task.leader_id)
    actions = tuple(
        AgentAction(
            action.agent_id,
            action.principal_id,
            leader.alternative_id,
            "bound to delegated leader",
        )
        for action in task.initial_actions
    )
    return CollectiveOutcome(
        institution=DELEGATED_LEADER,
        final_actions=actions,
        collective_choice_id=leader.alternative_id,
        metadata={
            "leader_id": task.leader_id,
            "peer_messages": 1,
            "effective_decision_makers": 1,
        },
    )


def coalition_discipline(task: ObjectiveTask) -> CollectiveOutcome:
    """Bind each representative to the plurality position of its coalition."""
    members: dict[str, list[AgentAction]] = defaultdict(list)
    for action in task.initial_actions:
        members[task.coalition_by_agent[action.agent_id]].append(action)

    platforms = {
        coalition: collective_choice(task, coalition_actions)
        for coalition, coalition_actions in members.items()
    }
    actions = tuple(
        AgentAction(
            action.agent_id,
            action.principal_id,
            platforms[task.coalition_by_agent[action.agent_id]],
            "bound to coalition platform",
        )
        for action in task.initial_actions
    )
    return CollectiveOutcome(
        institution=COALITION_DISCIPLINE,
        final_actions=actions,
        collective_choice_id=collective_choice(task, actions),
        metadata={
            "coalition_platforms": platforms,
            "peer_messages": len(task.initial_actions),
            "effective_decision_makers": len(platforms),
        },
    )


def _distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def run_institution(
    task: ObjectiveTask,
    institution: str,
    *,
    compromise_tolerance: float = 1.0,
) -> CollectiveOutcome:
    if institution == PRIVATE_BALLOT:
        return private_ballot(task)
    if institution == OPEN_DELIBERATION:
        return open_deliberation(task, compromise_tolerance=compromise_tolerance)
    if institution == DELEGATED_LEADER:
        return delegated_leader(task)
    if institution == COALITION_DISCIPLINE:
        return coalition_discipline(task)
    raise ValueError(f"unknown institution: {institution}")


def run_institutions(
    task: ObjectiveTask,
    institutions: Iterable[str] = INSTITUTIONS,
    *,
    compromise_tolerance: float = 1.0,
) -> list[CollectiveOutcome]:
    return [
        run_institution(
            task, institution, compromise_tolerance=compromise_tolerance,
        )
        for institution in institutions
    ]
