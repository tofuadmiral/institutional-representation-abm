"""Read-only validity summary; intentionally no significance tests on four histories."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def audit(root: Path) -> dict:
    sessions = [dict(file=p.name, **json.loads(p.read_text())) for p in sorted((root / "sessions").glob("*.json"))]
    calls = {p.stem: json.loads(p.read_text()) for p in (root / "calls").glob("*.json")}
    referenced = {k for r in sessions for k in r.get("call_keys", [])}
    missing = sorted(referenced - calls.keys())
    branches = [r for r in sessions if "actions" in r]
    summaries = []
    for r in branches:
        summary = {k: r.get(k) for k in ("file", "status", "shared_history", "condition", "ledger", "release",
                                               "due_count", "obligation_errors", "breaches", "false_obligations",
                                               "negative_unbound_votes", "first_passed", "second_passed", "realized_utility")}
        yes_count = sum(a["vote"] for a in r["actions"])
        summary["second_vote_pivotal_actors"] = [a["actor"] for a in r["actions"]
            if ((yes_count - int(a["vote"]) + int(not a["vote"])) >= 4) != (yes_count >= 4)]
        summaries.append(summary)
    histories = []
    for r in sessions:
        if "profile" not in r or r.get("status") != "completed":
            continue
        offer = next(e for e in r["events"] if e["type"] == "final_offer")
        ratification = next(e for e in r["events"] if e["type"] == "ratification")
        projects = (("A0", "B0"), ("A0", "B1"), ("A1", "B0"), ("A1", "B1"))[offer["package"]]
        gains = {int(i): sum(utility[p] for p in projects) for i, utility in r["profile"]["utilities"].items()}
        histories.append(dict(file=r["file"], package=offer["package"], first=offer["first"],
                              signers=[i for i, v in enumerate(ratification["signatures"]) if v],
                              negative_package_signers=[i for i, v in enumerate(ratification["signatures"]) if v and gains[i] < 0],
                              package_gains=gains))
    capability_groups = collections.defaultdict(list)
    for r in sessions:
        if "expected" in r and "principal_utility_if_accepted" in r["expected"]:
            capability_groups[(r.get("stage", "unspecified"), r.get("thinking"))].append(r)
    capability = []
    for (stage, thinking), rows in capability_groups.items():
        action_correct = utility_correct = exact = harmful_accepted = 0
        for r in rows:
            reply, expected = r.get("reply", {}), r["expected"]
            action_key = "accept" if "accept" in expected else "action"
            complete = r.get("status") == "completed"
            action_correct += complete and reply.get(action_key) == expected[action_key]
            utility_correct += complete and reply.get("principal_utility_if_accepted") == expected["principal_utility_if_accepted"]
            exact += complete and reply == expected
            accepts = reply.get("accept") is True if action_key == "accept" else reply.get("action") == "accept"
            harmful_accepted += complete and expected["principal_utility_if_accepted"] < 0 and accepts
        capability.append(dict(stage=stage, thinking=thinking, n=len(rows), exact=exact,
                               action_correct=action_correct, utility_correct=utility_correct,
                               harmful_cases=sum(r["expected"]["principal_utility_if_accepted"] < 0 for r in rows),
                               harmful_accepted=harmful_accepted,
                               failures=sum(r.get("status") != "completed" for r in rows)))
    return dict(root=str(root), recorded_calls=len(calls), sessions=len(sessions),
                completed=sum(r.get("status") == "completed" for r in sessions),
                failures=[{k: r.get(k) for k in ("file", "error")} for r in sessions if r.get("status") == "failed"],
                missing_referenced_calls=missing,
                finish_reasons=dict(collections.Counter(c["response"]["choices"][0].get("finish_reason") for c in calls.values())),
                prompt_tokens=sum(c["response"].get("usage", {}).get("prompt_tokens", 0) for c in calls.values()),
                completion_tokens=sum(c["response"].get("usage", {}).get("completion_tokens", 0) for c in calls.values()),
                histories=histories, branches=summaries, capability=capability)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    print(json.dumps(audit(parser.parse_args().root), indent=2))
