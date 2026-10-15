from analysis.paper3_amendment_ballot_fidelity import fixed_history_ballot_diagnostic
from paper3 import amendment_opportunity as opportunity


def events(item, amend_votes, final_votes):
    return [dict(type="draft", action=dict(policy=item["favorite"])),
            dict(type="responses", responses=[]),
            dict(type="amendment", action=dict(policy="C")),
            dict(type="final", action=dict(policy=item["favorite"])),
            dict(type="vote", requested=[dict(amendment=a, final=f)
                                         for a, f in zip(amend_votes, final_votes,
                                                         strict=True)])]


def test_pivotal_outsider_refusal_can_be_strictly_harmful():
    item = opportunity.draw(0, "mandate_aligned")
    outsider = item["outsider"]
    backers = [a for a in item["compromise_over_favorite"] if a != outsider]
    assert len(backers) == 3
    amend = [a in backers for a in range(7)]
    report = fixed_history_ballot_diagnostic(item, "open_amendment",
                                             events(item, amend, [True] * 7))
    row = next(x for x in report["rows"]
               if x["actor"] == outsider and x["field"] == "amendment")
    assert row["actual_policy"] == item["favorite"]
    assert row["flipped_policy"] == "C"
    assert row["strictly_harmful_requested_ballot"]


def test_majority_imposed_loss_is_not_automatically_own_ballot_error():
    item = opportunity.draw(0, "mandate_aligned")
    amend = [a in item["compromise_over_favorite"] for a in range(7)]
    report = fixed_history_ballot_diagnostic(item, "open_amendment",
                                             events(item, amend, [True] * 7))
    nonbacker = next(a for a in range(7) if a not in item["compromise_over_favorite"])
    row = next(x for x in report["rows"]
               if x["actor"] == nonbacker and x["field"] == "amendment")
    assert row["actual_policy"] == "C"
    assert not row["strictly_harmful_requested_ballot"]
    assert not row["enactment_pivotal"]


def test_closed_advisory_amendment_vote_cannot_be_causal():
    item = opportunity.draw(0, "mandate_aligned")
    report = fixed_history_ballot_diagnostic(item, "closed_agenda",
                                             events(item, [False] * 7, [True] * 7))
    assert all(not x["enactment_pivotal"] and
               not x["strictly_harmful_requested_ballot"]
               for x in report["rows"] if x["field"] == "amendment")
