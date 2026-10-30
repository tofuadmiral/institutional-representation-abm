"""Prospective constituent-release institution; pure controller, no model calls.

This is exploratory infrastructure. A mechanical release/enforcement difference
is not a behavioral finding about representative agents.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from paper3 import mandate_release_rival_opportunity as opportunity

ARMS = ("irrevocable", "constituent_release")
ACTORS = opportunity.ACTORS
PROJECTS = opportunity.SECOND_PROJECTS
MAX_MESSAGE = 1600


@dataclass(frozen=True)
class Offer:
    second_project: str
    coalition: tuple[int, ...]
    message: str


@dataclass(frozen=True)
class Episode:
    arm: str
    shocked: bool
    proposer: int
    draft: Offer
    responses: tuple[dict[str, object], ...]
    final: Offer
    consent: tuple[bool, ...]
    active: bool
    requested_x: tuple[bool, ...]
    executed_x: tuple[bool, ...]
    x_passed: bool
    release_ballots: tuple[tuple[int, int], ...]
    released: tuple[int, ...]
    requested_y: tuple[bool, ...]
    executed_y: tuple[bool, ...]
    y_passed: bool
    district_utilities: tuple[int, ...]
    citizen_utilities: tuple[tuple[int, ...], ...]


def parse_offer(value: object) -> Offer:
    if type(value) is not dict or set(value) != {
        "second_project", "coalition", "message"
    }:
        raise ValueError("offer fields")
    project, coalition, message = (
        value["second_project"], value["coalition"], value["message"]
    )
    if project not in PROJECTS or type(coalition) is not list or len(coalition) not in (0, 4):
        raise ValueError("offer project or coalition size")
    if any(type(actor) is not int or actor not in ACTORS for actor in coalition):
        raise ValueError("offer coalition member")
    if len(set(coalition)) != len(coalition):
        raise ValueError("duplicate coalition member")
    if type(message) is not str or len(message) > MAX_MESSAGE:
        raise ValueError("offer message")
    return Offer(project, tuple(sorted(coalition)), message)


def parse_response(value: object) -> dict[str, object]:
    if type(value) is not dict or set(value) != {"support", "counter_project", "message"}:
        raise ValueError("response fields")
    if type(value["support"]) is not bool or value["counter_project"] not in PROJECTS:
        raise ValueError("response choice")
    if type(value["message"]) is not str or len(value["message"]) > MAX_MESSAGE:
        raise ValueError("response message")
    return dict(value)


def parse_boolean(value: object, field: str) -> bool:
    if type(value) is not dict or set(value) != {field} or type(value[field]) is not bool:
        raise ValueError("one boolean action required")
    return value[field]


def release_ballots(game: opportunity.RivalWitness, project: str,
                    coalition: tuple[int, ...], *, shocked: bool,
                    x_passed: bool, active: bool) -> tuple[tuple[int, int], ...]:
    """Count constituents who reject the *remaining* project, only after change.

    A release ballot is available to a signer if that district's remaining
    project utility changed. Citizens' votes are synthetic, not LLM actions.
    """
    if not (shocked and x_passed and active):
        return ()
    index = opportunity.INDEX[project]
    return tuple((actor, sum(row[index] < 0 for row in game.after[actor]))
                 for actor in coalition
                 if any(before[index] != after[index]
                        for before, after in zip(game.before[actor], game.after[actor],
                                                 strict=True)))


def resolve(game: opportunity.RivalWitness, arm: str, shocked: bool,
            proposer: int, draft: Offer, responses: tuple[dict[str, object], ...],
            final: Offer, consent: tuple[bool, ...], requested_x: tuple[bool, ...],
            requested_y: tuple[bool, ...]) -> Episode:
    """Deterministically enact requested choices under one announced rule."""
    opportunity.validate(game)
    if arm not in ARMS or type(shocked) is not bool or proposer not in ACTORS:
        raise ValueError("arm, state or proposer")
    for offer in (draft, final):
        if not isinstance(offer, Offer) or offer.second_project not in PROJECTS or (
            len(offer.coalition) not in (0, 4)
            or tuple(sorted(set(offer.coalition))) != offer.coalition
            or any(actor not in ACTORS for actor in offer.coalition)
            or type(offer.message) is not str or len(offer.message) > MAX_MESSAGE
        ):
            raise ValueError("invalid offer")
    if len(responses) != 6 or len(consent) != 7 or len(requested_x) != 7 or len(requested_y) != 7:
        raise ValueError("action inventory")
    if any(type(value) is not bool for value in (*consent, *requested_x, *requested_y)):
        raise ValueError("boolean action")
    if any(type(row) is not dict or set(row) != {"support", "counter_project", "message"}
           for row in responses):
        raise ValueError("response inventory")
    active = bool(final.coalition) and all(consent[actor] for actor in final.coalition)
    executed_x = tuple(requested_x[actor] or (active and actor in final.coalition)
                       for actor in ACTORS)
    x_passed = sum(executed_x) >= 4
    eligible = active and x_passed and all(executed_x[actor] for actor in final.coalition)
    ballots = (release_ballots(game, final.second_project, final.coalition,
                               shocked=shocked, x_passed=x_passed, active=active)
               if arm == "constituent_release" else ())
    released = (tuple(actor for actor, release_yes in ballots if release_yes >= 5)
                if arm == "constituent_release" else ())
    due = set(final.coalition) - set(released) if eligible else set()
    executed_y = tuple(requested_y[actor] or actor in due for actor in ACTORS)
    y_passed = sum(executed_y) >= 4
    table = game.after if shocked else game.before
    index = opportunity.INDEX[final.second_project]
    citizen_utilities = tuple(tuple((row[0] if x_passed else 0) +
                                    (row[index] if y_passed else 0)
                                    for row in district) for district in table)
    return Episode(
        arm=arm, shocked=shocked, proposer=proposer, draft=draft,
        responses=responses, final=final, consent=consent, active=active,
        requested_x=requested_x, executed_x=executed_x, x_passed=x_passed,
        release_ballots=ballots, released=released,
        requested_y=requested_y, executed_y=executed_y, y_passed=y_passed,
        district_utilities=tuple(map(sum, citizen_utilities)),
        citizen_utilities=citizen_utilities,
    )


def episode(game: opportunity.RivalWitness, arm: str, shocked: bool, proposer: int,
            ask: Callable[[int, str, dict[str, object]], object]) -> Episode:
    """Run 29 representative decisions, keeping closed-stage responses sealed.

    The caller owns prompt construction, exact request persistence, billing,
    response decoding, and failed-prefix retention. No inference occurs here.
    """
    opportunity.validate(game)
    if arm not in ARMS or proposer not in ACTORS or type(shocked) is not bool:
        raise ValueError("episode setup")
    public = dict(before=game.before, possible_after_shock=game.after,
                  shock_probability=str(game.shock_probability),
                  proposer=proposer, arm=arm)
    draft = parse_offer(ask(proposer, "draft", dict(public)))
    context = dict(public, draft=draft)
    responses = tuple(parse_response(ask(actor, "response", dict(context)))
                      for actor in ACTORS if actor != proposer)
    final = parse_offer(ask(proposer, "final", dict(context, responses=responses)))
    context = dict(context, responses=responses, final=final)
    consent = tuple(parse_boolean(ask(actor, "consent", dict(context)), "consent")
                    for actor in ACTORS)
    active = bool(final.coalition) and all(consent[actor] for actor in final.coalition)
    first_context = dict(context, consent=consent, contract_active=active)
    requested_x = tuple(parse_boolean(ask(actor, "x_vote", dict(first_context)), "vote")
                        for actor in ACTORS)
    executed_x = tuple(requested_x[actor] or (active and actor in final.coalition)
                       for actor in ACTORS)
    x_passed = sum(executed_x) >= 4
    ballots = (release_ballots(game, final.second_project, final.coalition,
                               shocked=shocked, x_passed=x_passed, active=active)
               if arm == "constituent_release" else ())
    released = (tuple(actor for actor, count in ballots if count >= 5)
                if arm == "constituent_release" else ())
    second_context = dict(first_context, requested_x=requested_x,
                          executed_x=executed_x, x_passed=x_passed,
                          shock_realized=shocked,
                          after=game.after if shocked else game.before,
                          release_ballots=ballots, released=released)
    requested_y = tuple(parse_boolean(ask(actor, "y_vote", dict(second_context)), "vote")
                        for actor in ACTORS)
    return resolve(game, arm, shocked, proposer, draft, responses, final,
                   consent, requested_x, requested_y)
