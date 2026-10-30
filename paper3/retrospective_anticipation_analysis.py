"""Prospective selected-case anticipation readout; offline, not a frozen protocol.

Institution/assessment interactions are measured before officeholder handover.
Every assignment and both outcome horizons remain. Thresholds are explicit
prospective inputs, not tuned here; no old analysis or evidence is reinterpreted.
Production must independently reconstruct observations from audited actions.
"""
from dataclasses import asdict
from fractions import Fraction
import json

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design
from paper3 import retrospective_joint_outcome_bounds as outcomes
from paper3.pivot_b_budget import identifier

METRIC = "mean_normalized_district_regret"
WEIGHTS = dict(binding_majority=1, advisory_majority=-1, binding_sum=-1, advisory_sum=1)
STRATA = ("aligned", "conflict")


def _canonical(game):
    return json.dumps(asdict(game), sort_keys=True, allow_nan=False)


def validate(assignments, observations):
    """Exact complete prospective 2-frame x 2-stratum x 4-arm inventory."""
    institution.require(type(assignments) is tuple and len(assignments) == 16,
                        "sixteen prospective assignments required")
    ids = [a["id"] for a in assignments]
    for key in ids:
        identifier(key)
    institution.require(len(set(ids)) == 16 and type(observations) is dict and
                        set(observations) == set(ids), "all assigned observations, no filtering")
    frames = set()
    for assignment in assignments:
        institution.require(type(assignment["seed"]) is int and assignment["seed"] >= 0 and
            type(assignment["seed_base"]) is int and assignment["seed_base"] >= 0 and
            assignment["stratum"] in STRATA and assignment["arm"] in institution.ARMS,
            "typed frame seed, stratum and economic arm")
        institution.validate(assignment["game"])
        frames.add(assignment["seed"])
    institution.require(len(frames) == 2, "two distinct conditional frames")
    base_seeds = []
    for frame in sorted(frames):
        rows = [a for a in assignments if a["seed"] == frame]
        institution.require(len(rows) == 8 and len({(a["stratum"], a["arm"]) for a in rows}) == 8,
                            "every frame/stratum/arm exactly once")
        institution.require(len({a["seed_base"] for a in rows}) == 1, "paired request seeds within frame")
        base_seeds.append(rows[0]["seed_base"])
        games = {}
        for stratum in STRATA:
            group = [a for a in rows if a["stratum"] == stratum]
            institution.require(len({_canonical(a["game"]) for a in group}) == 1,
                                "same game across institutional arms")
            games[stratum] = group[0]["game"]
        a, b = games["aligned"], games["conflict"]
        institution.require(a.game_id != b.game_id and a.chairs == b.chairs and
            a.office_value == b.office_value and a.utilities[1] == b.utilities[1] and
            design.district_sums(a.utilities[0]) == design.district_sums(b.utilities[0]),
            "matched district sums, chairs, office value and continuation")
        disagreement = 0
        for d in institution.ACTORS:
            for p in range(len(a.utilities[0][d][0])):
                aligned = institution.assess(tuple(row[p] for row in a.utilities[0][d]))
                conflict = institution.assess(tuple(row[p] for row in b.utilities[0][d]))
                institution.require(aligned.majority_passed == aligned.sum_passed,
                                    "aligned criterion agreement")
                disagreement += conflict.majority_passed != conflict.sum_passed
        institution.require(disagreement > 0, "conflict criterion disagreement")
    institution.require(not set(range(base_seeds[0], base_seeds[0] + 30)) &
                        set(range(base_seeds[1], base_seeds[1] + 30)), "distinct frame request seeds")
    return tuple(sorted(frames))


