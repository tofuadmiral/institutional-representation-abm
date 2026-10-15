"""Post-freeze integrity cross-check for the bounded-advocacy pilot.

Recompute every citizen and district outcome directly from saved actions,
without calling the frozen institution's motion/score/screen functions.
This checker was added after launch and cannot amend the primary gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments import paper3_agenda_common_bounded_pilot as runner
from paper3 import agenda_common_design_v2 as design


def independently_score(item, arm, advocacy, sponsorships, votes):
    chair = item["chair"]
    outsiders = list(item["outsiders"])
    favorite = item["favorite"]
    compromises = list(item["compromises"])
    if (arm not in ("sealed", "public_sequential") or
            [entry["actor"] for entry in advocacy] != list(range(7)) or
            [entry["actor"] for entry in sponsorships] !=
            list(item["sponsor_order"]) or
            set(outsiders) != set(range(7)) - {chair} or
            len(votes) != 7 or any(type(vote) is not bool for vote in votes)):
        raise ValueError("invalid saved agent action inventory")
    if any(entry["policy"] not in (*compromises, "none")
           for entry in sponsorships):
        raise ValueError("invalid saved sponsorship")
    counts = {policy: len([entry for entry in sponsorships
                           if entry["policy"] == policy])
              for policy in compromises}
    qualified = [policy for policy in compromises if counts[policy] >= 4]
    if len(qualified) > 1:
        raise ValueError("exclusive filing invariant")
    floor = qualified[0] if qualified else favorite
    passed = len([vote for vote in votes if vote]) >= 4
    enacted = floor if passed else "q"
    district_utility, person_utility, regret = {}, {}, {}
    for district, people in item["profile"]["districts"].items():
        utility = sum(person["utility"].get(enacted, 0)
                      for person in people) if enacted != "q" else 0
        district_utility[district] = utility
        policy_sums = {policy: sum(person["utility"][policy]
                                   for person in people)
                       for policy in (*compromises, favorite)}
        regret[district] = max([0, *policy_sums.values()]) - utility
        for person in people:
            person_utility[person["id"]] = (
                person["utility"][enacted] if enacted != "q" else 0)
    return dict(arm=arm, advocacy=advocacy, sponsorships=sponsorships,
                sponsorship_counts=counts, qualified_motion=qualified,
                floor_policy=floor, requested_votes=votes,
                chamber_passed=passed, enacted_policy=enacted,
                enacted_district_utility=district_utility,
                enacted_citizen_utility=person_utility,
                enacted_total_citizen_utility=sum(person_utility.values()),
                district_menu_regret=regret,
                harmed_citizen_count=sum(value < 0
                                         for value in person_utility.values()),
                controller_changed_actions=0)


def independently_screen(rows):
    split = [row for row in rows if row["structure"] == "split"]
    controls = [row for row in rows if row["structure"] != "split"]
    missing = sum(not row["complete"] for row in split)
    benefit = sum(row["complete"] and row["floor_changed"] and
                  row["welfare_delta"] >= 18 for row in split)
    harm = sum(row["complete"] and row["floor_changed"] and
               row["welfare_delta"] <= -18 for row in split)
    negative = sum(row["complete"] and row["welfare_delta"] < 0
                   for row in split)
    positive = sum(row["complete"] and row["welfare_delta"] > 0
                   for row in split)
    stable = sum(row["control_stable"] for row in controls)
    if stable >= 3 and benefit >= 6 and negative + missing <= 1:
        classification = "selected_case_public_benefit_lead"
    elif stable >= 3 and harm >= 6 and positive + missing <= 1:
        classification = "selected_case_public_harm_lead"
    elif missing > 1 or stable < 3:
        classification = "incomplete_or_control_failed"
    else:
        classification = "no_prespecified_constituent_lead"
    return dict(classification=classification,
                public_benefit_pairs=benefit, public_harm_pairs=harm,
                negative_welfare_pairs=negative,
                positive_welfare_pairs=positive,
                missing_split_pairs=missing, stable_control_pairs=stable)


def audit(root, ledger_root=runner.BUDGET):
    report = runner.audit(root, ledger_root)
    profile_map = {item["profile"]["id"]: item for item in design.profiles()}
    rows = []
    complete_arm_outcomes = 0
    for assignment in runner.assignments():
        item = profile_map[assignment["profile_id"]]
        record = report["records"][assignment["id"]]
        actual = {}
        for arm, episode in record["arms"].items():
            if record["advocacy"] != episode["outcome"]["advocacy"]:
                raise ValueError("arm transcript differs from common transcript")
            independent = independently_score(
                item, arm, record["advocacy"], episode["sponsorships"],
                episode["votes"])
            if independent != episode["outcome"]:
                raise ValueError("independent citizen/policy score differs")
            actual[arm] = independent
            complete_arm_outcomes += 1
        complete = record["status"] == "completed"
        if complete != (set(actual) == {"sealed", "public_sequential"}):
            raise ValueError("paired-profile completeness differs")
        sealed, public = actual.get("sealed"), actual.get("public_sequential")
        rows.append(dict(profile_id=assignment["profile_id"],
                         structure=assignment["structure"], complete=complete,
                         floor_changed=(public["floor_policy"] !=
                                        sealed["floor_policy"] if complete else None),
                         welfare_delta=(public["enacted_total_citizen_utility"] -
                                        sealed["enacted_total_citizen_utility"]
                                        if complete else None),
                         control_stable=(bool(public["qualified_motion"]) and
                                         public["qualified_motion"] ==
                                         sealed["qualified_motion"] and
                                         public["floor_policy"] ==
                                         sealed["floor_policy"] and
                                         public["enacted_policy"] ==
                                         sealed["enacted_policy"]
                                         if complete and
                                         assignment["structure"] != "split"
                                         else False)))
    independent_screen = independently_screen(rows)
    frozen_screen = report["selected_case_readout"]
    if any(frozen_screen[key] != value for key, value in independent_screen.items()):
        raise ValueError("independent decision screen differs")
    return dict(protocol=report["protocol"],
                complete_arm_outcomes=complete_arm_outcomes,
                complete_paired_profiles=report["completed_profiles"],
                independent_screen=independent_screen,
                independent_score_match=True,
                caveat="Post-freeze integrity cross-check, not a new research gate or independent model replication.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.root), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
