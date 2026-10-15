"""Arithmetic opportunity check for electoral credit and coalition enforcement.

This is an offline stylized decision problem, not an agent experiment.  The
incumbent has nine synthetic constituents and a district-sum mandate plus a
fixed value for retaining office.  Three other chamber yes votes are fixed,
so its executed vote is pivotal for a four-vote majority.  A four-member
binding contract can execute yes despite the incumbent requesting no.

The electorate votes to retain the incumbent when the publicly attributed
yes/no action agrees with each citizen's sign of utility from the project;
the alternative is a fixed status-quo challenger.  This is a deliberately
simple position-based election rule, not a claim about human voters.
"""
from __future__ import annotations

from itertools import product


def evaluate(
    citizen_utilities: tuple[int, ...],
    *,
    office_bonus: int,
    record: str,
    binding: bool,
    other_yes: int = 3,
) -> list[dict]:
    if len(citizen_utilities) != 9 or any(type(u) is not int for u in citizen_utilities):
        raise ValueError("nine integer citizen utilities required")
    if type(office_bonus) is not int or office_bonus < 0:
        raise ValueError("nonnegative integer office bonus required")
    if record not in ("requested", "executed"):
        raise ValueError("record must be requested or executed")
    if type(binding) is not bool or type(other_yes) is not int or not 0 <= other_yes <= 6:
        raise ValueError("invalid institution or chamber votes")

    district_sum = sum(citizen_utilities)
    options = []
    for consent, requested_yes in product((False, True), repeat=2):
        executed_yes = requested_yes or (binding and consent)
        enacted = other_yes + int(executed_yes) >= 4
        observed_yes = requested_yes if record == "requested" else executed_yes
        citizen_ballots = [observed_yes == (utility > 0)
                           for utility in citizen_utilities]
        retained = sum(citizen_ballots) >= 5
        options.append(dict(consent=consent, requested_yes=requested_yes,
                            executed_yes=executed_yes, enacted=enacted,
                            retain_votes=sum(citizen_ballots), retained=retained,
                            citizen_ballots=citizen_ballots,
                            district_policy_utility=district_sum if enacted else 0,
                            representative_payoff=(district_sum if enacted else 0) +
                            (office_bonus if retained else 0)))
    return options


def unique_optimum(options: list[dict]) -> dict | None:
    if not options:
        raise ValueError("no decision options")
    maximum = max(row["representative_payoff"] for row in options)
    winners = [row for row in options if row["representative_payoff"] == maximum]
    return winners[0] if len(winners) == 1 else None
