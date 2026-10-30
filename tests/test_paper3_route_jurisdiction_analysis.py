"""No cherry-picking completed episodes in the route discovery readout."""
import json
import unittest

from paper3 import route_jurisdiction as game
from paper3 import route_jurisdiction_analysis as analysis
from paper3 import route_jurisdiction_design as design


def episode(profile, arm, policy, route, review):
    def ask(messages):
        context = json.loads(messages[1]["content"].split("\n", 1)[0])
        stage = context["stage"]
        if stage == "recommendation":
            return json.dumps(dict(policy_id=policy))
        if stage == "offer":
            return json.dumps(dict(policy_id=policy, route=route))
        if stage == "ballot":
            actor = context["acting_for"]
            return json.dumps(dict(yes=profile["utilities"][actor][policy] > 0))
        return json.dumps(dict(approve=review))
    result = game.run_episode(profile, arm, ask)
    assert result["status"] == "completed"
    return result


class RouteJurisdictionAnalysisTests(unittest.TestCase):
    def test_paired_offer_change_separate_from_mechanical_replay(self):
        p = design.frame()[0]
        h, c = p["structural_policy_ids"]["H"], p["structural_policy_ids"]["C"]
        records = {(p["name"], "narrow"): episode(p, "narrow", h, "floor", False),
                   (p["name"], "comprehensive"): episode(p, "comprehensive", c, "committee", True)}
        report = analysis.readout([p], records)
        self.assertEqual(report["completed_pairs"], 1)
        self.assertTrue(report["pairs"][0]["pre_vote_policy_changed"])
        self.assertTrue(report["pairs"][0]["pre_vote_route_changed"])
        self.assertEqual(report["pre_vote_any_change_rate_bounds"], [1.0, 1.0])
        self.assertEqual(set(report["assignments"][0]["outcome_utilities"]), set(p["actors"]))
        self.assertEqual(report["pairs"][0]["narrow_fixed_action_replay"]["comprehensive"]["outcome"], "q")

    def test_missing_pair_retained_with_finite_bounds(self):
        p, q = design.frame()[0], design.frame()[3]
        h, c = p["structural_policy_ids"]["H"], p["structural_policy_ids"]["C"]
        records = {(p["name"], "narrow"): episode(p, "narrow", h, "floor", False),
                   (p["name"], "comprehensive"): episode(p, "comprehensive", c, "committee", True),
                   (q["name"], "narrow"): dict(status="failed", error="bad JSON"),
                   (q["name"], "comprehensive"): None}
        report = analysis.readout([p, q], records)
        self.assertEqual(report["total_pairs"], 2)
        self.assertEqual(report["completed_pairs"], 1)
        self.assertEqual(report["missing_pairs"], 1)
        self.assertEqual(report["pre_vote_any_change_rate_bounds"], [0.5, 1.0])
        self.assertEqual(report["pairs"][1]["status"], "incomplete")
        self.assertEqual([x["status"] for x in report["assignments"]],
                         ["completed", "completed", "failed", "not_started"])
        self.assertAlmostEqual(report["mean_regret_delta_bounds"][1]
                               - report["mean_regret_delta_bounds"][0], 1.0)

    def test_missing_assignment_or_tampered_resolution_rejected(self):
        p = design.frame()[0]
        h = p["structural_policy_ids"]["H"]
        one = episode(p, "narrow", h, "floor", False)
        with self.assertRaisesRegex(ValueError, "every assigned episode"):
            analysis.readout([p], {(p["name"], "narrow"): one})
        one["resolution"] = dict(one["resolution"], outcome="q")
        with self.assertRaisesRegex(ValueError, "does not replay"):
            analysis.readout([p], {(p["name"], "narrow"): one,
                                   (p["name"], "comprehensive"): None})


if __name__ == "__main__":
    unittest.main()
