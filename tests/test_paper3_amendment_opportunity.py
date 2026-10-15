import unittest

from paper3 import amendment_opportunity as opportunity
from paper3 import direct_ratification as base


class AmendmentOpportunityTests(unittest.TestCase):
    def test_frame_is_deterministic_and_has_no_duplicate_profiles(self):
        first = opportunity.frame()
        self.assertEqual(first, opportunity.frame())
        self.assertEqual(len(first), 8)
        self.assertEqual(len({row["profile"]["id"] for row in first}), 8)

    def test_each_profile_has_the_declared_legal_and_mandate_opportunity(self):
        for row in opportunity.frame():
            with self.subTest(row=row["profile"]["id"]):
                profile = row["profile"]
                base.validate(profile)
                outsider = f'r{row["outsider"]}'
                self.assertEqual(base.poll(profile, row["favorite"])["yes_counts"][outsider], 4)
                self.assertEqual(base.poll(profile, "C")["yes_counts"][outsider], 9)
                self.assertGreaterEqual(len(row["favorite_support"]), 4)
                self.assertGreaterEqual(len(row["compromise_support"]), 4)
                self.assertEqual(len(row["outsider_ideal_support"]), 3)
                self.assertEqual(len(row["ideal_over_favorite"]), 3)
                self.assertEqual(len(row["compromise_over_favorite"]),
                                 4 if row["stratum"] == "mandate_aligned" else 3)
                self.assertEqual(row["profile"]["proposer"] in row["favorite_support"], True)
                self.assertEqual(row["outsider"] in row["compromise_support"], True)
                outsider_sums = row["district_totals"][outsider]
                self.assertGreater(outsider_sums[row["outsider_ideal"]],
                                   max(outsider_sums[row["favorite"]], outsider_sums["C"]))
                if row["stratum"] == "mandate_aligned":
                    self.assertGreater(outsider_sums["C"], outsider_sums[row["favorite"]])
                else:
                    self.assertGreater(outsider_sums[row["favorite"]], outsider_sums["C"])

    def test_bad_parameters_fail(self):
        for args in ((-1, "mandate_aligned"), (0, "unknown"), (4, "mandate_divergent")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                opportunity.draw(*args)
