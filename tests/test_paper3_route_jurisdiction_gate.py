"""Prospective gate construction and exact offline scoring."""
import json
import unittest

from paper3 import route_jurisdiction_gate as gate


class RouteJurisdictionGateTests(unittest.TestCase):
    def test_twelve_distinct_cases_cover_rules_and_actual_action_stages(self):
        cases = gate.cases()
        self.assertEqual(len(cases), 12)
        self.assertEqual(len({c["name"] for c in cases}), 12)
        self.assertEqual(sum(c["kind"] == "rule" for c in cases), 8)
        self.assertEqual({c["stage"] for c in cases if c["kind"] == "action"},
                         {"recommendation", "offer", "ballot", "review"})
        self.assertEqual(sum(c["arm"] == "narrow" for c in cases[:8]), 4)
        self.assertEqual(sum(c["arm"] == "comprehensive" for c in cases[:8]), 4)

    def test_expected_answers_score_exact_and_not_in_prompt(self):
        for case in gate.cases():
            answer = dict(case["expected"])
            if case["name"] == "action-offer":
                answer["route"] = "floor"
            raw = json.dumps(answer)
            with self.subTest(case=case["name"]):
                self.assertTrue(gate.score(raw, case)["exact"])
                self.assertNotIn(raw, case["messages"][1]["content"])

    def test_rule_boundary_errors_do_not_pass(self):
        # Independently specified expected answers guard against a shared bug
        # in case construction and the resolver used to build the key.
        manual = [
            ("p0", False, "p0"), ("q", True, "p1"),
            ("q", False, "p2"), ("q", True, "p1"),
            ("p0", True, "p2"), ("p0", True, "p2"),
            ("q", True, "p0"), ("q", True, "p2"),
        ]
        self.assertEqual([
            (c["expected"]["outcome"], c["expected"]["review_binding"],
             c["expected"]["own_best_policy"]) for c in gate.cases()[:8]
        ], manual)
        for case in gate.cases()[:8]:
            wrong = dict(case["expected"], review_binding=not case["expected"]["review_binding"])
            with self.subTest(case=case["name"]):
                self.assertFalse(gate.score(json.dumps(wrong), case)["exact"])
        # Crossing the same five-yes floor/rejected-review case changes only
        # whether recorded review binds.
        self.assertEqual(gate.cases()[0]["expected"]["outcome"], "p0")
        self.assertEqual(gate.cases()[1]["expected"]["outcome"], "q")

    def test_invalid_json_duplicate_keys_and_bad_types_fail(self):
        case = gate.cases()[0]
        for raw in ('{"outcome":"p0","outcome":"q","review_binding":false,"own_best_policy":"p0"}',
                    '{"outcome":"p0","review_binding":1,"own_best_policy":"p0"}',
                    'not JSON'):
            self.assertFalse(gate.score(raw, case)["exact"])
        action = next(c for c in gate.cases() if c["name"] == "action-ballot")
        self.assertFalse(gate.score('{"yes":1}', action)["exact"])

    def test_offer_control_allows_both_routes_but_requires_dominant_policy(self):
        offer = next(c for c in gate.cases() if c["name"] == "action-offer")
        self.assertTrue(gate.score('{"policy_id":"p0","route":"floor"}', offer)["exact"])
        self.assertTrue(gate.score('{"policy_id":"p0","route":"committee"}', offer)["exact"])
        self.assertFalse(gate.score('{"policy_id":"p1","route":"committee"}', offer)["exact"])


if __name__ == "__main__":
    unittest.main()
