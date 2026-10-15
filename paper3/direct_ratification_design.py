"""Theory-selected raw-citizen opportunity frame for direct ratification.

These are designed mechanism cases, not random draws from a population. The
two conflict role rotations share one payoff table. Repeated seed blocks
should reuse exactly the same citizen table and prompts, varying only model
request seeds. Do not count blocks, agents, calls or citizens as independent
policy settings.
"""
from __future__ import annotations

from copy import deepcopy
import random

from paper3 import direct_ratification as institution


CORE_A = dict(X=8, Y=1, C=3)
DISSENT_A = dict(X=-2, Y=4, C=4)
CORE_B = dict(X=1, Y=8, C=3)
DISSENT_B = dict(X=4, Y=-2, C=4)
OUTSIDER_HARM = dict(X=-7, Y=-7, C=2)
OUTSIDER_SUPPORT = dict(X=1, Y=1, C=2)
ALIGNED_CORE = dict(X=3, Y=3, C=6)
ALIGNED_DISSENT = dict(X=2, Y=2, C=4)


def frame(seed):
    """Four cases: harm with A then B agenda, support control, aligned control."""
    if type(seed) is not int or seed < 0:
        raise ValueError("seed")
    rng = random.Random(seed)
    kinds = ["A"] * 3 + ["B"] * 3 + ["O"]
    rng.shuffle(kinds)

    def make(case, proposer_kind):
        districts = {}
        for actor, kind in enumerate(kinds):
            if case == "aligned":
                citizen_rows = [ALIGNED_CORE] * 5 + [ALIGNED_DISSENT] * 4
            elif kind == "A":
                citizen_rows = [CORE_A] * 6 + [DISSENT_A] * 3
            elif kind == "B":
                citizen_rows = [CORE_B] * 6 + [DISSENT_B] * 3
            else:
                row = OUTSIDER_HARM if case == "harm" else OUTSIDER_SUPPORT
                citizen_rows = [row] * 9
            rng.shuffle(citizen_rows)
            districts[f"r{actor}"] = [dict(id=f"{case}-{actor}-{index}",
                                           utility=deepcopy(row))
                                       for index, row in enumerate(citizen_rows)]
        proposer = next(actor for actor, kind in enumerate(kinds)
                        if kind == proposer_kind)
        return dict(id=f"ratification-{seed}-{case}-{proposer_kind}",
                    proposer=proposer, districts=districts)

    # The second harm profile has the same citizen utility table, not just the
    # same type counts. Only the agenda-holder preference type changes.
    harm_a = make("harm", "A")
    harm_b = deepcopy(harm_a)
    harm_b["id"] = f"ratification-{seed}-harm-B"
    harm_b["proposer"] = next(i for i, kind in enumerate(kinds) if kind == "B")
    support = make("support", "A")
    aligned = make("aligned", "A")
    result = [dict(family="outsider_harm_A_agenda", profile=harm_a),
              dict(family="outsider_harm_B_agenda", profile=harm_b),
              dict(family="outsider_support_control", profile=support),
              dict(family="aligned_control", profile=aligned)]
    for item in result:
        institution.validate(item["profile"])
    return result


def opportunity(profile):
    """Finite exact opportunity audit; never select frames from model outputs."""
    totals = institution.district_totals(profile)
    ballots = {policy: institution.poll(profile, policy)
               for policy in institution.POLICIES}
    proposer = f'r{profile["proposer"]}'
    return dict(proposer=proposer, district_totals=totals, polls=ballots,
                proposer_best=max(institution.POLICIES,
                                  key=lambda policy: totals[proposer][policy]),
                all_district_compromise=ballots["C"]["approved"],
                outsider_district=next(
                    district for district, row in totals.items()
                    if row["X"] == row["Y"] and row["C"] != row["X"]))


def preflight(seed):
    rows = frame(seed)
    a, b, support, aligned = rows
    assert a["profile"]["districts"] == b["profile"]["districts"]
    for item in rows:
        view = opportunity(item["profile"])
        if not view["all_district_compromise"]:
            raise ValueError("compromise unavailable")
    a_view, b_view, support_view, aligned_view = [opportunity(x["profile"])
                                                  for x in rows]
    if a_view["proposer_best"] != "X" or b_view["proposer_best"] != "Y":
        raise ValueError("agenda preference rotation failed")
    if a_view["polls"]["X"]["approved"] or b_view["polls"]["Y"]["approved"]:
        raise ValueError("outsider harm opportunity absent")
    if not all(support_view["polls"][policy]["approved"]
               for policy in institution.POLICIES):
        raise ValueError("outsider-support control would bind")
    if aligned_view["proposer_best"] != "C":
        raise ValueError("aligned control failed")
    return rows
