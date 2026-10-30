"""Independent, offline arithmetic check for the ratification-population run.

This file was added while the frozen discovery was live. It is NOT one of the
53 frozen protocol sources, does not alter their score or decision rules, and
cannot rescue a failed prewritten behavioral gate. It recomputes controller
arithmetic from saved profile rows and requested actions without calling the
institution's score function. Use only after the run is terminal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from experiments import paper3_ratification_population_discovery as frozen


def _require(test, message):
    if not test:
        raise ValueError(message)


def independent_outcome(profile, arm, events):
    """Derive passage and every citizen/district value from raw actions."""
    _require(arm in ("advisory_poll", "binding_ratification"), "invalid arm")
    _require([event.get("type") for event in events] ==
             ["draft", "responses", "final", "vote"], "event sequence")
    policy = events[2]["action"]["policy"]
    _require(policy in ("X", "Y", "C"), "final policy")
    ballots = events[3]["requested"]
    _require(len(ballots) == 7 and all(type(ballot) is bool for ballot in ballots),
             "requested ballots")
    chamber_passed = sum(ballots) >= 4
    districts = profile["districts"]
    _require(set(districts) == {f"r{actor}" for actor in range(7)},
             "district inventory")
    counts = {}
    district_final = {}
    citizen_final = {}
    for district, people in districts.items():
        _require(len(people) == 9, "citizen count")
        counts[district] = 0
        district_final[district] = 0
        for person in people:
            citizen_id = person["id"]
            _require(citizen_id not in citizen_final, "duplicate citizen")
            value = person["utility"][policy]
            _require(type(value) is int, "noninteger utility")
            citizen_final[citizen_id] = value
            district_final[district] += value
            counts[district] += value > 0
    approvals = {district: count >= 5 for district, count in counts.items()}
    referendum_passed = all(approvals.values())
    enacted = chamber_passed and (
        arm == "advisory_poll" or referendum_passed)
    citizen_enacted = {person: value if enacted else 0
                       for person, value in citizen_final.items()}
    district_enacted = {district: value if enacted else 0
                        for district, value in district_final.items()}
    return dict(
        final_policy=policy,
        chamber_passed=chamber_passed,
        requested_ballots=ballots,
        referendum=dict(yes_counts=counts, district_approvals=approvals,
                        approved=referendum_passed),
        enacted_policy=policy if enacted else "q",
        final_proposal_district_utility=district_final,
        enacted_district_utility=district_enacted,
        final_proposal_citizen_utility=citizen_final,
        enacted_citizen_utility=citizen_enacted,
        final_proposal_total_citizen_utility=sum(citizen_final.values()),
        enacted_total_citizen_utility=sum(citizen_enacted.values()),
        controller_changed_ballots=0,
    )


def independent_readout(assignments, profiles, episodes):
    """Retain every assigned cell, independently checking complete outcomes."""
    _require(set(episodes) == {assignment["id"] for assignment in assignments},
             "episode inventory")
    checked = {}
    cells = {}
    for assignment in assignments:
        episode_id = assignment["id"]
        episode = episodes[episode_id]
        _require(episode["id"] == episode_id, "episode identity")
        key = (assignment["game_id"], assignment["distribution"],
               assignment["arm"])
        _require(key not in cells, "duplicate game cell")
        if episode["status"] == "completed":
            _require(episode.get("calls") == 16, "complete episode call count")
            expected = independent_outcome(
                profiles[assignment["profile_id"]], assignment["arm"],
                episode["events"])
            _require(episode["outcome"] == expected,
                     "independent outcome mismatch: " + episode_id)
            checked[episode_id] = expected
            cells[key] = int(expected["final_policy"] != assignment["favorite"])
        else:
            _require(episode["status"] in
                     ("failed", "not_started", "instrument_error"),
                     "unknown terminal episode status")
            cells[key] = None
    games = {}
    for game_id in sorted({assignment["game_id"] for assignment in assignments}):
        terms = (("veto", "binding_ratification", 1),
                 ("veto", "advisory_poll", -1),
                 ("approve", "binding_ratification", -1),
                 ("approve", "advisory_poll", 1))
        lower = upper = 0
        values = {}
        for distribution, arm, coefficient in terms:
            value = cells[(game_id, distribution, arm)]
            values[f"{distribution}|{arm}"] = value
            if value is None:
                lower += min(0, coefficient)
                upper += max(0, coefficient)
            else:
                lower += coefficient * value
                upper += coefficient * value
        complete = all(value is not None for value in values.values())
        games[game_id] = dict(cells=values, complete=complete,
                              interaction=lower if complete else None,
                              interaction_bound=[lower, upper])
    return dict(assigned_episodes=len(assignments),
                complete_episodes=len(checked),
                independent_games=len(games),
                complete_games=sum(item["complete"] for item in games.values()),
                games=games,
                verified_outcomes=checked)


def audit_run(root):
    """Compare independent arithmetic/primary interactions with frozen audit."""
    root = Path(root)
    manifest, protocol = frozen.verify(root)
    terminal = root / "sessions/terminal.json"
    _require(terminal.is_file(), "run not terminal")
    original = frozen.audit(root)
    assignments = manifest["protocol"]["assignments"]
    profiles = frozen.profiles()
    episodes = {assignment["id"]: json.loads(
        (root / "episodes" / (assignment["id"] + ".json")).read_text())
        for assignment in assignments}
    independent = independent_readout(assignments, profiles, episodes)
    _require(independent["complete_episodes"] == original["completed_episodes"],
             "complete episode count mismatch")
    _require(independent["complete_games"] ==
             original["readout"]["complete_games"],
             "complete game count mismatch")
    for published_game in original["readout"]["games"]:
        game_id = published_game["game_id"]
        computed = independent["games"][game_id]
        _require(computed["interaction_bound"] ==
                 published_game["interaction_bound"],
                 "primary bound mismatch")
        _require(computed["interaction"] == published_game["interaction"],
                 "primary interaction mismatch")
        for cell_key, value in computed["cells"].items():
            _require(value == published_game["cells"][cell_key]
                     ["alternative_proposed"], "primary cell mismatch")
    payload = json.dumps(independent, sort_keys=True, separators=(",", ":"))
    return dict(protocol=protocol,
                assigned_episodes=independent["assigned_episodes"],
                complete_episodes=independent["complete_episodes"],
                independent_games=independent["independent_games"],
                complete_games=independent["complete_games"],
                independent_report_sha256=hashlib.sha256(payload.encode()).hexdigest(),
                exact_arithmetic_and_primary_match=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_run(args.run), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