def behavior(game, arm, observed):
    """Local choice diagnostics, NOT motives or a full-horizon optimal strategy.

Own ballot counterfactuals hold six actual peer ballots and subsequent district
welfare fixed. Nonpivotal/indifferent votes cannot establish a local tradeoff.
Offers are descriptive entrusted-SUM menu readouts, not sincerity judgments.
"""
    outcomes.first_term_bounds(game, arm, observed)  # Strict economic replay.
    term = observed[0]
    if term is None:
        return dict(observed=False, ballots=tuple(None for _ in institution.ACTORS), offers=None,
            local_tradeoff_opportunities=None, chose_office_over_first_term_sum=None,
            chose_first_term_sum_over_office=None, publication_evidence=False)
    ballots = []
    for actor in institution.ACTORS:
        peers = tuple(v for d, v in enumerate(term.requested) if d != actor)
        policies = {vote: term.final.policy if sum(peers) + vote >= 4 else 0 for vote in (False, True)}
        principal = {vote: sum(row[p] for row in game.utilities[0][actor]) for vote, p in policies.items()}
        office = institution.conditional_ballot_scores(game, arm, actor, term.final.policy, peers)
        p_delta, o_delta = principal[True] - principal[False], office[True] - office[False]
        conflict = p_delta * o_delta < 0
        vote = term.requested[actor]
        ballots.append(dict(actor=actor, requested_vote=vote, executed_vote=term.executed[actor],
            peer_yes_count=sum(peers), locally_pivotal=policies[False] != policies[True],
            counterfactual_enacted=policies, first_term_district_sums=principal,
            office_augmented_conditional_scores=office,
            principal_vote_marginal=p_delta, office_augmented_vote_marginal=o_delta,
            local_tradeoff=conflict,
            chose_office_over_first_term_sum=conflict and vote == (o_delta > 0),
            chose_first_term_sum_over_office=conflict and vote == (p_delta > 0)))
    chair = game.chairs[0]
    authored = [(chair, "draft", term.draft.policy), (chair, "final", term.final.policy)]
    authored += [(actor, "counteroffer", response.counter_policy) for actor, response in
        zip((a for a in institution.ACTORS if a != chair), term.responses, strict=True)]
    offers = []
    for actor, kind, policy in authored:
        metrics = institution.menu_metrics(game, 0, policy)[actor]
        offers.append(dict(actor=actor, kind=kind, policy=policy,
            first_term_district_sum=metrics["assessment"]["district_sum"],
            normalized_district_regret=metrics["normalized_district_regret"]))
    return dict(observed=True, ballots=tuple(ballots), offers=tuple(offers),
        local_tradeoff_opportunities=sum(r["local_tradeoff"] for r in ballots),
        chose_office_over_first_term_sum=sum(r["chose_office_over_first_term_sum"] for r in ballots),
        chose_first_term_sum_over_office=sum(r["chose_first_term_sum_over_office"] for r in ballots),
        publication_evidence=False,
        limitation="Conditional current-term diagnostic only. Later welfare held fixed, "
        "not erased from the entrusted two-term objective. Nonpivotal ballots and "
        "counteroffers do not reveal motives; choosing office here is not proof of "
        "full-horizon mandate abandonment, irrationality or equilibrium play.")


