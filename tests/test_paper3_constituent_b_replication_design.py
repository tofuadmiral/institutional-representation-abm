"""Offline checks for a conditional, not-yet-authorized replication frame."""
import json
import unittest

from paper3 import constituent_b_qwen_design as discovery
from paper3 import constituent_b_replication_design as replication


class ConstituentBReplicationDesignTests(unittest.TestCase):
    def test_profiles_are_untouched_and_opportunity_preserved(self):
        candidate = replication.profiles()
        previous = discovery.profiles()
        self.assertEqual(len(candidate), 9)
        self.assertEqual(len({row["prepared"]["contract_profile"]["id"]
                              for row in candidate}), 9)
        def utility_tables(rows):
            return {json.dumps(row["prepared"]["contract_profile"]["utilities"],
                               sort_keys=True) for row in rows}
        self.assertFalse(utility_tables(candidate) & utility_tables(previous))
        self.assertEqual({row["family"] for row in candidate},
                         {"exchange_majority_conflict_outsider_harm",
                          "exchange_majority_aligned_outsider_harm",
                          "majority_conflict_outsider_support_control"})
        self.assertEqual(sum(row["strict_with_outsider_harm"] > 0
                             for row in candidate), 6)

    def test_complete_pairing_and_fresh_seeds(self):
        assignments = replication.assignments()
        self.assertEqual(len(assignments), 27)
        self.assertEqual(len({row["id"] for row in assignments}), 27)
        self.assertEqual(sum(row["intended_calls"] for row in assignments), 810)
        by_profile = {}
        for row in assignments:
            by_profile.setdefault(row["profile_id"], []).append(row)
        self.assertEqual(len(by_profile), 9)
        for rows in by_profile.values():
            self.assertEqual({row["arm"] for row in rows},
                             {"public_promise", "member_enforcement",
                              "universal_clearance"})
            self.assertEqual(len({row["seed_base"] for row in rows}), 1)
        candidate_seeds = {row["seed_base"] + i for row in assignments
                           for i in range(row["intended_calls"])}
        discovery_seeds = {row["seed_base"] + i for row in discovery.assignments()
                           for i in range(row["intended_calls"])}
        self.assertEqual(len(candidate_seeds), 270)
        self.assertFalse(candidate_seeds & discovery_seeds)


if __name__ == "__main__":
    unittest.main()
