"""Independent, read-only inventory check for the frozen Qwen B allocation.

The frozen runner replays scheduled episode prefixes. This extra check rejects
any decision file outside a scheduled prefix, index, profile, arm or seed. It
does not score agent behavior or modify the frozen run.
"""
from __future__ import annotations


def check(manifest, decisions, *, terminal=False):
    assignments = manifest["protocol"]["assignments"]
    scheduled = {row["id"]: row for row in assignments}
    if len(assignments) != 21 or len(scheduled) != 21:
        raise ValueError("expected 21 unique assignments")
    seen = {key: set() for key in scheduled}
    for saved in decisions:
        case = saved["case"]
        case_id = case["id"]
        if not isinstance(case_id, str) or "-" not in case_id:
            raise ValueError("invalid decision id")
        episode_id, suffix = case_id.rsplit("-", 1)
        if episode_id not in scheduled or len(suffix) != 2 or not suffix.isdigit():
            raise ValueError("unscheduled decision id")
        assignment = scheduled[episode_id]
        index = int(suffix)
        if index >= assignment["intended_calls"] or index in seen[episode_id]:
            raise ValueError("duplicate or out-of-range decision index")
        context = case["context"]
        if (context["index"] != index or
                context["profile_id"] != assignment["profile_id"] or
                context["arm"] != assignment["arm"] or
                case["request"]["seed"] != assignment["seed_base"] + index):
            raise ValueError("decision metadata differs from schedule")
        if terminal and saved["result"]["status"] == "prepared":
            raise ValueError("terminal inventory retains prepared decision")
        seen[episode_id].add(index)
    for episode_id, indices in seen.items():
        if indices != set(range(len(indices))):
            raise ValueError("noncontiguous decision prefix: " + episode_id)
    return dict(scheduled_episodes=len(scheduled), recorded_decisions=sum(map(len, seen.values())),
                episode_prefix_lengths={key: len(value) for key, value in seen.items()})