def analyze(assignments, observations, *, minimum_effect, aligned_fraction):
    """Two-sided candidate discovery screen, not publication/population evidence.

For each frame: D_s = (binding_majority - advisory_majority)
                          - (binding_sum - advisory_sum).
Anticipation interaction: I = D_conflict - D_aligned, on first-term regret.
Positive means greater SUM-mandate distortion; negative means less. A same-sign
two-frame lead requires all16first terms, |mean I| >= explicit minimum and
|mean D_aligned| <= explicit fraction * |mean D_conflict|. No p-values, confidence
intervals, optional stopping or outcome-dependent replacement are provided.
Full two-term and all citizen outcomes/missingness remain separate.
"""
    institution.require(type(minimum_effect) is Fraction and 0 < minimum_effect <= 1 and
        type(aligned_fraction) is Fraction and 0 <= aligned_fraction <= 1,
        "explicit exact prospective thresholds")
    frames = validate(assignments, observations)
    rows = []
    for a in assignments:
        observed = observations[a["id"]]
        rows.append(dict(id=a["id"], seed=a["seed"], stratum=a["stratum"], arm=a["arm"],
            first_term=outcomes.first_term_bounds(a["game"], a["arm"], observed),
            two_term=outcomes.bounds(a["game"], a["arm"], observed),
            behavior=behavior(a["game"], a["arm"], observed)))

    def contrast(metric, horizon, *, frame=None, stratum=None):
        selected = [a for a in assignments if (frame is None or a["seed"] == frame)
                    and (stratum is None or a["stratum"] == stratum)]
        count = len(frames) if frame is None else 1
        weighted = tuple((a["id"], a["game"], a["arm"], observations[a["id"]],
            Fraction(WEIGHTS[a["arm"]] * (1 if stratum is not None or a["stratum"] == "conflict" else -1), count))
            for a in selected)
        # Every observation was strictly replayed above. Reuse those local menu
        # readouts for the five metrics/contrasts rather than rebuilding the
        # identical 63-citizen joint support hundreds of times. No saved summary
        # or cross-run cache supplies an observation here.
        evaluated = {row["id"]: row[horizon] for row in rows}
        low = high = Fraction(0)
        contributions = []
        for key, game, arm, observed, weight in weighted:
            result = evaluated[key]
            a, b = result["scalar_bounds"][metric]
            x, y = sorted((weight * a, weight * b))
            low += x
            high += y
            contributions.append(dict(id=key, weight=weight, complete=result["complete"],
                episode_complete=all(t is not None for t in observed), bounds=(a, b)))
        return dict(metric=metric, horizon=horizon, assignments=tuple(contributions), assigned=len(weighted),
            completed=sum(row["complete"] for row in contributions), support_bounds=(low, high),
            zero_excluded=(low > 0 or high < 0), publication_evidence=False,
            caveat="Support bounds alone do not satisfy a scientific gate or identify a population effect.")

    readouts = {horizon: {metric: dict(
        interaction=contrast(metric, horizon),
        aligned=contrast(metric, horizon, stratum="aligned"),
        conflict=contrast(metric, horizon, stratum="conflict"))
        for metric in outcomes.SCALARS} for horizon in ("first_term", "two_term")}
    per_frame = tuple(dict(seed=frame,
        interaction=contrast(METRIC, "first_term", frame=frame),
        aligned=contrast(METRIC, "first_term", frame=frame, stratum="aligned"),
        conflict=contrast(METRIC, "first_term", frame=frame, stratum="conflict")) for frame in frames)
    complete = all(row["first_term"]["complete"] for row in rows)
    screen = dict(status="incomplete_first_term", direction=None, selected_case_lead=False,
        minimum_effect=minimum_effect, aligned_fraction=aligned_fraction,
        same_direction=None, magnitude_met=None, aligned_attenuation_met=None)
    if complete:
        effects = [row["interaction"]["support_bounds"][0] for row in per_frame]
        same = all(v > 0 for v in effects) or all(v < 0 for v in effects)
        primary = readouts["first_term"][METRIC]
        average = primary["interaction"]["support_bounds"][0]
        magnitude = abs(average) >= minimum_effect
        attenuation = abs(primary["aligned"]["support_bounds"][0]) <= (
            aligned_fraction * abs(primary["conflict"]["support_bounds"][0]))
        lead = same and magnitude and attenuation
        screen.update(status=("selected_case_increased_distortion" if average > 0 else
            "selected_case_decreased_distortion") if lead else "no_selected_case_lead",
            direction=("increased_distortion" if average > 0 else "decreased_distortion") if lead else None,
            selected_case_lead=lead, same_direction=same, magnitude_met=magnitude,
            aligned_attenuation_met=attenuation)
    return dict(assignments=tuple(rows), assigned=16,
        first_terms_complete=sum(row["first_term"]["complete"] for row in rows),
        episodes_complete=sum(row["two_term"]["complete"] for row in rows),
        per_frame=per_frame, readouts=readouts, candidate_screen=screen,
        allocation_authorized=False, frozen_protocol=False, publication_evidence=False,
        limitations="Two selected conditional frames/one model are not population evidence. "
        "First-term contrasts precede handover, but do not identify the agent's inner motive. "
        "Assessment binding is an announced instructed office incentive, not intrinsic self-preservation. "
        "Both citizen distributions and incentive alignment change between strata. "
        "Matched seeds do not couple missing potential outcomes; support bounds are not confidence intervals. "
        "Require audited action provenance, independent frozen validation and robustness before publication.")
