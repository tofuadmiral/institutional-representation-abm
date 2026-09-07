"""Core types for experiments on delegated-objective fidelity."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import dist
from typing import Any, Mapping, Optional, Tuple


Point = Tuple[float, ...]


def preference_distance(a: Point, b: Point) -> float:
    if len(a) != len(b):
        raise ValueError("preference points must have the same dimensionality")
    return dist(a, b)


@dataclass(frozen=True)
class PrincipalPreference:
    """A structured objective entrusted to one representative."""

    principal_id: int
    ideal_point: Point
    weight: float = 1.0
    group: str = "default"

    def __post_init__(self) -> None:
        if self.principal_id < 0:
            raise ValueError("principal_id must be non-negative")
        if not self.ideal_point:
            raise ValueError("ideal_point must have at least one dimension")
        if self.weight <= 0:
            raise ValueError("principal weight must be positive")
        if not self.group:
            raise ValueError("group must be non-empty")


@dataclass(frozen=True)
class PolicyAlternative:
    alternative_id: str
    position: Point

    def __post_init__(self) -> None:
        if not self.alternative_id:
            raise ValueError("alternative_id must be non-empty")
        if not self.position:
            raise ValueError("alternative position must have at least one dimension")


@dataclass(frozen=True)
class AgentAction:
    """A representative's observable choice at one stage of the process."""

    agent_id: int
    principal_id: int
    alternative_id: str
    rationale: str = ""


@dataclass(frozen=True)
class ObjectiveTask:
    """A matched preference profile and policy choice set."""

    task_id: str
    principals: Tuple[PrincipalPreference, ...]
    alternatives: Tuple[PolicyAlternative, ...]
    initial_actions: Tuple[AgentAction, ...]
    coalition_by_agent: Mapping[int, str]
    leader_id: int
    status_quo_id: str

    def __post_init__(self) -> None:
        if len(self.principals) < 3:
            raise ValueError("an objective task requires at least three principals")
        dimensions = {len(p.ideal_point) for p in self.principals}
        dimensions.update(len(a.position) for a in self.alternatives)
        if len(dimensions) != 1:
            raise ValueError("all preferences and alternatives must share dimensionality")

        principal_ids = [p.principal_id for p in self.principals]
        if len(principal_ids) != len(set(principal_ids)):
            raise ValueError("principal ids must be unique")
        alternative_ids = [a.alternative_id for a in self.alternatives]
        if len(alternative_ids) != len(set(alternative_ids)):
            raise ValueError("alternative ids must be unique")
        if self.status_quo_id not in alternative_ids:
            raise ValueError("status_quo_id must identify an alternative")

        action_agent_ids = [a.agent_id for a in self.initial_actions]
        if len(action_agent_ids) != len(set(action_agent_ids)):
            raise ValueError("agent ids must be unique")
        if set(a.principal_id for a in self.initial_actions) != set(principal_ids):
            raise ValueError("every principal must have exactly one representative action")
        if any(a.alternative_id not in alternative_ids for a in self.initial_actions):
            raise ValueError("actions must select an available alternative")
        if self.leader_id not in action_agent_ids:
            raise ValueError("leader_id must identify an agent")
        if set(self.coalition_by_agent) != set(action_agent_ids):
            raise ValueError("every agent must have a coalition assignment")

    def principal_for(self, principal_id: int) -> PrincipalPreference:
        for principal in self.principals:
            if principal.principal_id == principal_id:
                return principal
        raise KeyError(principal_id)

    def alternative_for(self, alternative_id: str) -> PolicyAlternative:
        for alternative in self.alternatives:
            if alternative.alternative_id == alternative_id:
                return alternative
        raise KeyError(alternative_id)

    def action_for_agent(self, agent_id: int) -> AgentAction:
        for action in self.initial_actions:
            if action.agent_id == agent_id:
                return action
        raise KeyError(agent_id)


@dataclass(frozen=True)
class CollectiveOutcome:
    """Agent actions and collective policy produced by an institution."""

    institution: str
    final_actions: Tuple[AgentAction, ...]
    collective_choice_id: Optional[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)
