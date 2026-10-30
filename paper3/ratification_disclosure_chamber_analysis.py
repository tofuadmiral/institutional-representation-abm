"""Prewritten hard-game disclosure readout; descriptive, not a paper test."""
from __future__ import annotations

from paper3 import direct_ratification as base
from paper3 import direct_ratification_analysis as prior
from paper3 import ratification_disclosure_chamber_design as design


def readout(records):
    rows = []
    for item in design.profiles():
        profile = item["profile"]
        finite = prior.bounds(profile)
        arms = {}
        for information in ("private", "certified", "public"):
            selected = base.ARMS if information != "public" else (
                ("binding_ratification",) if item["distribution"] == "veto" else ())
            if not selected:
                continue
            by_rule = {}
            for arm in selected:
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
                         favorite_support=item["favorite_support"],
                         compromise_support=item["compromise_support"],
                         welfare=item["welfare"], arms=arms))
    return dict(profiles=rows, assignments=len(records),
                completed_episodes=sum(value["status"] == "completed"
                                       for value in records.values()),
                limitation="Six pre-generated conditional synthetic games from one template, one model route. Public information is sampled only in binding-veto calibration cells; it cannot estimate a full public interaction. Calls, districts and citizens are not independent games.")


def _success(item, policy):
    return bool(item["status"] == "completed" and
                item["outcome"]["final_policy"] == policy and
                item["outcome"]["chamber_passed"] and
                item["outcome"]["enacted_policy"] == policy)


def discovery_screen(report):
    rows = report["profiles"]
    if len(rows) != 12:
        raise ValueError("six paired games required")
    coverage = report["assignments"] == 54 and report["completed_episodes"] == 54
    no_veto_controls = []
    advisory_veto_controls = []
    public_calibration = []
    private_veto = []
    certified_veto = []
    per_game = []
    for game_id in range(6):
        approve = next(row for row in rows if row["game_id"] == game_id and
                       row["distribution"] == "approve")
        veto = next(row for row in rows if row["game_id"] == game_id and
                    row["distribution"] == "veto")
        favorite = approve["favorite"]
        comparisons = {}
        for information in ("private", "certified"):
            approve_advisory = approve["arms"][information]["advisory_poll"]
            approve_binding = approve["arms"][information]["binding_ratification"]
            veto_advisory = veto["arms"][information]["advisory_poll"]
            veto_binding = veto["arms"][information]["binding_ratification"]
            no_veto = (_success(approve_advisory, favorite) and
                       _success(approve_binding, favorite))
            advisory_veto = _success(veto_advisory, favorite)
            success = _success(veto_binding, "C")
            no_veto_controls.append(no_veto)
            advisory_veto_controls.append(advisory_veto)
            if information == "private":
                private_veto.append(success)
            else:
                certified_veto.append(success)
            comparisons[information] = dict(
                no_veto_control=no_veto,
                advisory_veto_control=advisory_veto,
                binding_veto_success=success,
                binding_veto_final_policy=(veto_binding["outcome"]["final_policy"]
                                           if veto_binding["status"] == "completed"
                                           else None),
                binding_veto_chamber_passed=(veto_binding["outcome"]["chamber_passed"]
                                             if veto_binding["status"] == "completed"
                                             else None))
        public = veto["arms"]["public"]["binding_ratification"]
        calibrated = _success(public, "C")
        public_calibration.append(calibrated)
        per_game.append(dict(game_id=game_id, favorite=favorite,
                             favorite_support_count=len(approve["favorite_support"]),
                             compromise_support_count=len(approve["compromise_support"]),
                             welfare=approve["welfare"], public_calibration=calibrated,
                             comparisons=comparisons))
    interpretable = (coverage and all(no_veto_controls) and
                     all(advisory_veto_controls) and all(public_calibration))
    certified_gain = [game_id for game_id, (private, certified) in
                      enumerate(zip(private_veto, certified_veto, strict=True))
                      if certified and not private]
    certified_loss = [game_id for game_id, (private, certified) in
                      enumerate(zip(private_veto, certified_veto, strict=True))
                      if private and not certified]
    if not interpretable:
        pathway = "not_identified"
    elif certified_gain or certified_loss:
        pathway = "discordant_information_on_hard_games"
    elif all(private_veto):
        pathway = "both_sufficient_on_hard_games"
    elif not any(private_veto):
        pathway = "neither_sufficient_on_hard_games"
    else:
        pathway = "same_outcomes_mixed_games"
    return dict(coverage=coverage, no_veto_controls=no_veto_controls,
                advisory_veto_controls=advisory_veto_controls,
                public_calibration=public_calibration,
                private_veto_success=private_veto,
                certified_veto_success=certified_veto,
                certified_gain_game_ids=certified_gain,
                certified_loss_game_ids=certified_loss,
                interpretable_selected_cases=interpretable,
                pathway=pathway, games=per_game,
                caveat="Outcome cells are full pre-vote proposal plus chamber plus referendum enactment; proposal and chamber failures must be separated. Six conditional draws from one generator are not population evidence. Public calibration lacks its own full factorial controls. A certified count changes available facts and provenance; different request seeds mean the trace is not a matched-response mediation estimate.")
