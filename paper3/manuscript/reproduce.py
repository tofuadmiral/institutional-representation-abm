"""Reconstruct the reported offers, ballots and primary paired comparisons offline."""
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import numpy as np
from scipy.stats import beta, binomtest

DATA = Path(__file__).resolve().parent / "data"


def records(study):
    path = DATA / f"{study}.jsonl.gz"
    metadata = json.loads((DATA / "provenance.json").read_text())[study]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata["export_sha256"]
    with gzip.open(path, "rt", encoding="utf-8") as file:
        rows = [json.loads(line) for line in file]
    assert len(rows) == len({r["id"] for r in rows}) == metadata["actions"]
    return rows


def csv_rows(name):
    with (DATA / name).open(newline="") as file:
        return list(csv.DictReader(file))


def prompt(row):
    return json.loads(row["request"]["messages"][1]["content"])


def intervals(successes, n):
    """Simultaneous bounds for the positive and negative discordance rates."""
    tail = 0.05 / 4
    lower = beta.ppf(tail, successes, n - successes + 1) if successes else 0
    upper = beta.ppf(1-tail, successes + 1, n - successes) if successes < n else 1
    return lower, upper


def qwen_games(study):
    grouped = defaultdict(dict)
    for record in records(study):
        if record["phase"] == "main":
            grouped[record["case_id"]][record["arm"], record["step"], record["actor"]] = record
    assert len(grouped) == 60
    rows = []
    for case, actions in sorted(grouped.items()):
        assert len(actions) == 9
        request, = (r for r in actions.values() if r["step"] == "request")
        state = prompt(request)
        plans = state["constituency_payoffs"]
        fallback = state["status_quo"]
        proposer, claimant = state["agenda"], state["claimant"]
        requested = request["action"]["plan"]
        gains = {p: sum(u[a] > plans[fallback][a] for a in u) for p, u in plans.items()}
        assert sorted(gains.values()) == [0, 2, 3, 3]
        if study == "matched-reminder":
            compromises = [p for p in plans if gains[p] == 3]
            assert requested == max(compromises, key=lambda p: plans[p][claimant])
        offers = {}
        for arm in ("ordinary", "counts"):
            offer = actions[arm, "offer", proposer]
            offers[arm] = prompt(offer)
            assert offers[arm]["observed_request"] == request["action"]
            plan = offer["action"]["plan"]
            votes = {}
            for actor in sorted(plans[fallback]):
                ballot = actions[arm, "ballot", actor]
                ballot_state = prompt(ballot)
                assert ballot_state["observed_offer"] == offer["action"]
                assert "coalition_information" not in ballot_state
                votes[actor] = ballot["action"]["vote"]
            implemented = plan if set(votes.values()) == {"yes"} else fallback
            harmed = plans[plan][claimant] < plans[fallback][claimant]
            rows.append(dict(
                study=study, case=case, arm=arm, agenda=proposer, claimant=claimant,
                requested=requested, requested_gainers=gains[requested], offered=plan,
                offered_gainers=gains[plan], claimant_harmed_if_passed=int(harmed),
                claimant_vote=votes[claimant], yes=sum(v == "yes" for v in votes.values()),
                fallback=fallback, implemented=implemented, enacted_all_gain=int(gains[implemented] == 3),
            ))
        info = offers["counts"]["coalition_information"]
        assert info.pop("strict_gainers_per_plan") == gains and info["required_yes"] == 3
        if study == "counts-and-reminder":
            del offers["counts"]["coalition_information"]
        assert offers["counts"] == offers["ordinary"]
    return rows


def qwen_summary(rows):
    cells = defaultdict(dict)
    for row in rows:
        cells[row["case"]][row["arm"]] = row["enacted_all_gain"]
    n = len(cells)
    paired = Counter((v["ordinary"], v["counts"]) for v in cells.values())
    up, down = paired[0, 1], paired[1, 0]
    positive, negative = intervals(up, n), intervals(down, n)
    return dict(
        matched_games=n, without_counts=paired[1, 1] + down, with_counts=paired[1, 1] + up,
        counts_only=up, control_only=down, both=paired[1, 1], neither=paired[0, 0],
        difference_pp=100*(up-down)/n,
        interval_pp=[100*(positive[0]-negative[1]), 100*(positive[1]-negative[0])],
        paired_p=binomtest(up, up+down, 0.5).pvalue if up+down else 1.0,
        vetoes_of_harmful=sum(r["claimant_harmed_if_passed"] and r["claimant_vote"]=="no" for r in rows),
        mutual_gain_offers=sum(r["offered_gainers"]==3 for r in rows),
        requests_for_mutual_gain=sum(r["arm"]=="ordinary" and r["requested_gainers"]==3 for r in rows),
        requests_adopted_with_counts=sum(r["arm"]=="counts" and r["implemented"]==r["requested"] for r in rows),
    )


