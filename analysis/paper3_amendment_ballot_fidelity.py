"""Secondary fixed-history ballot-fidelity diagnostic for the amendment game.

This is a local counterfactual, not an equilibrium, motive, proposal-quality,
or population estimator. It is outside the frozen primary pilot protocol.
"""
from __future__ import annotations

from paper3 import amendment_institution as game
from paper3 import direct_ratification as base


def fixed_history_ballot_diagnostic(item, arm, events):
    """Flip one requested ballot field, hold the other six and agenda fixed."""
    game.validate_item(item)
    base.require(arm in game.ARMS and [event["type"] for event in events] ==
                 ["draft", "responses", "amendment", "final", "vote"],
                 "complete amendment history")
    amendment = events[2]["action"]["policy"]
    final = events[3]["action"]["policy"]
    requested = events[4]["requested"]
    base.require(len(requested) == 7 and
                 all(set(action) == {"amendment", "final"}
                     and type(action["amendment"]) is bool
                     and type(action["final"]) is bool for action in requested),
                 "requested ballot record")
    amend_votes = [action["amendment"] for action in requested]
    final_votes = [action["final"] for action in requested]
    original = game.enact(item, arm, amendment, final, amend_votes, final_votes)
    sums = base.district_totals(item["profile"])

    def utility(actor, enacted):
        return 0 if enacted == "q" else sums[f"r{actor}"][enacted]

    rows = []
    for actor in base.ACTORS:
        for field in ("amendment", "final"):
            alternate_amend = amend_votes.copy()
            alternate_final = final_votes.copy()
            target = alternate_amend if field == "amendment" else alternate_final
            target[actor] = not target[actor]
            replay = game.enact(item, arm, amendment, final,
                                alternate_amend, alternate_final)
            actual_utility = utility(actor, original["enacted_policy"])
            alternate_utility = utility(actor, replay["enacted_policy"])
            rows.append(dict(actor=actor, field=field,
                             requested=requested[actor][field],
                             actual_policy=original["enacted_policy"],
                             flipped_policy=replay["enacted_policy"],
                             actual_own_district_utility=actual_utility,
                             flipped_own_district_utility=alternate_utility,
                             strictly_harmful_requested_ballot=(
                                 alternate_utility > actual_utility),
                             strictly_helpful_requested_ballot=(
                                 alternate_utility < actual_utility),
                             enactment_pivotal=(replay["enacted_policy"] !=
                                                original["enacted_policy"])))
    return dict(arm=arm, actual_enacted_policy=original["enacted_policy"],
                rows=rows,
                strictly_harmful_count=sum(x["strictly_harmful_requested_ballot"]
                                           for x in rows),
                enactment_pivotal_count=sum(x["enactment_pivotal"] for x in rows),
                caveat="One-field fixed-history flips hold other actions fixed; they are not alternate trajectories or evidence of intent.")
