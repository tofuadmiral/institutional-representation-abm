import unittest

from paper3 import direct_ratification as game
from paper3 import direct_ratification_analysis as analysis
from paper3 import direct_ratification_pilot_design as design


class PilotDesignTests(unittest.TestCase):
    def test_schedule_exact_repeats_and_fresh_request_seeds(self):
        rows = design.profiles()
        self.assertEqual(len(rows), 8)
        assignments = design.assignments()
        self.assertEqual(len(assignments), 16)
        self.assertEqual(sum(row["intended_calls"] for row in assignments), 256)
        seeds = [row["seed_base"] + i for row in assignments for i in range(16)]
        self.assertEqual(len(set(seeds)), 256)
        for first, second in zip(rows[::2], rows[1::2]):
            self.assertEqual(first["profile"]["districts"],
                             second["profile"]["districts"])
            self.assertEqual(first["profile"]["proposer"],
                             second["profile"]["proposer"])
            for arm in game.ARMS:
                actor = first["profile"]["proposer"]
                a = game.messages(first["profile"], arm, actor, "draft", [])
                b = game.messages(second["profile"], arm, actor, "draft", [])
                self.assertEqual(a, b)

    def test_conflict_is_not_a_pareto_dominance_fixture(self):
        profile = design.profiles()[0]["profile"]
        totals = game.district_totals(profile)
        self.assertTrue(any(row["X"] > row["C"] for row in totals.values()))
        self.assertTrue(any(row["Y"] > row["C"] for row in totals.values()))
        self.assertTrue(any(row["C"] > row["X"] and row["C"] > row["Y"]
                            for row in totals.values()))
        self.assertEqual(sum(game.poll(profile, "X")["district_approvals"].values()), 6)
        self.assertEqual(sum(game.poll(profile, "Y")["district_approvals"].values()), 6)

    def test_missingness_is_exact_finite_menu_not_independent_citizen_extremes(self):
        row = design.profiles()[0]
        bounds = analysis.bounds(row["profile"])
        self.assertEqual(bounds["possible_policies"], ["q", "X", "Y", "C"])
        exact_total = [0] + [sum(c["utility"][policy]
                                 for district in row["profile"]["districts"].values()
                                 for c in district)
                             for policy in game.POLICIES]
        self.assertEqual(bounds["total_citizen_utility"],
                         dict(min=min(exact_total), max=max(exact_total)))
        self.assertEqual(len(bounds["citizens"]), 63)

    def test_all_statuses_and_mechanical_only_distinguished(self):
        rows = design.profiles()
        records = {}
        for row in rows:
            p = row["profile"]
            events = [dict(type="draft", actor=p["proposer"],
                           action=dict(policy="X", message="")),
                      dict(type="responses", responses=[]),
                      dict(type="final", actor=p["proposer"],
                           action=dict(policy="X", message="")),
                      dict(type="vote", requested=[True] * 7)]
            for arm in game.ARMS:
                records[(p["id"], arm)] = dict(status="completed", events=events,
                                               outcome=game.score(p, arm, events), calls=16)
        first = rows[0]["profile"]["id"]
        result = analysis.readout(rows, records)
        self.assertEqual(result["completed_pairs"], 8)
        self.assertTrue(result["profiles"][0]["contrast"]["mechanical_only"])
        self.assertFalse(result["profiles"][4]["contrast"]["mechanical_only"])
        records[(first, "binding_ratification")] = dict(status="failed", error="invalid")
        result = analysis.readout(rows, records)
        self.assertEqual(result["completed_pairs"], 7)
        self.assertEqual(result["completed_episodes"], 15)
        self.assertEqual(result["profiles"][0]["arms"]["binding_ratification"]["status"],
                         "failed")
        self.assertFalse(result["profiles"][0]["contrast"]["completed"])
        self.assertIn("finite_missingness_bounds", result["profiles"][0]["contrast"])

    def test_prospective_triage_rejects_mechanical_only(self):
        rows = design.profiles()
        records = {}
        for row in rows:
            p = row["profile"]
            for arm in game.ARMS:
                chosen = "X" if row["family"] == "outsider_harm_A_agenda" else (
                    "Y" if row["family"] == "outsider_harm_B_agenda" else "C")
                events = [dict(type="draft", actor=p["proposer"],
                               action=dict(policy=chosen, message="")),
                          dict(type="responses", responses=[]),
                          dict(type="final", actor=p["proposer"],
                               action=dict(policy=chosen, message="")),
                          dict(type="vote", requested=[True] * 7)]
                records[(p["id"], arm)] = dict(status="completed", events=events,
                                               outcome=game.score(p, arm, events), calls=16)
        first = analysis.readout(rows, records)
        self.assertFalse(analysis.discovery_triage(first)["triage"])
        for row in rows:
            if row["family"].startswith("outsider_harm"):
                p = row["profile"]
                events = records[(p["id"], "binding_ratification")]["events"]
                events[2] = dict(type="final", actor=p["proposer"],
                                 action=dict(policy="C", message=""))
                records[(p["id"], "binding_ratification")]["outcome"] = game.score(
                    p, "binding_ratification", events)
        second = analysis.readout(rows, records)
        self.assertTrue(analysis.discovery_triage(second)["triage"])


if __name__ == "__main__":
    unittest.main()
