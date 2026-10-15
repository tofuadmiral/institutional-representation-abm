"""Selected-game person-level readout for institutional information access."""
from __future__ import annotations

from paper3 import direct_ratification as base
from paper3 import direct_ratification_analysis as prior
from paper3 import ratification_disclosure_design as design


def readout(records):
    rows = []
    for item in design.profiles():
        profile = item["profile"]
        finite = prior.bounds(profile)
        arms = {}
        for information in design.INFORMATION:
            by_rule = {}
            for arm in base.ARMS:
                saved = records[(profile["id"], information, arm)]
                if saved["status"] == "completed":
                    by_rule[arm] = dict(status="completed", outcome=saved["outcome"],
                                        events=saved["events"], calls=saved["calls"])
                else:
                    by_rule[arm] = dict(status=saved["status"],
                                        error=saved.get("error"),
                                        finite_missingness_bounds=finite)
            arms[information] = by_rule
        rows.append(dict(profile_id=profile["id"], game_id=item["game_id"],
                         distribution=item["distribution"],
                         favorite=item["favorite"], outsider=item["outsider"],
                         welfare=item["welfare"], arms=arms))
    return dict(profiles=rows, assignments=len(records),
                completed_episodes=sum(value["status"] == "completed"
                                       for value in records.values()),
                limitation="Two theory-selected games, no population sample. Information access is the institutional treatment; certified bulletins change available facts and source authority. Model responses are claims, not verified votes. Calls and citizens are not independent units.")


def discovery_screen(report):
    """Classify possible paths without favoring a desired experimental result."""
    rows = report["profiles"]
    if len(rows) != 4:
        raise ValueError("four game/distribution profiles required")
    coverage = report["completed_episodes"] == 24 and all(
        item["status"] == "completed" for row in rows
        for by_rule in row["arms"].values() for item in by_rule.values())
    public_benchmark = []
    no_veto_controls = []
    veto_advisory_controls = []
    private_veto = []
    certified_veto = []
    per_cell = []
    for row in rows:
        favorite = row["favorite"]
        distribution = row["distribution"]
        for information in design.INFORMATION:
            advisory = row["arms"][information]["advisory_poll"]
            binding = row["arms"][information]["binding_ratification"]
            pair_complete = (advisory["status"] == "completed" and
                             binding["status"] == "completed")
            advisory_favorite = bool(pair_complete and
                                     advisory["outcome"]["final_policy"] == favorite and
                                     advisory["outcome"]["chamber_passed"])
            binding_favorite = bool(pair_complete and
                                    binding["outcome"]["final_policy"] == favorite and
                                    binding["outcome"]["chamber_passed"])
            binding_compromise = bool(pair_complete and
                                      binding["outcome"]["final_policy"] == "C" and
                                      binding["outcome"]["chamber_passed"])
            per_cell.append(dict(game_id=row["game_id"],
                                 distribution=distribution,
                                 information=information,
                                 pair_complete=pair_complete,
                                 advisory_favorite=advisory_favorite,
                                 binding_favorite=binding_favorite,
                                 binding_compromise=binding_compromise))
            if information == "public":
                public_benchmark.append(advisory_favorite and
                                        (binding_compromise if distribution == "veto"
                                         else binding_favorite))
            if distribution == "approve":
                no_veto_controls.append(advisory_favorite and binding_favorite)
            else:
                veto_advisory_controls.append(advisory_favorite)
            if distribution == "veto" and information == "private":
                private_veto.append(advisory_favorite and binding_compromise)
            if distribution == "veto" and information == "certified":
                certified_veto.append(advisory_favorite and binding_compromise)
    interpretable = (coverage and all(public_benchmark) and
                     all(no_veto_controls) and all(veto_advisory_controls))
    if not interpretable:
        path = "not_identified"
    elif all(private_veto) and all(certified_veto):
        path = "voluntary_sufficient_on_selected_games"
    elif not any(private_veto) and all(certified_veto):
        path = "certified_repair_on_selected_games"
    elif not any(certified_veto):
        path = "certified_not_sufficient_on_selected_games"
    else:
        path = "mixed_selected_games"
    return dict(coverage=coverage, public_benchmark=public_benchmark,
                no_veto_controls=no_veto_controls,
                veto_advisory_controls=veto_advisory_controls,
                private_veto_adaptation=private_veto,
                certified_veto_adaptation=certified_veto,
                interpretable_selected_cases=interpretable,
                pathway=path, cells=per_cell,
                caveat="This is a prewritten classification on two hand-built games, not a causal population effect or paper claim. Mandatory certified information changes both available facts and source authority; free-text disclosure must be inspected separately without post-hoc scoring rescue.")
