"""Offline checks for the prospective route-jurisdiction instrument."""
import json
import unittest

from paper3 import route_jurisdiction as game


def profile():
    rows = {
        "r0": [10, 5, 2], "r1": [8, 3, 2], "r2": [8, 3, 2],
        "r3": [8, -2, 2], "r4": [8, -2, 2], "r5": [-7, -2, 2],
        "r6": [-9, 3, 2],
    }
    return game.make_profile("arithmetic-only", {
        a: dict(q=0, p0=v[0], p1=v[1], p2=v[2]) for a, v in rows.items()
    }, proposer="r0", reviewer="r6", committee=["r1", "r2", "r3"],
       floor_threshold=5, committee_threshold=2)


class RouteJurisdictionTests(unittest.TestCase):
    def test_opportunity_is_distinct_from_behavior(self):
        p = profile()
        narrow = game.exact_opportunities(p, "narrow")
        comprehensive = game.exact_opportunities(p, "comprehensive")
        self.assertEqual(narrow["proposer_best_utility"], 10)
        self.assertIn(dict(policy_id="p0", route="floor"), narrow["proposer_optima"])
        self.assertEqual(comprehensive["proposer_best_utility"], 5)
        self.assertIn(dict(policy_id="p1", route="committee"), comprehensive["proposer_optima"])
        self.assertEqual(len(narrow["options"]), 8)
        self.assertEqual(len(comprehensive["options"]), 8)

    def test_fixed_actions_isolate_mechanical_review(self):
        p = profile()
        ballots = {a: p["utilities"][a]["p0"] > 0 for a in p["actors"]}
        offer = dict(policy_id="p0", route="floor")
        narrow = game.resolve(p, "narrow", offer, ballots, False)
        broad = game.resolve(p, "comprehensive", offer, ballots, False)
        self.assertEqual(narrow["outcome"], "p0")
        self.assertEqual(broad["outcome"], "q")
        self.assertFalse(narrow["review_binding"])
        self.assertTrue(broad["review_blocked"])
        self.assertEqual(broad["yes"], 5)

    def test_committee_needs_four_votes_and_review_in_both_arms(self):
        p = profile()
        ballots = {a: p["utilities"][a]["p1"] > 0 for a in p["actors"]}
        offer = dict(policy_id="p1", route="committee")
        for arm in game.ARMS:
            self.assertEqual(game.resolve(p, arm, offer, ballots, True)["outcome"], "p1")
            self.assertEqual(game.resolve(p, arm, offer, ballots, False)["outcome"], "q")
        self.assertEqual(sum(ballots.values()), 4)
        self.assertEqual(game.resolve(p, "narrow", offer, ballots, True)["committee_yes"], 2)

    def test_recommendations_and_ballots_are_sealed(self):
        p = profile()
        recommendation = game.messages(p, "narrow", "r1", "recommendation")
        self.assertNotIn("recommendations", recommendation[1]["content"])
        offer = dict(policy_id="p1", route="committee")
        ballot = game.messages(p, "narrow", "r1", "ballot",
                               recommendations={a: "p0" for a in p["actors"]}, offer=offer)
        self.assertNotIn('"ballots"', ballot[1]["content"])
        review = game.messages(p, "narrow", "r6", "review",
                               recommendations={a: "p0" for a in p["actors"]}, offer=offer,
                               ballots={a: True for a in p["actors"]})
        self.assertIn('"ballots"', review[1]["content"])

    def test_complete_episode_has_same_sixteen_opportunities(self):
        p = profile()
        for arm in game.ARMS:
            calls = []

            def ask(messages):
                context = json.loads(messages[1]["content"].split("\n", 1)[0])
                calls.append(context)
                stage = context["stage"]
                if stage == "recommendation":
                    return '{"policy_id":"p0"}'
                if stage == "offer":
                    return '{"policy_id":"p1","route":"committee"}'
                if stage == "ballot":
                    return json.dumps(dict(yes=p["utilities"][context["acting_for"]]["p1"] > 0))
                return '{"approve":true}'

            result = game.run_episode(p, arm, ask)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(len(calls), 16)
            self.assertEqual([c["stage"] for c in calls].count("recommendation"), 7)
            self.assertEqual([c["stage"] for c in calls].count("ballot"), 7)
            self.assertEqual(result["resolution"]["outcome"], "p1")
            self.assertEqual(len(result["outcome_metrics"]["utilities"]), 7)
            self.assertEqual(result["outcome_metrics"]["harmed_vs_status_quo"], ["r3", "r4", "r5"])
            self.assertTrue(all(v is True for v in result["vote_sign_consistency"].values()))

    def test_invalid_action_keeps_failed_prefix_without_repair(self):
        p = profile()
        responses = iter(['{"policy_id":"p0"}', '{"policy_id":"p0","policy_id":"p1"}'])
        result = game.run_episode(p, "narrow", lambda messages: next(responses))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["actions"]), 1)
        self.assertIn("duplicate", result["error"])

    def test_group_size_is_explicit_not_silently_scaled(self):
        p = profile()
        nine = game.make_profile("nine", {**p["utilities"],
                         "r7": dict(q=0, p0=1, p1=-1, p2=2),
                         "r8": dict(q=0, p0=-1, p1=1, p2=2)},
                         proposer="r0", reviewer="r6",
                         committee=["r1", "r2", "r3", "r4", "r5"],
                         floor_threshold=7, committee_threshold=3)
        self.assertEqual(len(nine["actors"]), 9)
        self.assertEqual(nine["floor_threshold"], 7)
        self.assertEqual(nine["committee_threshold"], 3)
        self.assertRaises(ValueError, game.make_profile, "bad", nine["utilities"],
                          proposer="r0", reviewer="r6",
                          committee=["r1", "r2", "r3", "r4", "r5"],
                          floor_threshold=5, committee_threshold=6)

    def test_metrics_expose_all_principals_not_just_reviewer(self):
        m = game.metrics(profile(), "p1")
        self.assertEqual(m["harmed_vs_status_quo"], ["r3", "r4", "r5"])
        self.assertEqual(set(m["own_best_regret"]), set(profile()["actors"]))
        self.assertGreater(m["total_utility"], 0)


if __name__ == "__main__":
    unittest.main()
