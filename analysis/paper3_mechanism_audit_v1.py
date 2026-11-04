"""Post-outcome, offline mechanism diagnosis of two completed Paper 3 studies.

All conditional incentives hold future district utility fixed. Nothing here is
an equilibrium prediction, a motive classifier, or a replacement frozen screen.
The command checks saved economic actions, never performs inference or billing.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from fractions import Fraction
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True

from paper3 import retrospective_accountability as core  # noqa: E402
from paper3 import retrospective_anticipation_analysis as science  # noqa: E402
from paper3 import retrospective_episode_journal as journal  # noqa: E402

STUDIES = {
    "discovery": ("pivot_b_graceful_continuation_v1",
                  "cce94f8ed48d86898522f918e16904b2815ce83c966d79b87652be248636df19"),
    "validation": ("pivot_b_independent_validation_v1",
                   "e92c710c772f57fc11190aa88e9c33947eafab45c0a69321e77d0289d24213f0"),
}
AMENDMENT = ("results/paper3/pivot_b_independent_validation_v1/"
             "reasoning_timeout_amendment_v1/manifest.json")
PROTOCOL = "89f5dabecbaf3ba3d7bac299fb836aeb967bb241e5679d332756a2cec435e851"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def plain(value):
    if isinstance(value, Fraction):
        return {"exact": str(value), "decimal": float(value)}
    if hasattr(value, "__dataclass_fields__"):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def game_from(value):
    return core.Game(value["game_id"], tuple(tuple(tuple(tuple(row) for row in district)
        for district in table) for table in value["utilities"]),
        tuple(value["chairs"]), value["office_value"])


def menu(game, arm, term=0):
    """Enacted outcomes, not choice values under endogenous peer responses."""
    core.validate(game)
    binding, majority = core.rules(arm)
    result = []
    for actor in core.ACTORS:
        policies = []
        for policy in range(len(game.utilities[term][actor][0])):
            a = core.assess(tuple(row[policy] for row in game.utilities[term][actor]))
            retained = not binding or (a.majority_passed if majority else a.sum_passed)
            # Terminal acting-identity scores differ from SUM only by past constants.
            bonus = game.office_value * retained if term == 0 else 0
            policies.append(dict(policy=policy, utility=a.district_sum,
                majority_passed=a.majority_passed, sum_passed=a.sum_passed,
                retained=retained if term == 0 else None, score=a.district_sum + bonus))
        result.append(policies)
    return result


def maxima(values, allowed=None):
    allowed = list(range(len(values))) if allowed is None else list(allowed)
    best = max(values[p] for p in allowed)
    return [p for p in allowed if values[p] == best]


def preferences(policies, allowed=None):
    u = [p["utility"] for p in policies]
    s = [p["score"] for p in policies]
    allowed = list(range(len(u))) if allowed is None else list(allowed)
    mandate, office = maxima(u, allowed), maxima(s, allowed)
    reversals = []
    for a, b in combinations(allowed, 2):
        if (u[a] - u[b]) * (s[a] - s[b]) < 0:
            m, o = (a, b) if u[a] > u[b] else (b, a)
            reversals.append(dict(mandate_policy=m, office_policy=o,
                district_utility_sacrificed=u[m] - u[o], office_score_gained=s[o] - s[m]))
    return dict(mandate_optima=mandate, office_optima=office,
                disjoint_optima=not bool(set(mandate) & set(office)), strict_reversals=reversals)


def passable(m, criterion):
    return [p for p in range(len(m[0])) if p == 0 or
            sum(row[p][criterion] > row[0][criterion] for row in m) >= 4]


def choice(policies, selected, allowed=None):
    prefs = preferences(policies, allowed)
    u = selected in prefs["mandate_optima"]
    s = selected in prefs["office_optima"]
    return dict(**prefs, selected=selected,
        optimum_membership="both" if u and s else "mandate_only" if u else "office_only" if s else "neither",
        office_favoring_witnesses=[r for r in prefs["strict_reversals"] if r["office_policy"] == selected],
        mandate_favoring_witnesses=[r for r in prefs["strict_reversals"] if r["mandate_policy"] == selected])


def audit_assignment(assignment, row):
    game, arm = assignment["game"], assignment["arm"]
    logs = row["logicals"]
    require(len(logs) == 30 and row["status"] == "completed", "complete thirty-action assignment")

    def saved(actor, identity, term, stage, context, index):
        record = logs[index]
        require((record["actor"], record["identity"], record["term"], record["stage"], record["index"])
                == (actor, identity, term, stage, index), "saved actor/identity/term/stage/index")
        require(record["status"] == "recorded_valid" and record["classification"]["instrument_safe"],
                "saved accepted action")
        return record["classification"]["execution"]["executed_action"]

    replay = core.episode(game, arm, saved)
    require(replay == row["outcome"] and tuple(row["terms"]) == replay.terms,
            "entire two-term economic action replay")
    first = replay.terms[0]
    m = menu(game, arm)
    ppass, spass = passable(m, "utility"), passable(m, "score")
    actors = []
    for actor, policies in enumerate(m):
        diffs = [p for p in policies[1:] if
                 p["utility"] * (p["score"] - policies[0]["score"]) < 0]
        actors.append(dict(actor=actor, policies=policies,
            assessment_disagreements=[p["policy"] for p in policies[1:]
                                      if p["majority_passed"] != p["sum_passed"]],
            passage_reversals=[p["policy"] for p in diffs], **preferences(policies)))

    offers, supports = [], []
    for record in logs[:15]:
        actor, stage = record["actor"], record["stage"]
        action = record["classification"]["execution"]["executed_action"]
        if stage in ("draft", "final", "response"):
            policy = action["counter_policy" if stage == "response" else "policy"]
            offers.append(dict(actor=actor, stage=stage, policy=policy, message=action["message"],
                logical_id=record["id"], full_menu=choice(m[actor], policy),
                score_support_menu=choice(m[actor], policy, spass),
                mandate_support_menu=choice(m[actor], policy, ppass)))
        if stage == "response":
            p = first.draft.policy
            ud = m[actor][p]["utility"]
            sd = m[actor][p]["score"] - m[actor][0]["score"]
            supports.append(dict(actor=actor, draft_policy=p, support=action["support"],
                utility_delta=ud, score_delta=sd, strict_reference_disagreement=ud * sd < 0,
                matches_mandate_reference=action["support"] == (ud > 0),
                matches_office_reference=action["support"] == (sd > 0),
                caveat="Nonbinding support; not a decisive ballot or expected-outcome valuation."))

    local = science.behavior(game, arm, replay.terms)
    votes = []
    for actor, ballot in enumerate(local["ballots"]):
        p = first.final.policy
        ud, sd = m[actor][p]["utility"], m[actor][p]["score"] - m[actor][0]["score"]
        votes.append(dict(**ballot, passage_reference_disagreement=ud * sd < 0,
            passage_utility_delta=ud, passage_score_delta=sd,
            matches_mandate_reference=first.requested[actor] == (ud > 0),
            matches_office_reference=first.requested[actor] == (sd > 0)))
    return dict(id=assignment["id"], seed=assignment["seed"], stratum=assignment["stratum"], arm=arm,
        chair=game.chairs[0], office_value=game.office_value, structural_actors=actors,
        mandate_strict_support_menu=ppass, office_strict_support_menu=spass,
        offers=offers, supports=supports, ballots=votes,
        realized=dict(draft_policy=first.draft.policy, final_policy=first.final.policy,
            enacted=[t.enacted for t in replay.terms], yes_count=sum(first.requested),
            final_equals_draft=first.final.policy == first.draft.policy,
            final_matches_counteroffer=any(r.counter_policy == first.final.policy for r in first.responses),
            cumulative_district_utilities=replay.cumulative_district_utilities,
            cumulative_citizen_utilities=replay.cumulative_citizen_utilities,
            initial_incumbent_scores=replay.initial_incumbent_scores),
        economic_replay_equal=True)


def reference(game, arm, objective, coalition_filter):
    """Sincere myopic scripts, common lower-ID tie rule; no equilibrium claim.

    The optional filter assumes every peer uses the same conditional criterion
    and supports strictly positive gain over rejection. It ignores bargaining
    history, continuation responses, and public persuasion. Neither script is
    the full-horizon mandate optimum or an inference about LLM preferences.
    """
    require(objective in ("utility", "score"), "known script objective")
    choices = []
    menus = [menu(game, arm, t) for t in (0, 1)]

    def ask(actor, identity, term, stage, context, index):
        m = menus[term]
        allowed = passable(m, objective) if coalition_filter else range(len(m[actor]))
        preferred = min(maxima([p[objective] for p in m[actor]], allowed))
        if stage in ("draft", "final"):
            action = dict(policy=preferred, message="offline conditional reference")
        elif stage == "response":
            p = context["draft"]["policy"]
            action = dict(support=m[actor][p][objective] > m[actor][0][objective],
                          counter_policy=preferred, message="offline conditional reference")
        else:
            p = context["final"]["policy"]
            action = dict(vote=m[actor][p][objective] > m[actor][0][objective])
        choices.append(dict(index=index, actor=actor, term=term, stage=stage, action=action))
        return action

    return core.episode(game, arm, ask), choices


def script_readout(assignments, objective, coalition_filter, original_screen):
    observations, rows, actions = {}, [], {}
    for a in assignments:
        ep, choices = reference(a["game"], a["arm"], objective, coalition_filter)
        observations[a["id"]] = ep.terms
        actions[a["id"]] = choices
        rows.append(dict(id=a["id"], enacted=[t.enacted for t in ep.terms],
                         district_utilities=ep.cumulative_district_utilities,
                         incumbent_scores=ep.initial_incumbent_scores))
    readout = science.analyze(assignments, observations,
        minimum_effect=original_screen["minimum_effect"], aligned_fraction=original_screen["aligned_fraction"])
    return dict(objective=objective, coalition_filter=coalition_filter,
        tie_rule="lowest policy ID; vote/support no on exact ties",
        candidate_screen=readout["candidate_screen"],
        first_term_interaction=readout["readouts"]["first_term"][science.METRIC]["interaction"]["support_bounds"][0],
        two_term_interaction=readout["readouts"]["two_term"][science.METRIC]["interaction"]["support_bounds"][0],
        per_frame=[dict(seed=r["seed"], **{k: r[k]["support_bounds"][0]
                    for k in ("aligned", "conflict", "interaction")}) for r in readout["per_frame"]],
        assignments=rows, actions=actions, model_calls=0,
        interpretation="Synthetic reference behavior only; not a measured model effect or full-game strategy.")


def summarize(rows):
    actors = [a for r in rows for a in r["structural_actors"]]
    ballots = [b for r in rows for b in r["ballots"]]
    offers = [o for r in rows for o in r["offers"]]
    supports = [s for r in rows for s in r["supports"]]
    disjoint = [o for o in offers if o["full_menu"]["disjoint_optima"]]
    sensitive_votes = [b for b in ballots if b["passage_reference_disagreement"]]
    return dict(episodes=len(rows), actors=len(actors),
        policy_cells_excluding_status_quo=sum(len(a["policies"])-1 for a in actors),
        assessment_disagreement_cells=sum(len(a["assessment_disagreements"]) for a in actors),
        strict_passage_reversal_cells=sum(len(a["passage_reversals"]) for a in actors),
        actors_with_any_menu_reversal=sum(bool(a["strict_reversals"]) for a in actors),
        actors_with_disjoint_menu_optima=sum(a["disjoint_optima"] for a in actors),
        first_term_ballots=len(ballots), pivotal_ballots=sum(b["locally_pivotal"] for b in ballots),
        local_tradeoff_opportunities=sum(b["local_tradeoff"] for b in ballots),
        passage_sensitive_observed_ballots=len(sensitive_votes),
        passage_sensitive_office_matching_votes=sum(b["matches_office_reference"] for b in sensitive_votes),
        passage_sensitive_mandate_matching_votes=sum(b["matches_mandate_reference"] for b in sensitive_votes),
        first_term_offers=len(offers), offers_by_stage=dict(Counter(o["stage"] for o in offers)),
        offers_with_disjoint_full_menu_optima=len(disjoint),
        disjoint_offer_membership=dict(Counter(o["full_menu"]["optimum_membership"] for o in disjoint)),
        offers_with_office_favoring_pairwise_witness=sum(bool(o["full_menu"]["office_favoring_witnesses"]) for o in offers),
        first_term_responses=len(supports),
        sensitive_support_statements=sum(s["strict_reference_disagreement"] for s in supports),
        sensitive_office_matching_support=sum(s["strict_reference_disagreement"] and s["matches_office_reference"] for s in supports),
        yes_count_distribution=dict(Counter(r["realized"]["yes_count"] for r in rows)))


def study(name, root, expected_sha):
    path = root / "report.json"
    require(digest(path) == expected_sha, "completed report pin changed")
    report = journal.decode(journal.load(path))
    require(len(report["assignments"]) == 16, "full assignment inventory")
    metadata = {a["id"]: a for a in report["analysis"]["assignments"]}
    assignments, audited = [], []
    for row in report["assignments"]:
        meta = metadata[row["id"]]
        a = dict(id=row["id"], game=game_from(row["game"]), arm=row["arm"],
                 seed=meta["seed"], stratum=meta["stratum"], seed_base=row["seed_base"])
        assignments.append(a)
        checked = audit_assignment(a, row)
        require(sum(b["local_tradeoff"] for b in checked["ballots"])
                == meta["behavior"]["local_tradeoff_opportunities"], "original diagnostic mismatch")
        audited.append(checked)
    assignments = tuple(assignments)
    scripts = [script_readout(assignments, objective, coalition, report["analysis"]["candidate_screen"])
               for coalition in (False, True) for objective in ("utility", "score")]
    comparison = []
    for i in (0, 2):
        a, b = scripts[i:i+2]
        different = []
        for key in a["actions"]:
            for x, y in zip(a["actions"][key], b["actions"][key], strict=True):
                if x["action"] != y["action"]:
                    different.append(dict(assignment=key, index=x["index"], term=x["term"], stage=x["stage"]))
        comparison.append(dict(coalition_filter=a["coalition_filter"], differing_actions=different,
            differing_first_term_enactments=sum(x["enacted"][0] != y["enacted"][0]
                for x, y in zip(a["assignments"], b["assignments"], strict=True))))
    return dict(name=name, report_sha256=expected_sha, original_screen=report["analysis"]["candidate_screen"],
        original_validation=report.get("validation"), summary=summarize(audited),
        by_stratum_arm={f"{s}/{a}": summarize([r for r in audited if r["stratum"] == s and r["arm"] == a])
            for s in science.STRATA for a in core.ARMS},
        assignments=audited, reference_scripts=scripts, reference_comparisons=comparison)


def protected_inventory(repo):
    manifest = journal.load(repo / AMENDMENT)
    require(hashlib.sha256(journal.canonical(manifest).encode()).hexdigest() == PROTOCOL,
            "amendment protocol pin")
    require(len(manifest["sources"]) == 215 and len(manifest["prior_files"]) == 58
            and len(manifest["prior_entries"]) == 7408, "historical inventory sizes")
    expected = dict(manifest["sources"])
    expected.update(manifest["prior_files"])
    expected.update({"results/paper3/pivot_b_budget/entries/" + k: v
                     for k, v in manifest["prior_entries"].items()})
    for name, sha in expected.items():
        require(digest(repo / name) == sha, "frozen evidence changed: " + name)
    paths = {repo / name for name in expected}
    for root_name, _ in STUDIES.values():
        paths.update((repo / "results/paper3" / root_name).rglob("*.json"))
    paths.update((repo / "results/paper3/pivot_b_budget").rglob("*.json"))
    for name in ("validation_final_audit_2026_10_29.json", "validation_stage_closeout_2026_10_29.json",
                 "validation_portable_replay_2026_10_29.json"):
        paths.add(repo / "results/paper3" / name)
    paths.update((repo / "paper3/data" / (root + "_complete.zip")) for root, _ in STUDIES.values())
    require(all(p.is_file() and not p.is_symlink() for p in paths), "regular protected evidence")
    return {p.relative_to(repo).as_posix(): digest(p) for p in sorted(paths)}


def install_guard(output):
    """Deny network, child processes, and all writes except the new result file."""
    state = {"network_denials": 0, "process_denials": 0}

    def guard(event, args):
        if event.startswith("socket."):
            state["network_denials"] += 1
            raise RuntimeError("offline network denial")
        if event in ("subprocess.Popen", "os.system", "os.posix_spawn", "os.fork", "os.exec"):
            state["process_denials"] += 1
            raise RuntimeError("offline process denial")
        if event == "open":
            name, mode, flags = args
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            if writing and (not isinstance(name, (str, bytes)) or Path(name).resolve() != output):
                raise RuntimeError("protected offline write denial")
    sys.addaudithook(guard)
    import socket
    import subprocess
    for action in (lambda: socket.socket(), lambda: subprocess.Popen([sys.executable, "-c", "pass"])):
        try:
            action()
        except RuntimeError:
            pass
        else:
            raise AssertionError("offline guard selftest failed")
    require(state == {"network_denials": 1, "process_denials": 1}, "guard selftests")
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    require(output.parent.is_dir() and not output.exists(), "new output in existing directory required")
    guard = install_guard(output)
    before = protected_inventory(REPO)
    studies = {name: study(name, REPO / "results/paper3" / root, sha)
               for name, (root, sha) in STUDIES.items()}
    after = protected_inventory(REPO)
    require(before == after, "protected sources, data, archives, or ledger changed")
    require(guard == {"network_denials": 1, "process_denials": 1}, "unexpected network/process attempt")
    result = dict(format="paper3-offline-mechanism-audit-v1", analysis_date="2026-11-01",
        exploratory_post_outcome=True, new_model_calls=0, frozen_scientific_findings_changed=False,
        source_sha256=digest(__file__), protected_inventory=before,
        protected_before_after_equal=True, guard_selftests=guard, studies=studies,
        assumptions=["Conditional score comparisons hold later district utility fixed.",
            "Policy-menu comparisons assume enactment; they do not predict acceptance.",
            "Strict support menus assume sincere conditional responses by every peer.",
            "Response support and counteroffers are nonbinding communication.",
            "Local ballot counterfactuals hold six realized peer ballots fixed.",
            "Scripts are myopic with a common explicit tie rule, not two-term optimal strategies.",
            "Observed matching does not establish motive, collusion, or causal message influence.",
            "Counts reuse games across arms; they are not independent statistical samples."])
    with output.open("x") as stream:
        json.dump(plain(result), stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(output), "sha256": digest(output),
        "protected_files": len(before), "summary": {k: v["summary"] for k, v in studies.items()}}))


if __name__ == "__main__":
    main()
