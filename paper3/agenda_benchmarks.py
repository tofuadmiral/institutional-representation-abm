"""Exact finite-menu benchmarks, not equilibria or LLM behavior.

Ratification is sincere (strictly positive utility); pairwise votes compare
ratification continuation outcomes, not policies that might fail to enact.
"""
from __future__ import annotations
import random
from paper3 import agenda_rights as game


def policy_ids(profile):
    return sorted(profile["losses"][game.ROLES[0]], key=lambda p: (p != "q", int(p[1:]) if p != "q" else 0))


def continuation(profile, policy):
    return policy if sum(row[policy] > 0 for row in profile["utilities"].values()) >= 4 else profile["status_quo"]


def finish(profile, arm, proposal, amendment):
    utilities = profile["utilities"]
    p, a = continuation(profile, proposal), continuation(profile, amendment)
    ballots = {r: amendment if utilities[r][a] > utilities[r][p] else proposal for r in game.ROLES}
    leader = profile["leader"]
    choice = amendment if utilities[leader][a] > utilities[leader][p] else proposal
    cards = {r: {pid:utilities[r][pid] > 0 for pid in {proposal,amendment}} for r in game.ROLES}
    return game.resolve(profile, arm, proposal, amendment, ballots, choice, cards)


def sponsor_response(profile, arm, proposal):
    ids = policy_ids(profile)
    sponsor = profile["sponsor"]
    outcomes = {a:finish(profile, arm, proposal, a) for a in ids}
    amendment = max(ids, key=lambda a: (profile["utilities"][sponsor][outcomes[a]["outcome"]],
        a == proposal, -ids.index(a)))
    return dict(proposal=proposal, amendment=amendment, resolution=outcomes[amendment])


def benchmark(profile, arm, *, lookahead=True):
    """Explicit self-interested heuristic with publicly fixed tie conventions."""
    ids = policy_ids(profile)
    leader = profile["leader"]
    branches = {p:sponsor_response(profile, arm, p) for p in ids}
    if lookahead:
        proposal = max(ids, key=lambda p: (profile["utilities"][leader][branches[p]["resolution"]["outcome"]],
            profile["utilities"][leader][continuation(profile,p)], -ids.index(p)))
    else:
        proposal = max(ids, key=lambda p: (profile["utilities"][leader][continuation(profile,p)], -ids.index(p)))
    selected = branches[proposal]
    return dict(selected, lookahead=lookahead, arm=arm,
        locked_metrics=game.metrics(profile, proposal),
        enacted_metrics=game.metrics(profile, selected["resolution"]["outcome"]))


def certificate(profile):
    ids = policy_ids(profile)
    u = profile["utilities"]
    viable = [p for p in ids if continuation(profile,p) == p and p != profile["status_quo"]]
    challenges = []
    for p in viable:
        for a in viable:
            supporters = [r for r in game.ROLES if u[r][a] > u[r][p]]
            if len(supporters) >= 4 and u[profile["leader"]][a] < u[profile["leader"]][p] and u[profile["sponsor"]][a] > u[profile["sponsor"]][p]:
                challenges.append(dict(proposal=p, amendment=a, supporters=supporters))
    # The status quo is always an attainable continuation outcome even though
    # strict sincere ratification of q has zero yes votes. A leader can prefer
    # retaining q while a majority/sponsor prefer a viable alternative. The
    # narrower both-ratifiable-policy certificate above deliberately misses this.
    continuation_challenges = []
    for p in ids:
        for a in ids:
            pc, ac = continuation(profile,p), continuation(profile,a)
            supporters = [r for r in game.ROLES if u[r][ac] > u[r][pc]]
            if len(supporters) >= 4 and u[profile["leader"]][ac] < u[profile["leader"]][pc] and u[profile["sponsor"]][ac] > u[profile["sponsor"]][pc]:
                continuation_challenges.append(dict(proposal=p, amendment=a,
                    proposal_continuation=pc, amendment_continuation=ac, supporters=supporters))
    pareto = [p for p in ids if not any(all(u[r][a] >= u[r][p] for r in game.ROLES)
        and any(u[r][a] > u[r][p] for r in game.ROLES) for a in ids)]
    regrets = {p:game.metrics(profile,p)["mean_regret"] for p in ids}
    return dict(viable=viable, sponsor_beneficial_majority_challenges=challenges,
        sponsor_beneficial_continuation_challenges=continuation_challenges,
        majority_graph={p:[a for a in ids if sum(u[r][a] > u[r][p] for r in game.ROLES) >= 4] for p in ids},
        pareto_policies=pareto, min_mean_regret=min(regrets.values()),
        mean_regret_optima=[p for p in ids if regrets[p] == min(regrets.values())],
        lookahead={arm:benchmark(profile,arm) for arm in game.ARMS},
        myopic={arm:benchmark(profile,arm,lookahead=False) for arm in game.ARMS})


def generated_profile(seed):
    """Prospective sampling building block; not a frozen confirmatory sample.

    No rejection/filtering by outcomes, LLM behavior or desired treatment sign.
    Distinct policies and distinct ideals are sampled separately on a 7x7 grid.
    """
    rng = random.Random(seed)
    grid = [(x,y) for x in range(7) for y in range(7)]
    coordinates = rng.sample(grid,8)
    ideals = rng.sample(grid,7)
    weights = [(rng.randint(1,3),rng.randint(1,3)) for _ in game.ROLES]
    leader,sponsor = rng.sample(list(game.ROLES),2)
    order = ["q"]+[f"p{i}" for i in range(1,8)]
    rng.shuffle(order)
    return game.make_profile(f"generated-{seed}",coordinates,ideals,weights,leader,sponsor,order)
