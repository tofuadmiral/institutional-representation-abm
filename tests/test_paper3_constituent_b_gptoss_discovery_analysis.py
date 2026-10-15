"""Offline checks of the seven-profile discovery estimand and missingness."""
import unittest

from paper3 import coalition_contracts as game
from paper3 import constituent_b_gptoss_discovery_analysis as analysis
from paper3 import constituent_b_gptoss_discovery_design as design
from paper3 import constituent_b_institution as institution


class DiscoveryAnalysisTests(unittest.TestCase):
    @staticmethod
    def _records(completed=False):
        records = {}
        for item in design.profiles():
            prepared = item["prepared"]
            profile_id = prepared["contract_profile"]["id"]
            for arm in game.ARMS:
                if not completed:
                    row = dict(status="not_started")
                else:
                    def ask(actor, stage, messages, index):
                        if stage in ("draft", "response", "final"):
                            value = dict(projects=dict(A="A0", B="B0"), first="A",
                                         coalition=[0, 1, 3, 4], message="fabricated")
                            if stage == "response":
                                value["support"] = True
                        elif stage == "consent":
                            value = dict(consent=True)
                        else:
                            value = dict(vote=True)
                        import json
                        return json.dumps(value)
                    row = dict(status="completed", **institution.episode(prepared, arm, ask))
                records[(profile_id, arm)] = row
        return records

    def test_assignment_inventory_is_distinct_and_balanced(self):
        profiles = design.profiles()
        assignments = design.assignments()
        self.assertEqual(len(profiles), 7)
        self.assertEqual(len(assignments), 21)
        self.assertEqual([row["phase"] for row in assignments], [1] * 3 + [2] * 18)
        self.assertEqual({row["arm"] for row in assignments}, set(game.ARMS))
        self.assertEqual(len({row["seed_base"] for row in assignments}), 7)
        self.assertEqual(len({str(row["prepared"]["contract_profile"]["utilities"])
                              for row in profiles}), 7)
        self.assertEqual(sum(row["intended_calls"] for row in assignments), 630)

    def test_full_readout_retains_people_and_pre_vote_behavior(self):
        result = analysis.readout(design.profiles(), self._records(completed=True))
        self.assertEqual(result["assigned_episodes"], 21)
        self.assertEqual(result["completed_episodes"], 21)
        self.assertEqual(result["completed_profile_pairs"], 21)
        for profile in result["profiles"]:
            for arm in profile["arms"].values():
                self.assertEqual(len(arm["citizen_outcome"]["citizens"]), 63)
                self.assertEqual(len(arm["ballots"]), 2)
                self.assertEqual(len(arm["fixed_continuation_ballot_checks"]), 14)
                self.assertIn("draft_terms", arm)
                self.assertIn("final_terms", arm)
            self.assertEqual(len(profile["pairwise"]), 3)
            self.assertTrue(all(pair["completed"] for pair in profile["pairwise"]))

    def test_incomplete_readout_retains_all_cells_with_finite_bounds(self):
        records = self._records()
        result = analysis.readout(design.profiles(), records)
        self.assertEqual(result["completed_episodes"], 0)
        self.assertEqual(result["completed_profile_pairs"], 0)
        self.assertEqual(len(result["profiles"]), 7)
        for profile in result["profiles"]:
            self.assertEqual(set(profile["arms"]), set(game.ARMS))
            for pair in profile["pairwise"]:
                self.assertFalse(pair["completed"])
                self.assertEqual(pair["finite_bounds"]["possible_outcome_pairs"], 81)
                self.assertEqual(len(pair["finite_bounds"]["district_utility_change"]), 7)
        records.pop(next(iter(records)))
        with self.assertRaisesRegex(ValueError, "assignment inventory"):
            analysis.readout(design.profiles(), records)


if __name__ == "__main__":
    unittest.main()
