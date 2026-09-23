"""Post-hoc descriptive readout, not additional model counterfactuals or tests.

Ballot flips hold all other recorded actions fixed. State pivotality describes
the rule transition only; it does not predict how agents would subsequently act.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.commitment_memory import contract_state, project_sequence
from paper3.representation_metrics import representation_metrics


def readout(episode):
    if episode["status"] != "completed":
        return dict(status=episode["status"], outcomes_available=False,
                    reason="incomplete trajectory; no votes or payoffs imputed")
    events = episode["events"]
    first_event = next(e for e in events if e["type"] == "first_vote")
    state = contract_state(events)
    first, second = project_sequence(events)
    first_votes = first_event["votes"]
    actions = sorted(episode["actions"], key=lambda a: a["actor"])
    if (len(first_votes) != 7 or [a["actor"] for a in actions] != list(range(7))
            or any(type(v) is not bool for v in first_votes)
            or any(type(a["vote"]) is not bool for a in actions)):
        raise ValueError("requires all seven actual ballots in both rounds")
    if first_event["passed"] != (sum(first_votes) >= 4):
        raise ValueError("first-round passage mismatch")
    first_flips = []
    for actor in range(7):
        altered = copy.deepcopy(events)
        event = next(e for e in altered if e["type"] == "first_vote")
        event["votes"][actor] = not event["votes"][actor]
        event["passed"] = sum(event["votes"]) >= 4
        counterstate = contract_state(altered)
        first_flips.append(dict(actor=actor, policy_pivotal=event["passed"] != first_event["passed"],
            rule_state_pivotal=counterstate["status"] != state["status"],
            flipped_rule_status=counterstate["status"]))
    second_votes = [a["vote"] for a in actions]
    second_passed = sum(second_votes) >= 4
    if second_passed != episode["second_passed"]:
        raise ValueError("second-round passage mismatch")
    utilities = episode["profile"]["utilities"]
    utilities = {str(k): v for k, v in utilities.items()}
    passed = tuple(p for p, accepted in ((first, first_event["passed"]), (second, second_passed)) if accepted)
    metrics = representation_metrics(utilities, (first, second), passed, state["signers"])
    if metrics["realized"] != {str(k): v for k, v in episode["realized_utility"].items()}:
        raise ValueError("actual payoff mismatch")
    second_flips = []
    for actor, action in enumerate(actions):
        votes = list(second_votes)
        votes[actor] = not votes[actor]
        flipped_passed = sum(votes) >= 4
        due = actor in state["signers"] and state["status"] == "second_vote_due"
        second_flips.append(dict(actor=actor, obligation_due=due,
            policy_pivotal=flipped_passed != second_passed,
            own_utility_change_if_only_this_vote_flipped=utilities[str(actor)][second] * (flipped_passed - second_passed),
            flipped_vote_would_breach_live_promise=due and not votes[actor]))
    return dict(status="completed", outcomes_available=True, rule_status=state["status"],
        signers=state["signers"], nonsigners=[i for i in range(7) if i not in state["signers"]],
        first_project=first, first_votes=first_votes, first_passed=first_event["passed"],
        first_round_promise_breaches=[i for i in state["signers"] if not first_votes[i]] if len(state["signers"]) >= 4 else [],
        second_project=second, second_votes=second_votes, second_passed=second_passed,
        second_round_state_report_errors=[a["actor"] for a in actions if a["obligation_due"] !=
            (a["actor"] in state["signers"] and state["status"] == "second_vote_due")],
        first_ballot_flips=first_flips, second_ballot_flips=second_flips, **metrics,
        interpretation="descriptive, post-hoc; ballot flips do not generate new model behavior; regret is a menu gap, not proof of mandate abandonment")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("episode", type=Path)
    args = parser.parse_args()
    print(json.dumps(readout(json.loads(args.episode.read_text())), indent=2))
