"""Deterministic preference profiles for the identification layer."""

from __future__ import annotations

import random
from enum import Enum

from agent_exploration.objectives import (
    AgentAction,
    ObjectiveTask,
    PolicyAlternative,
    PrincipalPreference,
    preference_distance,
)


class PreferenceScenario(str, Enum):
    ALIGNED = "aligned"
    POLARIZED = "polarized"
    FRAGMENTED = "fragmented"
    INTENSE_MINORITY = "intense_minority"


ALTERNATIVES = (
    PolicyAlternative("left", (-1.0, 0.0)),
    PolicyAlternative("center", (0.0, 0.0)),
    PolicyAlternative("right", (1.0, 0.0)),
)


def generate_objective_task(
    *,
    seed: int,
    scenario: PreferenceScenario,
    num_agents: int = 7,
) -> ObjectiveTask:
    if num_agents < 3:
        raise ValueError("num_agents must be at least three")
    rng = random.Random(seed)

    polarized_majority = -1.0 if seed % 2 == 0 else 1.0
    polarized_sides = [polarized_majority] * ((num_agents + 1) // 2)
    polarized_sides += [-polarized_majority] * (num_agents // 2)
    rng.shuffle(polarized_sides)

    fragmented_centers = [(-1.0, "left"), (0.0, "center"), (1.0, "right")]
    fragmented_assignments = [
        fragmented_centers[(agent_id + seed) % len(fragmented_centers)]
        for agent_id in range(num_agents)
    ]
    rng.shuffle(fragmented_assignments)

    minority_size = max(1, num_agents // 3)
    intense_minority_membership = [True] * minority_size
    intense_minority_membership += [False] * (num_agents - minority_size)
    rng.shuffle(intense_minority_membership)

    ideals: list[tuple[float, float]] = []
    groups: list[str] = []
    weights: list[float] = []
    for agent_id in range(num_agents):
        if scenario is PreferenceScenario.ALIGNED:
            ideals.append((rng.uniform(-0.2, 0.2), rng.uniform(-0.1, 0.1)))
            groups.append("aligned")
            weights.append(1.0)
        elif scenario is PreferenceScenario.POLARIZED:
            side = polarized_sides[agent_id]
            ideals.append((side, rng.uniform(-0.1, 0.1)))
            groups.append("left" if side < 0 else "right")
            weights.append(1.0)
        elif scenario is PreferenceScenario.FRAGMENTED:
            center, group = fragmented_assignments[agent_id]
            ideals.append((center, rng.uniform(-0.1, 0.1)))
            groups.append(group)
            weights.append(1.0)
        else:
            if intense_minority_membership[agent_id]:
                ideals.append((-1.0, rng.uniform(-0.05, 0.05)))
                groups.append("intense_minority")
                weights.append(2.0)
            else:
                ideals.append((0.25, rng.uniform(-0.1, 0.1)))
                groups.append("majority")
                weights.append(1.0)

    principals = tuple(
        PrincipalPreference(i, ideal, weights[i], groups[i])
        for i, ideal in enumerate(ideals)
    )
    initial_actions = tuple(
        AgentAction(
            agent_id=i,
            principal_id=i,
            alternative_id=min(
                ALTERNATIVES,
                key=lambda alternative: preference_distance(
                    principal.ideal_point, alternative.position
                ),
            ).alternative_id,
            rationale="nearest alternative to entrusted preference",
        )
        for i, principal in enumerate(principals)
    )

    shuffled_agents = list(range(num_agents))
    rng.shuffle(shuffled_agents)
    coalition_by_agent = {
        agent_id: f"coalition-{index % 2}"
        for index, agent_id in enumerate(shuffled_agents)
    }
    leader_id = rng.randrange(num_agents)
    return ObjectiveTask(
        task_id=f"objective-{scenario.value}-{seed}",
        principals=principals,
        alternatives=ALTERNATIVES,
        initial_actions=initial_actions,
        coalition_by_agent=coalition_by_agent,
        leader_id=leader_id,
        status_quo_id="center",
    )
