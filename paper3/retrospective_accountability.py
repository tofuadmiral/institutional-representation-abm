"""Unfrozen two-term accountability controller; no model or network calls.

The office value is a stipulated game incentive, not an intrinsic LLM motive.
Citizens supply exact utilities and deterministic performance assessments.
The controller never overrides a representative's requested policy ballot.
"""
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass
from fractions import Fraction

ACTORS = tuple(range(7))
ARMS = ("advisory_majority", "advisory_sum", "binding_majority", "binding_sum")
MAX_MESSAGE = 128
Table = tuple[tuple[tuple[int, ...], ...], ...]


def require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class Game:
    game_id: str
    utilities: tuple[Table, Table]
    chairs: tuple[int, int]
    office_value: int


@dataclass(frozen=True)
class Offer:
    policy: int
    message: str


@dataclass(frozen=True)
class Response:
    support: bool
    counter_policy: int
    message: str


@dataclass(frozen=True)
class Assessment:
    citizen_ballots: tuple[bool, ...]
    majority_passed: bool
    district_sum: int
    sum_passed: bool


@dataclass(frozen=True)
class Term:
    game_id: str
    arm: str
    index: int
    occupants: tuple[str, ...]
    draft: Offer
    responses: tuple[Response, ...]
    final: Offer
    requested: tuple[bool, ...]
    executed: tuple[bool, ...]
    proposal_passed: bool
    enacted: int
    citizen_utilities: tuple[tuple[int, ...], ...]
    assessments: tuple[Assessment, ...]
    tenure_retained: tuple[bool, ...] | None
    next_occupants: tuple[str, ...]


@dataclass(frozen=True)
class Episode:
    terms: tuple[Term, Term]
    cumulative_citizen_utilities: tuple[tuple[int, ...], ...]
    cumulative_district_utilities: tuple[int, ...]
    initial_incumbent_scores: tuple[int, ...]
    successor_scores: tuple[int | None, ...]
    calls: int


def validate(game):
    require(isinstance(game, Game), "game type")
    require(type(game.game_id) is str and bool(game.game_id), "game identity")
    require(type(game.office_value) is int and 0 <= game.office_value <= 100,
            "bounded integer office value")
    require(type(game.chairs) is tuple and len(game.chairs) == 2 and
            all(type(actor) is int and actor in ACTORS for actor in game.chairs)
            and game.chairs[0] != game.chairs[1], "two distinct chair districts")
    require(type(game.utilities) is tuple and len(game.utilities) == 2, "two terms")
    width = None
    for table in game.utilities:
        require(type(table) is tuple and len(table) == 7, "seven districts")
        for district in table:
            require(type(district) is tuple and len(district) == 9, "nine citizens")
            for row in district:
                require(type(row) is tuple and 2 <= len(row) <= 8, "finite menu")
                width = len(row) if width is None else width
                require(len(row) == width and row[0] == 0 and
                        all(type(value) is int and -10 <= value <= 10
                            for value in row), "common bounded menu, zero status quo")


def rules(arm):
    require(arm in ARMS, "unknown institution")
    return arm.startswith("binding"), arm.endswith("majority")


def incumbent(actor):
    require(type(actor) is int and actor in ACTORS, "district")
    return f"incumbent-r{actor}"


def successor(actor):
    require(type(actor) is int and actor in ACTORS, "district")
    return f"successor-r{actor}"


def _policy(game, policy):
    require(type(policy) is int and 0 <= policy < len(game.utilities[0][0][0]),
            "policy index")


def _message(value):
    require(type(value) is str and len(value) <= MAX_MESSAGE and
            all((ord(char) >= 32 and not 127 <= ord(char) <= 159) or
                char in "\t\n\r" for char in value), "bounded public text message")


def parse_offer(game, action):
    require(type(action) is dict and set(action) == {"policy", "message"}, "offer fields")
    _policy(game, action["policy"])
    _message(action["message"])
    return Offer(**action)


def parse_response(game, action):
    require(type(action) is dict and set(action) == {"support", "counter_policy", "message"},
            "response fields")
    require(type(action["support"]) is bool, "support boolean")
    _policy(game, action["counter_policy"])
    _message(action["message"])
    return Response(**action)


def parse_vote(action):
    require(type(action) is dict and set(action) == {"vote"} and
            type(action["vote"]) is bool, "one ballot boolean")
    return action["vote"]


def assess(values):
    require(type(values) is tuple and len(values) == 9 and
            all(type(value) is int and -10 <= value <= 10 for value in values),
            "nine bounded citizen outcomes")
    ballots = tuple(value >= 0 for value in values)
    total = sum(values)
    return Assessment(ballots, sum(ballots) >= 5, total, total >= 0)


def menu_metrics(game, term, policy):
    validate(game)
    require(type(term) is int and term in (0, 1), "term index")
    _policy(game, policy)
    results = []
    for district in game.utilities[term]:
        sums = tuple(map(sum, zip(*district, strict=True)))
        width = max(sums) - min(sums)
        values = tuple(row[policy] for row in district)
        results.append(dict(
            assessment=asdict(assess(values)),
            normalized_district_regret=(Fraction(max(sums) - sums[policy], width)
                                        if width else Fraction(0)),
            citizen_utilities=values,
            citizen_menu_regret=tuple(max(row) - row[policy] for row in district),
            harmed_citizens=sum(value < 0 for value in values),
            positive_citizens=sum(value > 0 for value in values)))
    return tuple(results)


