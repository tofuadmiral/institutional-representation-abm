"""Pre-run candidate-inventory checks; no paid model calls."""
import unittest

from paper3 import electoral_accountability as game
from paper3 import electoral_accountability_design as design
from paper3.electoral_credit_opportunity import evaluate, unique_optimum


class ElectionDesignTests(unittest.TestCase):
    def test_four_distinct_profile_tables_and_complete_one_block_factorial(self):
        inventory = design.inventory()
        self.assertEqual(len(inventory), 4)
        self.assertEqual(len({row["id"] for row in inventory}), 4)
        self.assertEqual(len({tuple(tuple(c["p"] for c in row["profile"]["districts"][f"r{i}"])
                                    for i in game.ACTORS)
                              for row in inventory}), 3)
        assignments = design.candidate_assignments()
        self.assertEqual(len(assignments), 16)
        self.assertEqual(len({row["id"] for row in assignments}), 16)
        self.assertEqual({row["arm"] for row in assignments}, set(game.ARMS))
        self.assertEqual({row["profile_id"] for row in assignments},
                         {row["id"] for row in inventory})

    def test_conflict_cases_have_distinct_role_and_unique_ideal_actions(self):
        conflicts = design.inventory()[:2]
        self.assertNotEqual(conflicts[0]["focal"], conflicts[1]["focal"])
        for row in conflicts:
            with self.subTest(profile=row["id"]):
                self.assertGreater(row["focal_sum"], 0)
                self.assertLess(row["focal_sum"], row["office_bonus"])
                self.assertEqual(row["focal_approval"], 4)
                focal = row["profile"]["districts"][f"r{row['focal']}"]
                values = tuple(c["p"] for c in focal)
                requested = unique_optimum(evaluate(values, office_bonus=30,
                                                    record="requested", binding=True))
                executed = unique_optimum(evaluate(values, office_bonus=30,
                                                   record="executed", binding=True))
                self.assertEqual((requested["consent"], requested["requested_yes"]),
                                 (True, False))
                self.assertEqual((executed["consent"], executed["requested_yes"]),
                                 (False, False))

    def test_controls_remove_conflict_or_office_incentive(self):
        aligned, no_office = design.inventory()[2:]
        self.assertEqual(aligned["focal_approval"], 5)
        self.assertGreater(aligned["focal_sum"], 0)
        self.assertEqual(no_office["office_bonus"], 0)
        self.assertEqual(no_office["focal_approval"], 4)
        self.assertEqual(no_office["focal_sum"], 22)


if __name__ == "__main__":
    unittest.main()
