"""Offline arithmetic checks only; no hosted calls or model behavior."""
import unittest

from paper3.electoral_credit_opportunity import evaluate, unique_optimum


CONFLICT = (-2, -2, -2, -2, -2, 8, 8, 8, 8)
ALIGNED = (3, 3, 3, 3, 3, -1, -1, -1, -1)


class CreditOpportunityTests(unittest.TestCase):
    def test_binding_request_record_uniquely_rewards_hidden_yes(self):
        options = evaluate(CONFLICT, office_bonus=30,
                           record="requested", binding=True)
        winner = unique_optimum(options)
        self.assertIsNotNone(winner)
        self.assertEqual((winner["consent"], winner["requested_yes"],
                          winner["executed_yes"], winner["enacted"]),
                         (True, False, True, True))
        self.assertEqual((winner["retain_votes"], winner["representative_payoff"]),
                         (5, 52))

    def test_binding_execution_record_uniquely_rewards_refusal(self):
        options = evaluate(CONFLICT, office_bonus=30,
                           record="executed", binding=True)
        winner = unique_optimum(options)
        self.assertIsNotNone(winner)
        self.assertEqual((winner["consent"], winner["requested_yes"],
                          winner["executed_yes"], winner["enacted"]),
                         (False, False, False, False))
        self.assertEqual((winner["retain_votes"], winner["representative_payoff"]),
                         (5, 30))

    def test_no_binding_contract_cannot_hide_an_enacted_yes(self):
        for record in ("requested", "executed"):
            options = evaluate(CONFLICT, office_bonus=30,
                               record=record, binding=False)
            self.assertFalse(any(row["enacted"] and not row["requested_yes"]
                                 for row in options))
            self.assertIsNone(unique_optimum(options))

    def test_without_office_bonus_attribution_does_not_change_policy_optimum(self):
        for record in ("requested", "executed"):
            options = evaluate(CONFLICT, office_bonus=0,
                               record=record, binding=True)
            best = max(row["representative_payoff"] for row in options)
            self.assertEqual(best, 22)
            self.assertTrue(all(row["enacted"] for row in options
                                if row["representative_payoff"] == best))

    def test_aligned_majority_does_not_create_a_hidden_vote_incentive(self):
        for record in ("requested", "executed"):
            options = evaluate(ALIGNED, office_bonus=30,
                               record=record, binding=True)
            best = max(row["representative_payoff"] for row in options)
            self.assertEqual(best, 41)
            self.assertTrue(all(row["enacted"] and row["executed_yes"]
                                for row in options if row["representative_payoff"] == best))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            evaluate((1,) * 8, office_bonus=30, record="requested", binding=True)
        with self.assertRaises(ValueError):
            evaluate(CONFLICT, office_bonus=-1, record="requested", binding=True)
        with self.assertRaises(ValueError):
            evaluate(CONFLICT, office_bonus=30, record="private", binding=True)


if __name__ == "__main__":
    unittest.main()