def gpt_outcomes():
    calls = defaultdict(dict)
    for r in records("voting-rules"):
        calls[r["case_id"], r["rule"], r["mode"]][r["step"], r["agent"]] = r
    branches = csv_rows("voting-rules.csv")
    assert len(branches) == 72
    for branch in branches:
        roles = calls[branch["case_id"], branch["rule"], branch["mode"]]
        offer, = (r for r in roles.values() if r["step"] == "revision")
        state = prompt(offer)
        plan = offer["action"]["plan"]
        votes = [r["action"]["vote"] for r in roles.values() if r["step"] == "ballot"]
        assert len(votes) == 3
        adopted = plan if votes.count("yes") >= state["required_yes"] else state["status_quo"]
        assert adopted == branch["implemented"] and plan == branch["final_offer"]
        baseline = state["utilities"][state["status_quo"]]
        u = state["utilities"][adopted]
        assert int(any(x < y for x, y in zip(u, baseline))) == int(branch["harmful_exclusion"])
        assert min(u)/100 == float(branch["minimum_utility"])
    return branches


def verify_replay():
    by_id = {r["id"]: r for r in records("offer-replay")}
    rows = csv_rows("offer-replay.csv")
    assert len(rows) == len(by_id) == 144
    for row in rows:
        call = by_id[row["replay"]]
        plan = call["action"]["plan"]
        state = prompt(call)
        table, sq = state["utilities"], state["status_quo"]
        actor = state["utility_columns"].index(row["agenda"])
        feasible = [p for p, u in table.items() if p == sq or
                    sum(x > y for x, y in zip(u, table[sq])) >= state["required_yes"]]
        correct = plan in feasible and table[plan][actor] == max(table[p][actor] for p in feasible)
        assert plan == row["replay_offer"] and int(row["frontier"]) == correct
    return rows


def paired_contrast(games, ticks_per_point, comparisons):
    """Exact game bootstrap percentiles and Bonferroni-adjusted sign-flip test.

    Each integer is one game's paired difference before division by the
    number of within-game observations. Convolution enumerates resampled
    totals without materializing all n**n bootstrap samples.
    """
    ticks = np.asarray(games, dtype=int)
    n = len(ticks)
    offset = ticks.min()
    mass = np.bincount(ticks - offset) / n
    distribution = np.array([1.0])
    for _ in range(n):
        distribution = np.convolve(distribution, mass)
    quantiles = np.searchsorted(np.cumsum(distribution), [0.025, 0.975])
    interval = (quantiles / n + offset) / ticks_per_point

    totals = np.array([0])
    for value in ticks[ticks != 0]:
        totals = np.concatenate((totals + value, totals - value))
    p = np.mean(abs(totals) >= abs(ticks.sum()))
    return dict(estimate=ticks.mean() / ticks_per_point, interval=interval.tolist(),
                adjusted_p=min(1.0, comparisons * p))


def gpt_comparisons(branches, replay):
    # Each game has two observations per rule and two per message condition.
    cases = defaultdict(dict)
    for row in branches:
        cases[row["case_id"]][row["rule"], row["mode"]] = row
    assert len(cases) == 18 and all(len(case) == 4 for case in cases.values())
    for field, contrast in [
        ("harmful_exclusion", "rule"),
        ("minimum_utility", "rule"),
        ("proposer_concession", "mode"),
    ]:
        differences = []
        for case in cases.values():
            total = 0
            for (rule, mode), row in case.items():
                positive = rule == "unanimity" if contrast == "rule" else mode == "full_messages"
                points = 100 * Decimal(row[field])
                assert points == int(points)
                total += points if positive else -points
            differences.append(int(total))
        print(field, json.dumps(paired_contrast(differences, 2, 4)))

    # Two rules crossed with two label conditions give four observations per aid arm.
    cases = defaultdict(dict)
    for row in replay:
        cases[row["case"]][row["rule"], row["arm"]] = int(row["frontier"])
    assert len(cases) == 18 and all(len(case) == 8 for case in cases.values())
    differences = [
        sum(score if arm in ("both", "coalition") else -score
            for (_, arm), score in case.items()) * 100
        for case in cases.values()
    ]
    print("coalition aid (pp)", json.dumps(paired_contrast(differences, 4, 3)))


def main():
    branches = gpt_outcomes()
    for rule in ("majority", "unanimity"):
        sample = [b for b in branches if b["rule"] == rule and b["family"] == "conflict"]
        print(rule, "conflict agreements", sum(int(b["agreement"]) for b in sample), "/", len(sample))
    gpt_comparisons(branches, verify_replay())
    all_games = []
    for study in ("counts-and-reminder", "matched-reminder"):
        rows = qwen_games(study)
        print(study, json.dumps(qwen_summary(rows), indent=2))
        all_games.extend(rows)
    # The reader-facing CSV must agree with the independently reconstructed actions.
    assert csv_rows("qwen-games.csv") == [{k: str(v) for k, v in row.items()} for row in all_games]


if __name__ == "__main__":
    main()
