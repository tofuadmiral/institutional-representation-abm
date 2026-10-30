"""Prospective fixed-opportunity election diagnostic; not an election result.

The six early signature choices are an exogenous controlled intervention.
Only the focal agent is queried. This isolates the focal's consent choice
conditional on identical early coalitions across institutional arms; it does
not measure endogenous coalition formation or actual citizen voting.
"""
from __future__ import annotations

from paper3 import electoral_accountability as game


SPECS = (
    dict(id="controlled-conflict-c", focal=1, supporters=(0, 3, 5),
         values=(-3, -3, -3, -3, -3, 9, 9, 9, 9), office_bonus=30),
    dict(id="controlled-conflict-d", focal=6, supporters=(1, 2, 4),
         values=(8, 8, 8, 8, -3, -3, -3, -3, -3), office_bonus=30),
    dict(id="controlled-aligned", focal=2, supporters=(0, 4, 6),
         values=(4, 4, 4, 4, 4, -2, -2, -2, -2), office_bonus=30),
    dict(id="controlled-no-office", focal=1, supporters=(0, 3, 5),
         values=(-3, -3, -3, -3, -3, 9, 9, 9, 9), office_bonus=0),
)


def inventory():
    rows = []
    for spec in SPECS:
        supporters = set(spec["supporters"])
        assert len(supporters) == 3 and spec["focal"] not in supporters
        districts = {}
        for actor in game.ACTORS:
            values = (spec["values"] if actor == spec["focal"] else
                      ((2,) * 9 if actor in supporters else (-2,) * 9))
            districts[f"r{actor}"] = [dict(id=f"{spec['id']}-r{actor}-c{i}", p=value)
                                       for i, value in enumerate(values)]
        profile = dict(id=spec["id"], focal=spec["focal"],
                       office_bonus=spec["office_bonus"], districts=districts)
        game.validate(profile)
        early = {f"r{actor}": actor in supporters
                 for actor in game.ACTORS if actor != spec["focal"]}
        assert sum(early.values()) == 3
        rows.append(dict(id=spec["id"], focal=spec["focal"],
                         supporters=sorted(supporters),
                         focal_sum=sum(spec["values"]),
                         focal_majority_yes=sum(value > 0 for value in spec["values"]),
                         office_bonus=spec["office_bonus"],
                         profile=profile, early_consents=early))
    return rows


def cases():
    rows = []
    for item in inventory():
        early = dict(type="early_consents", consents=item["early_consents"])
        for arm in game.ARMS:
            # Promise signatures are payoff-irrelevant. Query the subsequent
            # requested ballot instead; identical record labels should then
            # imply identical meaningful choices under nonbinding rules.
            stage = "consent" if arm.startswith("binding") else "vote"
            events = ([early] if stage == "consent" else
                      [early, dict(type="consent", consents=[
                          True if actor == item["focal"] else
                          item["early_consents"][f"r{actor}"]
                          for actor in game.ACTORS])])
            rows.append(dict(id=f"{item['id']}--{arm}", profile_id=item["id"],
                             arm=arm, actor=item["focal"], stage=stage,
                             messages=game.messages(item["profile"], arm,
                                                    item["focal"], stage, events)))
    assert len(rows) == 16
    return rows


def opportunity_audit():
    """Exact conditional payoffs if the three early signers later vote yes.

    This is an offline opportunity proof, not an assumption that LLM voters
    will actually make those choices in a future full-institution run.
    """
    result = {}
    for item in inventory():
        profile, focal = item["profile"], item["focal"]
        early = dict(type="early_consents", consents=item["early_consents"])
        result[item["id"]] = {}
        for arm in game.ARMS:
            payoffs = {}
            for consent in (False, True):
                for requested in (False, True):
                    full = [consent if actor == focal else
                            item["early_consents"][f"r{actor}"]
                            for actor in game.ACTORS]
                    votes = [requested if actor == focal else
                             item["early_consents"][f"r{actor}"]
                             for actor in game.ACTORS]
                    events = [early, dict(type="consent", consents=full),
                              dict(type="vote", requested=votes)]
                    outcome = game.score(profile, arm, events)
                    payoffs[f"consent={consent},requested={requested}"] = dict(
                        payoff=outcome["representative_payoffs"][f"r{focal}"],
                        enacted=outcome["enacted_policy"],
                        retained=outcome["retained"][f"r{focal}"])
            result[item["id"]][arm] = payoffs
    return result


def screen(actions):
    """All-assignment selected-case rule fixed before observing hosted actions."""
    cells = {row["id"]: actions.get(row["id"])
             for row in cases()}
    complete = all(type(value) is bool for value in cells.values())
    def pair(profile, prefix):
        return [cells[f"{profile}--{prefix}_requested_record"],
                cells[f"{profile}--{prefix}_executed_record"]]
    conflicts = {profile: pair(profile, "binding")
                 for profile in ("controlled-conflict-c", "controlled-conflict-d")}
    controls = dict(
        aligned_binding=pair("controlled-aligned", "binding"),
        no_office_binding=pair("controlled-no-office", "binding"),
        promise_votes={row["id"]: pair(row["id"], "promise")
                       for row in inventory()},
    )
    # Aligned and zero-office binding consent can be payoff-indifferent:
    # an uncontracted focal may still cast the fourth yes ballot. Preserve
    # those actions descriptively, but do not require a unique consent.
    lead = (complete and all(value == [True, False] for value in conflicts.values())
            and all(controls["promise_votes"][row["id"]] ==
                    ([True, True] if row["id"] in
                     ("controlled-aligned", "controlled-no-office")
                     else [False, False]) for row in inventory()))
    return dict(all_16_scored=complete, conflicts=conflicts, controls=controls,
                selected_case_lead=lead,
                classification=("controlled_consent_lead" if lead else
                                "incomplete_not_identified" if not complete else
                                "no_prespecified_controlled_lead"),
                caveat="Exogenous identical early signatures isolate only a conditional focal consent decision. This is not endogenous coalition formation, a seven-agent trajectory, or real voter behavior. A selected-case lead requires untouched full-institution games and another model before a paper claim.")
