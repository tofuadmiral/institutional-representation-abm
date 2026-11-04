"""Offline partial identification and private controlled-probe arithmetic.

Continuation values are nuisance variables, not inferred beliefs. Coalition
support is a stated sincere-vote benchmark, not an equilibrium or a commitment.
No new research observations, inference, billing, or frozen-source edits.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from itertools import product
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True

from analysis import paper3_mechanism_audit_v1 as old  # noqa: E402

core, journal = old.core, old.journal
PRIOR = "results/paper3/offline_mechanism_audit_2026_11_01.json"
PRIOR_SHA = "bd3af3169b9ea093c58bf360e18f2e1b3892d5ce50ddbf0292f5ca9f19dd1a7f"
OLD_HELPER_SHA = "79b2101bc041286b229824404f0a3d1b8ada3085162c3e9a9f6630b509a5e691"


def optimal(values, allowed):
    top = max(values[p] for p in allowed)
    return [p for p in allowed if values[p] == top]


def prediction_sets(utility, score, allowed, epsilon):
    """Exact possible argmax sets with max(F)-min(F) <= epsilon.

    A policy p can maximize V+F iff max(V)-V[p] <= epsilon. Necessity follows
    from comparing with a V-maximizer; sufficiency assigns epsilon to p and
    zero to other actions. Both criteria use the same admissible nuisance
    class. A shared endpoint witness also works for actions in the intersection.
    No probability is assigned to nuisance values or reference objectives.
    """
    allowed = list(allowed)
    old.require(
        bool(allowed)
        and len(allowed) == len(set(allowed))
        and len(utility) == len(score)
        and epsilon >= 0,
        "bounded common menu",
    )
    u_top = max(utility[p] for p in allowed)
    s_top = max(score[p] for p in allowed)
    gaps = {
        p: dict(mandate=u_top - utility[p], office=s_top - score[p]) for p in allowed
    }
    u = [p for p in allowed if gaps[p]["mandate"] <= epsilon]
    s = [p for p in allowed if gaps[p]["office"] <= epsilon]
    radius = min(max(gaps[p].values()) for p in allowed)
    return dict(
        epsilon=epsilon,
        allowed=allowed,
        mandate_possible=u,
        office_possible=s,
        overlap=sorted(set(u) & set(s)),
        disjoint=not bool(set(u) & set(s)),
        first_overlap_epsilon=radius,
        gaps=gaps,
        possible_set_interpretation="Existence of a continuation value function, not actual beliefs or optimality.",
    )


def membership(predictions, policy):
    if policy not in predictions["allowed"]:
        return "outside_assumed_menu"
    u, s = (
        policy in predictions["mandate_possible"],
        policy in predictions["office_possible"],
    )
    return (
        "both"
        if u and s
        else "mandate_only"
        if u
        else "office_only"
        if s
        else "neither"
    )


def continuation_witness(utility, score, future, allowed, selected):
    """One legal deterministic future-policy mapping for a single actor.

    Each alternative p leads to a terminal policy q(p). The selected action
    gets this actor's best terminal policy; other actions get its worst. This
    is a support witness, not a forecast or joint fit to all actors' beliefs.
    """
    if selected not in allowed:
        return None
    low = min(range(len(future)), key=lambda q: (future[q], q))
    high = min(range(len(future)), key=lambda q: (-future[q], q))
    transition = {p: high if p == selected else low for p in allowed}
    u = [
        utility[p] + future[transition[p]] if p in transition else 0
        for p in range(len(utility))
    ]
    s = [
        score[p] + future[transition[p]] if p in transition else 0
        for p in range(len(score))
    ]
    return dict(
        terminal_policy_by_first_policy=transition,
        mandate_scores={p: u[p] for p in allowed},
        office_scores={p: s[p] for p in allowed},
        selected_mandate_optimal=selected in optimal(u, allowed),
        selected_office_optimal=selected in optimal(s, allowed),
        claim="Actor-specific existence witness only; not the actual counterfactual continuation.",
    )


def coalition_stress(game, arm):
    """Exact 6x6 shared deterministic continuation scenarios per proposal.

    Every actor evaluates the same terminal policy following passage and the
    same terminal policy following rejection. Enumerating deterministic pairs
    is not an exhaustive characterization of probabilistic common beliefs.
    """
    m = old.menu(game, arm)
    future = [
        [sum(c[q] for c in d) for q in range(len(d[0]))] for d in game.utilities[1]
    ]
    width = len(m[0])
    rows = []
    for p in range(1, width):
        scenarios = []
        for passed, rejected in product(range(width), repeat=2):
            u = [
                m[d][p]["utility"] + future[d][passed] - future[d][rejected]
                for d in core.ACTORS
            ]
            s = [
                m[d][p]["score"]
                - m[d][0]["score"]
                + future[d][passed]
                - future[d][rejected]
                for d in core.ACTORS
            ]
            scenarios.append(
                dict(
                    terminal_if_passed=passed,
                    terminal_if_rejected=rejected,
                    mandate_supporters=[d for d in core.ACTORS if u[d] > 0],
                    office_supporters=[d for d in core.ACTORS if s[d] > 0],
                    mandate_deltas=u,
                    office_deltas=s,
                )
            )
        summary = {}
        for criterion in ("mandate", "office"):
            counts = [len(s[criterion + "_supporters"]) for s in scenarios]
            summary[criterion] = dict(
                minimum_supporters=min(counts),
                maximum_supporters=max(counts),
                passing_scenarios=sum(c >= 4 for c in counts),
                scenarios=len(counts),
                passes_every_enumerated_scenario=all(c >= 4 for c in counts),
            )
        rows.append(dict(policy=p, summary=summary, scenarios=scenarios))
    return rows


def controlled_scores(game, arm, actor, policy):
    """PRIVATE hypothetical probe: three yes peers; fixed terminal status quo."""
    peers = [d for d in core.ACTORS if d != actor]
    peer_votes = {d: i < 3 for i, d in enumerate(peers)}
    results = {}
    offer = core.Offer(policy, "private controlled probe")
    responses = tuple(
        core.Response(False, 0, "private controlled probe") for _ in range(6)
    )
    terminal = core.Offer(0, "private fixed continuation")
    for vote in (False, True):
        ballots = tuple(vote if d == actor else peer_votes[d] for d in core.ACTORS)
        first = core.resolve_term(game, arm, 0, offer, responses, offer, ballots)
        second = core.resolve_term(
            game, arm, 1, terminal, responses, terminal, (False,) * 7, first
        )
        u = (
            first.assessments[actor].district_sum
            + second.assessments[actor].district_sum
        )
        s = u + game.office_value * first.tenure_retained[actor]
        results[vote] = dict(
            enacted=[first.enacted, second.enacted],
            mandate=u,
            office=s,
            retained=first.tenure_retained[actor],
            second_term_utility=second.assessments[actor].district_sum,
        )
    return dict(
        acting_district=actor,
        policy=policy,
        fixed_peer_votes=peer_votes,
        outcomes=results,
        mandate_predictions=[
            v
            for v in (False, True)
            if results[v]["mandate"] == max(r["mandate"] for r in results.values())
        ],
        office_predictions=[
            v
            for v in (False, True)
            if results[v]["office"] == max(r["office"] for r in results.values())
        ],
        original_observation=False,
        model_calls=0,
    )


def probe_catalogue(audited, games):
    aligned = {
        (a["seed"], a["arm"]): games[a["id"]]
        for a in audited
        if a["stratum"] == "aligned"
    }
    probes = []
    for a in audited:
        if a["stratum"] != "conflict" or a["arm"] != "binding_majority":
            continue
        game = games[a["id"]]
        for actor in a["structural_actors"]:
            for policy in actor["passage_reversals"]:
                d = actor["actor"]
                target = controlled_scores(game, a["arm"], d, policy)
                controls = {
                    "aligned": controlled_scores(
                        aligned[a["seed"], a["arm"]], a["arm"], d, policy
                    ),
                    "zero_bonus": controlled_scores(
                        replace(game, office_value=0), a["arm"], d, policy
                    ),
                }
                gain = (
                    target["outcomes"][True]["mandate"]
                    - target["outcomes"][False]["mandate"]
                )
                old.require(
                    target["mandate_predictions"] == [True]
                    and target["office_predictions"] == [False]
                    and 0 < gain < game.office_value,
                    "strict controlled-probe divergence",
                )
                old.require(
                    all(
                        c["mandate_predictions"] == c["office_predictions"] == [True]
                        for c in controls.values()
                    ),
                    "matched negative controls",
                )
                threshold = controlled_scores(
                    replace(game, office_value=gain), a["arm"], d, policy
                )
                old.require(
                    threshold["office_predictions"] == [False, True],
                    "exact bonus threshold tie",
                )
                probes.append(
                    dict(
                        source_assignment=a["id"],
                        seed=a["seed"],
                        actor=d,
                        policy=policy,
                        principal_gain_if_passed=gain,
                        office_bonus=game.office_value,
                        strict_opposition_continuation_margin=min(
                            gain, game.office_value - gain
                        ),
                        target=target,
                        controls=controls,
                        threshold_tie=threshold,
                        design_change="Peers and continuation are fixed in this proposed probe, unlike the original bargaining game.",
                    )
                )
    return probes


def study(name, audited, games):
    result = []
    for a in audited:
        game = games[a["id"]]
        m = old.menu(game, a["arm"])
        future = [
            [sum(c[q] for c in d) for q in range(len(d[0]))] for d in game.utilities[1]
        ]
        menus = {
            "all_enacted_policies": list(range(len(m[0]))),
            "myopic_mandate_support": a["mandate_strict_support_menu"],
            "myopic_office_support": a["office_strict_support_menu"],
        }
        actors = []
        for d in core.ACTORS:
            u, s = [p["utility"] for p in m[d]], [p["score"] for p in m[d]]
            span = max(future[d]) - min(future[d])
            views = {
                key: dict(
                    fixed_continuation=prediction_sets(u, s, allowed, 0),
                    full_menu_continuation_range=prediction_sets(u, s, allowed, span),
                )
                for key, allowed in menus.items()
            }
            actors.append(
                dict(
                    actor=d,
                    first_term_utility=u,
                    first_term_office_score=s,
                    second_term_utility=future[d],
                    continuation_span=span,
                    views=views,
                )
            )
        offers = []
        for o in a["offers"]:
            d, p = o["actor"], o["policy"]
            views = {}
            for key, allowed in menus.items():
                v = actors[d]["views"][key]
                witness = continuation_witness(
                    actors[d]["first_term_utility"],
                    actors[d]["first_term_office_score"],
                    future[d],
                    allowed,
                    p,
                )
                full_label = membership(v["full_menu_continuation_range"], p)
                if full_label == "both":
                    old.require(
                        witness["selected_mandate_optimal"]
                        and witness["selected_office_optimal"],
                        "shared continuation witness",
                    )
                views[key] = dict(
                    fixed_continuation_label=membership(v["fixed_continuation"], p),
                    full_range_label=full_label,
                    fixed_prediction_disjoint=v["fixed_continuation"]["disjoint"],
                    full_range_prediction_disjoint=v["full_menu_continuation_range"][
                        "disjoint"
                    ],
                    first_overlap_epsilon=v["fixed_continuation"][
                        "first_overlap_epsilon"
                    ],
                    witness=witness,
                )
            offers.append(
                dict(
                    logical_id=o["logical_id"],
                    actor=d,
                    stage=o["stage"],
                    policy=p,
                    views=views,
                )
            )
        result.append(
            dict(
                id=a["id"],
                seed=a["seed"],
                stratum=a["stratum"],
                arm=a["arm"],
                actor_menus=actors,
                offers=offers,
                coalition_stress=coalition_stress(game, a["arm"]),
            )
        )
    probes = probe_catalogue(audited, games)
    summaries = {}
    for key in (
        "all_enacted_policies",
        "myopic_mandate_support",
        "myopic_office_support",
    ):
        actor_views = [d["views"][key] for a in result for d in a["actor_menus"]]
        offers = [o["views"][key] for a in result for o in a["offers"]]
        disjoint_offers = [o for o in offers if o["fixed_prediction_disjoint"]]
        summaries[key] = dict(
            actor_menus=len(actor_views),
            offers=len(offers),
            fixed_disjoint_actor_menus=sum(
                v["fixed_continuation"]["disjoint"] for v in actor_views
            ),
            full_range_disjoint_actor_menus=sum(
                v["full_menu_continuation_range"]["disjoint"] for v in actor_views
            ),
            fixed_disjoint_offers=len(disjoint_offers),
            full_range_disjoint_offers=sum(
                o["full_range_prediction_disjoint"] for o in offers
            ),
            full_range_offer_membership=dict(
                Counter(o["full_range_label"] for o in offers)
            ),
            formerly_disjoint_offer_membership=dict(
                Counter(o["full_range_label"] for o in disjoint_offers)
            ),
            positive_overlap_radii=sorted(
                v["fixed_continuation"]["first_overlap_epsilon"]
                for v in actor_views
                if v["fixed_continuation"]["disjoint"]
            ),
        )
    active = [
        p
        for a in result
        if a["stratum"] == "conflict" and a["arm"] == "binding_majority"
        for p in a["coalition_stress"]
    ]
    return dict(
        name=name,
        summary=summaries,
        assignments=result,
        controlled_probe_candidates=probes,
        probe_summary=dict(
            candidates=len(probes),
            matched_control_states=2 * len(probes),
            threshold_tie_states=len(probes),
            all_targets_discriminate=True,
            all_controls_agree=True,
            new_model_calls=0,
        ),
        conflict_binding_coalition_summary={
            criterion: dict(
                policies=len(active),
                passes_every_enumerated_continuation=sum(
                    p["summary"][criterion]["passes_every_enumerated_scenario"]
                    for p in active
                ),
                passes_at_least_one_enumerated_continuation=sum(
                    p["summary"][criterion]["passing_scenarios"] > 0 for p in active
                ),
            )
            for criterion in ("mandate", "office")
        },
    )


def games_from_report(root, pin):
    path = root / "report.json"
    old.require(old.digest(path) == pin, "completed report pin")
    # The complete report's bytes are pinned; decode only the small saved games.
    fields = dict(journal.load(path)["items"])
    games = {}
    for raw in fields["assignments"]["items"]:
        row = dict(raw["items"])
        games[row["id"]] = old.game_from(journal.decode(row["game"]))
    old.require(len(games) == 16, "entire saved inventory")
    return games


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    old.require(
        output.parent == REPO / "results/paper3" and not output.exists(),
        "new sibling analysis output",
    )
    guard = old.install_guard(output)
    old.require(
        old.digest(REPO / PRIOR) == PRIOR_SHA
        and old.digest(Path(old.__file__)) == OLD_HELPER_SHA,
        "prior audit/source pin",
    )
    prior = journal.load(REPO / PRIOR)
    before = old.protected_inventory(REPO)
    old.require(
        before == prior["protected_inventory"],
        "completed experiment/history unchanged since previous audit",
    )
    studies = {
        name: study(
            name,
            prior["studies"][name]["assignments"],
            games_from_report(REPO / "results/paper3" / root, pin),
        )
        for name, (root, pin) in old.STUDIES.items()
    }
    old.require(
        before == old.protected_inventory(REPO)
        and old.digest(REPO / PRIOR) == PRIOR_SHA,
        "protected evidence changed",
    )
    old.require(
        guard == {"network_denials": 1, "process_denials": 1},
        "unexpected network/process attempt",
    )
    result = dict(
        format="paper3-behavioral-identification-v1",
        analysis_date="2026-11-02",
        source_sha256=old.digest(__file__),
        prior_audit_sha256=PRIOR_SHA,
        protected_inventory=before,
        protected_before_after_equal=True,
        guard_selftests=guard,
        exploratory_post_outcome=True,
        new_model_calls=0,
        original_results_changed=False,
        studies=studies,
        limitations=[
            "Idealized maximizing reference objectives; unknown planning, mistakes and objectives remain alternative explanations.",
            "Possible-action sets use unknown continuation functions, not inferred actual expectations.",
            "Actor-specific continuation witnesses do not jointly fit all actors or identify a full-game equilibrium.",
            "Myopic support menus are held fixed while continuation is varied, purely as sensitivity assumptions.",
            "Coalition enumeration covers shared deterministic policy pairs, not all mixed beliefs.",
            "Controlled probes are private counterfactual software states with fixed peers and terminal policy, not model observations.",
            "Bonus sensitivity would concern an explicit stipulated incentive, not intrinsic self-preservation.",
        ],
    )
    with output.open("x") as stream:
        json.dump(old.plain(result), stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            dict(
                output=str(output),
                sha256=old.digest(output),
                summary={
                    k: dict(
                        menus=v["summary"],
                        probes=v["probe_summary"],
                        coalitions=v["conflict_binding_coalition_summary"],
                    )
                    for k, v in studies.items()
                },
            )
        )
    )


if __name__ == "__main__":
    main()