def resolve_term(game, arm, term, draft, responses, final, votes, previous=None):
    validate(game)
    binding, majority = rules(arm)
    require(type(term) is int and term in (0, 1), "term index")
    require(isinstance(draft, Offer) and isinstance(final, Offer), "offer type")
    for offer in (draft, final):
        parse_offer(game, asdict(offer))
    require(type(responses) is tuple and len(responses) == 6 and
            all(isinstance(response, Response) for response in responses), "six responses")
    for response in responses:
        parse_response(game, asdict(response))
    require(type(votes) is tuple and len(votes) == 7 and
            all(type(value) is bool for value in votes), "seven ballots")
    if term == 0:
        require(previous is None, "initial term cannot have predecessor")
        occupants = tuple(map(incumbent, ACTORS))
    else:
        require(isinstance(previous, Term) and previous.index == 0 and
                previous.game_id == game.game_id and previous.arm == arm,
                "matching first-term predecessor required")
        replayed = resolve_term(game, arm, 0, previous.draft, previous.responses,
                                previous.final, previous.requested)
        require(previous == replayed, "predecessor must match exact first-term replay")
        occupants = previous.next_occupants
    passed = sum(votes) >= 4
    enacted = final.policy if passed else 0
    citizens = tuple(tuple(row[enacted] for row in district)
                     for district in game.utilities[term])
    assessments = tuple(map(assess, citizens))
    retained = (tuple(not binding or (item.majority_passed if majority else item.sum_passed)
                      for item in assessments) if term == 0 else None)
    next_occupants = (tuple(occupants[actor] if retained[actor] else successor(actor)
                           for actor in ACTORS) if retained is not None else occupants)
    return Term(game.game_id, arm, term, occupants, draft, responses, final,
                votes, votes, passed, enacted, citizens, assessments, retained, next_occupants)


def conditional_ballot_scores(game, arm, actor, policy, other_votes):
    """Exact first-term score conditional on six fixed peer ballots.

    Later district utility is held constant/omitted. These are not optimal
    bargaining strategies or a prediction of the peers' endogenous choices.
    """
    validate(game)
    binding, majority = rules(arm)
    incumbent(actor)
    _policy(game, policy)
    require(type(other_votes) is tuple and len(other_votes) == 6 and
            all(type(value) is bool for value in other_votes), "six fixed peer ballots")
    result = {}
    for vote in (False, True):
        enacted = policy if sum(other_votes) + vote >= 4 else 0
        assessment = assess(tuple(row[enacted] for row in game.utilities[0][actor]))
        retained = not binding or (assessment.majority_passed if majority
                                  else assessment.sum_passed)
        result[vote] = assessment.district_sum + game.office_value * retained
    return result


def episode(game: Game, arm: str, ask: Callable, on_term: Callable | None = None):
    """Thirty decisions; sealed stages and actual officeholder handover.

    ask(district, identity, term, stage, context, global_index) supplies a
    decoded action. Exceptions propagate; the caller must retain paid/prefix
    records and must not repair, replace or restart a failed episode.
    """
    validate(game)
    rules(arm)
    terms = []
    index = 0
    for term in (0, 1):
        previous = terms[0] if terms else None
        occupants = (previous.next_occupants if previous else tuple(map(incumbent, ACTORS)))
        base = dict(game_id=game.game_id, arm=arm, term=term, utilities=game.utilities,
                    office_value=game.office_value, chairs=game.chairs, occupants=occupants,
                    history=[asdict(item) for item in terms],
                    menu_assessments=tuple(tuple(asdict(assess(tuple(row[policy]
                        for row in district))) for policy in range(len(district[0])))
                        for district in game.utilities[term]))

        def decision(actor, stage, context):
            nonlocal index
            value = ask(actor, occupants[actor], term, stage, deepcopy(context), index)
            index += 1
            return value

        chair = game.chairs[term]
        draft = parse_offer(game, decision(chair, "draft", base))
        shared = dict(base, draft=asdict(draft))
        responses = tuple(parse_response(game, decision(actor, "response", shared))
                          for actor in ACTORS if actor != chair)
        shared = dict(shared, responses=tuple(asdict(item) for item in responses))
        final = parse_offer(game, decision(chair, "final", shared))
        shared = dict(shared, final=asdict(final))
        votes = tuple(parse_vote(decision(actor, "vote", shared)) for actor in ACTORS)
        terms.append(resolve_term(game, arm, term, draft, responses, final, votes, previous))
        if on_term is not None:
            on_term(terms[-1])
    require(index == 30, "thirty actions required")
    first, second = terms
    citizens = tuple(tuple(left + right for left, right in zip(a, b, strict=True))
                     for a, b in zip(first.citizen_utilities, second.citizen_utilities, strict=True))
    totals = tuple(map(sum, citizens))
    scores = tuple(total + game.office_value * first.tenure_retained[actor]
                   for actor, total in enumerate(totals))
    successors = tuple(second.assessments[actor].district_sum
                       if second.occupants[actor] == successor(actor) else None for actor in ACTORS)
    return Episode((first, second), citizens, totals, scores, successors, index)
