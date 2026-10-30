"""Prospective failure scope, never a historical completion-policy revision.

An unusable instrument stops globally; a completed, attributable, billing-safe
but illegal/incorrect decision stops its independent episode without repair.
The gate treats each already-assigned task as one independent diagnostic unit.
This does not authorize an institutional launch or establish missing-at-random.
"""

VERSION = "independent_episode_failure_scope_v1"


def classify(status, result):
    if status == "not_started":
        return "not_started"
    if status != "recorded" or type(result) is not dict or result.get("usable") is not True:
        return "global_stop"
    if result.get("valid_action") is not True or result.get("exact") is not True:
        return "episode_failure"
    return "passed"
