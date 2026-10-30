"""Unfrozen opportunity-conditioned electorates; pure offline generation.

Sampling is constructive and conditional, not population-representative.
Matched pairs preserve every district/policy sum; citizen distributions change.
Conditional passage scores hold subsequent district welfare fixed, not a
solution to the two-term bargaining game or a prediction of LLM behavior.
"""
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from itertools import product
from random import Random

from paper3 import retrospective_accountability as institution


@lru_cache(maxsize=None)
def _completions(positive, negative, total):
    if positive + negative == 0:
        return int(total == 0)
    if total < positive - 10 * negative or total > 10 * positive - negative:
        return 0
    values = range(1, 11) if positive else range(-10, 0)
    p, n = (positive - 1, negative) if positive else (positive, negative - 1)
    return sum(_completions(p, n, total - value) for value in values)


def citizen_column(rng, total, aligned):
    """Exact sum and approval-sign relation; nonzero bounded citizen values.

    Choose an attainable sign count uniformly, then a labeled value vector
    uniformly conditional on that count and sum, then shuffle citizens.
    This explicitly specified distribution is not uniform over all electorates.
    """
    institution.require(type(total) is int and 0 < abs(total) <= 32, "nonzero sum range")
    institution.require(type(aligned) is bool, "alignment boolean")
    majority_positive = (total > 0) == aligned
    counts = range(5, 7) if majority_positive else range(3, 5)
    possible = [p for p in counts if _completions(p, 9 - p, total)]
    institution.require(bool(possible), "attainable sign count")
    positive = rng.choice(possible)
    negative = 9 - positive
    remaining = total
    values = []
    while positive + negative:
        candidates = list(range(1, 11) if positive else range(-10, 0))
        p, n = (positive - 1, negative) if positive else (positive, negative - 1)
        weights = [_completions(p, n, remaining - value) for value in candidates]
        pick = rng.randrange(sum(weights))
        for value, weight in zip(candidates, weights, strict=True):
            if pick < weight:
                break
            pick -= weight
        values.append(value)
        remaining -= value
        positive, negative = p, n
    rng.shuffle(values)
    return tuple(values)


def _table(rng, sums, exposed):
    districts = []
    for actor in institution.ACTORS:
        columns = [(0,) * 9] + [citizen_column(rng, total, (actor, policy) not in exposed)
                                for policy, total in enumerate(sums[actor][1:], 1)]
        districts.append(tuple(tuple(row) for row in zip(*columns, strict=True)))
    return tuple(districts)


def district_sums(table):
    return tuple(tuple(map(sum, zip(*district, strict=True))) for district in table)


def conditional_menu(game, arm):
    """Strict pivotal support and menu regret, with future welfare fixed.

    Each district compares enactment with rejection/status quo. Four strictly
    positive differences make a policy passable under this benchmark, not an
    equilibrium-selected outcome. Zero differences are retained separately.
    """
    institution.validate(game)
    institution.rules(arm)
    rows = []
    for policy in range(len(game.utilities[0][0][0])):
        scores = [institution.conditional_ballot_scores(
            game, arm, actor, policy, (True,) * 3 + (False,) * 3)
                  for actor in institution.ACTORS]
        differences = tuple(row[True] - row[False] for row in scores)
        support = tuple(actor for actor, delta in enumerate(differences) if delta > 0)
        indifferent = tuple(actor for actor, delta in enumerate(differences) if delta == 0)
        regret = sum((row["normalized_district_regret"] for row in
                      institution.menu_metrics(game, 0, policy)), Fraction(0)) / 7
        rows.append(dict(policy=policy, score_differences=differences, support=support,
                         indifferent=indifferent, strictly_passable=len(support) >= 4,
                         mean_regret=regret))
    feasible = [row for row in rows if row["policy"] == 0 or row["strictly_passable"]]
    return dict(policies=tuple(rows), best_feasible_regret=min(row["mean_regret"]
                                                           for row in feasible))


def restricted_vote_equilibria(game, arm, policy):
    """All weak pure ballot equilibria, fixed proposal and future welfare.

    No claim about proposal, bargaining or the full two-term game. In particular,
    five or more yes ballots make every unilateral ballot outcome-irrelevant.
    Such a passing equilibrium exists even if all seven oppose passage versus
    rejection. This is why the sincere-support benchmark is not an equilibrium
    selection prediction or a constraint on attainable institutional outcomes.
    """
    institution.validate(game)
    institution._policy(game, policy)
    differences = conditional_menu(game, arm)["policies"][policy]["score_differences"]
    equilibria = []
    for votes in product((False, True), repeat=7):
        yes = sum(votes)
        if any((yes == 4 and votes[actor] and delta < 0) or
               (yes == 3 and not votes[actor] and delta > 0)
               for actor, delta in enumerate(differences)):
            continue
        equilibria.append(votes)
    return tuple(equilibria)


