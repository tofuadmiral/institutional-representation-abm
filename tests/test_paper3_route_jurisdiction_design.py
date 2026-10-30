"""The prospective frame is fixed by seed and opportunity type, not LLM results."""
import unittest

from paper3 import route_jurisdiction_design as design
from paper3 import route_jurisdiction as game


class RouteJurisdictionDesignTests(unittest.TestCase):
    def test_deterministic_disjoint_frame(self):
        first = design.frame()
        self.assertEqual(first, design.frame())
        self.assertEqual(len(first), 12)
        self.assertEqual(len({p["name"] for p in first}), 12)
        self.assertEqual(sum(p["split"] == "discovery_candidate" for p in first), 4)
        self.assertEqual(sum(p["split"] == "reserved" for p in first), 8)
        for family in design.FAMILIES:
            self.assertEqual(sum(p["family"] == family for p in first), 3)

    def test_certificates_include_negative_controls(self):
        for p in design.frame():
            h, c = p["structural_policy_ids"]["H"], p["structural_policy_ids"]["C"]
            narrow = design.opportunity_readout(p)["narrow"]
            broad = design.opportunity_readout(p)["comprehensive"]
            n_offers = narrow["proposer_optima"]
            b_offers = broad["proposer_optima"]
            if p["family"] == "bypass":
                self.assertEqual(n_offers, [dict(policy_id=h, route="floor")])
                self.assertEqual(b_offers, [dict(policy_id=c, route="committee")])
            elif p["family"] == "aligned_floor":
                self.assertEqual(narrow["proposer_best_utility"], broad["proposer_best_utility"])
                self.assertEqual({x["policy_id"] for x in n_offers}, {h})
                self.assertEqual({x["policy_id"] for x in b_offers}, {h})
                self.assertEqual(n_offers, [dict(policy_id=h, route="floor")])
                self.assertEqual(b_offers, n_offers)
            elif p["family"] == "gridlock":
                self.assertEqual(n_offers, [dict(policy_id=h, route="floor")])
                self.assertEqual(broad["proposer_best_utility"], 0)
                self.assertTrue(all(option["resolution"]["outcome"] == "q"
                                    for option in broad["options"]))
            else:
                self.assertEqual(n_offers, [dict(policy_id=c, route="committee")])
                self.assertEqual(b_offers, n_offers)
                harmed = [a for a in p["actors"] if p["utilities"][a][c] < 0]
                self.assertEqual(len(harmed), 3)
                self.assertNotIn(p["reviewer"], harmed)

    def test_routes_are_genuinely_non_dominated_under_comprehensive_review(self):
        p = next(p for p in design.frame() if p["family"] == "aligned_floor")
        h, c = p["structural_policy_ids"]["H"], p["structural_policy_ids"]["C"]
        def outcome(policy, route):
            ballots = {a: p["utilities"][a][policy] > 0 for a in p["actors"]}
            return game.resolve(p, "comprehensive", dict(policy_id=policy, route=route),
                                ballots, True)["outcome"]
        self.assertEqual(outcome(h, "floor"), h)
        self.assertEqual(outcome(h, "committee"), "q")
        self.assertEqual(outcome(c, "floor"), "q")
        self.assertEqual(outcome(c, "committee"), c)


if __name__ == "__main__":
    unittest.main()