@dataclass(frozen=True)
class Pair:
    seed: int
    draws: int
    aligned: institution.Game
    conflict: institution.Game
    exposed: tuple[tuple[int, int], ...]


def opportunity(pair):
    """Structural checks only. No outcome-dependent selection or model input."""
    left, right = pair.aligned, pair.conflict
    institution.validate(left)
    institution.validate(right)
    institution.require(left.office_value == right.office_value and
                        left.chairs == right.chairs and
                        left.utilities[1] == right.utilities[1], "matched continuation")
    institution.require(district_sums(left.utilities[0]) == district_sums(right.utilities[0]),
                        "matched district policy sums")
    observed = []
    for actor in institution.ACTORS:
        for policy in range(1, len(left.utilities[0][0][0])):
            a = institution.assess(tuple(row[policy] for row in left.utilities[0][actor]))
            b = institution.assess(tuple(row[policy] for row in right.utilities[0][actor]))
            institution.require(a.majority_passed == a.sum_passed, "aligned comparator")
            if b.majority_passed != b.sum_passed:
                observed.append((actor, policy))
    institution.require(tuple(observed) == pair.exposed, "exact exposure inventory")
    baseline = conditional_menu(left, "advisory_sum")
    aligned_binding = conditional_menu(left, "binding_majority")
    conflicted = conditional_menu(right, "binding_majority")
    passable = [row for row in baseline["policies"] if row["strictly_passable"]]
    changed = sum(a["score_differences"] != b["score_differences"] for a, b in
                  zip(aligned_binding["policies"], conflicted["policies"], strict=True))
    changed_support = sum(a["support"] != b["support"] for a, b in
                          zip(aligned_binding["policies"], conflicted["policies"], strict=True))
    return dict(
        distinct_baseline_coalitions=len({row["support"] for row in passable}),
        baseline_passable=len(passable),
        majority_binding_passable=sum(row["strictly_passable"]
                                     for row in conflicted["policies"]),
        changed_policy_scores=changed,
        changed_policy_support=changed_support,
        conditional_frontier_gap=(conflicted["best_feasible_regret"] -
                                  baseline["best_feasible_regret"]))


def generate(seed, *, office_value=24, max_draws=2000):
    """Five non-status-quo options; selected opportunities, not frozen cases.

    Require competing sum-support coalitions and at least one surviving
    majority-accountable option. A positive conditional frontier gap provides
    an incentive opportunity, not a required or observed behavioral effect.
    Rejection happens solely on exogenous tables, before any model output.
    """
    institution.require(type(seed) is int and seed >= 0, "seed")
    institution.require(type(max_draws) is int and max_draws > 0, "draw bound")
    institution.require(type(office_value) is int and 0 <= office_value <= 100, "office value")
    rng = Random(seed)
    for draw in range(1, max_draws + 1):
        sums = [[0] for _ in institution.ACTORS]
        for _ in range(5):
            coalition = set(rng.sample(institution.ACTORS, rng.choice((4, 5))))
            for actor in institution.ACTORS:
                total = rng.choice([n for n in range(8, 33) if n != office_value])
                sums[actor].append(total if actor in coalition else -total)
        exposed = tuple((actor, policy) for actor in institution.ACTORS
                        for policy in range(1, 6) if rng.random() < 0.45)
        # Independent tables can rearrange utilities even in unexposed cells.
        # Advisory arms estimate these distribution effects rather than assume zero.
        aligned = _table(rng, sums, ())
        conflict = _table(rng, sums, exposed)
        future_sums = [[0] + [rng.choice((-1, 1)) * rng.randint(8, 32)
                              for _ in range(5)] for _ in institution.ACTORS]
        future = _table(rng, future_sums, ())
        chairs = tuple(rng.sample(institution.ACTORS, 2))
        left = institution.Game(f"offline-{seed}-aligned", (aligned, future), chairs, office_value)
        right = institution.Game(f"offline-{seed}-conflict", (conflict, future), chairs, office_value)
        pair = Pair(seed, draw, left, right, exposed)
        checks = opportunity(pair)
        if (checks["distinct_baseline_coalitions"] >= 2 and
                checks["baseline_passable"] >= 2 and
                checks["majority_binding_passable"] >= 1 and
                checks["changed_policy_support"] >= 2 and
                checks["conditional_frontier_gap"] > 0):
            return pair
    raise ValueError("no conditioned opportunity within draw bound")
